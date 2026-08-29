import asyncio
import logging
import re

from backend.src.agents.a11y_expert_reviewer.a11y_expert_reviewer import run_a11y_expert_reviewer
from backend.src.agents.agentic_ai_ui.agentic_ai_ui import run_agentic_ai_ui_agent
from backend.src.agents.ajax_dynamic.ajax_dynamic import run_ajax_dynamic
from backend.src.agents.angular_framework.angular_framework import run_angular_framework
from backend.src.agents.aria_specialist.aria_specialist import run_aria_specialist
from backend.src.agents.checklist.checklist import run_checklist
from backend.src.agents.classifier.classifier import run_classifier
from backend.src.agents.cognitive.cognitive import run_cognitive
from backend.src.agents.compliance_audit.compliance_audit import run_compliance_audit
from backend.src.agents.css_analyzer.css_analyzer import run_css_analyzer
from backend.src.agents.delegation_coordinator.delegation_coordinator import run_delegation_coordinator
from backend.src.agents.fixer.fixer import run_fixer
from backend.src.agents.forms_a11y.forms_a11y import run_forms_a11y
from backend.src.agents.gap_research.gap_research import run_gap_research_check
from backend.src.agents.link_checker.link_checker import run_link_checker
from backend.src.agents.mobile_a11y.mobile_a11y import run_mobile_a11y
from backend.src.agents.niche_domains.niche_domains import run_niche_domains_agent
from backend.src.agents.operability.operability import run_operability
from backend.src.agents.perceiver.perceiver import run_perceiver
from backend.src.agents.react_framework.react_framework import run_react_framework
from backend.src.agents.reporter.reporter import run_reporter
from backend.src.agents.robustness.robustness import run_robustness
from backend.src.agents.screen_reader.screen_reader import run_screen_reader
from backend.src.agents.section508.section508 import run_section508
from backend.src.agents.spatial_3d_xr.spatial_3d_xr import run_spatial_3d_xr_agent
from backend.src.agents.svelte_framework.svelte_framework import run_svelte_framework
from backend.src.agents.tables_data.tables_data import run_tables_data
from backend.src.agents.tailwind_css.tailwind_css import run_tailwind_css
from backend.src.agents.test_generator.test_generator import run_test_generator
from backend.src.agents.understandability.understandability import run_understandability
from backend.src.agents.visual_a11y.visual_a11y import run_visual_a11y
from backend.src.agents.vpat_reporter.vpat_reporter import run_vpat_reporter
from backend.src.agents.vue_framework.vue_framework import run_vue_framework
from backend.src.agents.wcag_semantics.wcag_semantics import run_wcag_semantics
from backend.src.agents.web_components.web_components import run_web_components_agent
from backend.src.agents.widgets_a11y.widgets_a11y import run_widgets_a11y
from backend.src.config.settings import get_settings
from backend.src.services import batch_collector, chat_progress
from backend.src.services.complexity_router import classify_and_set_tradeoff
from backend.src.services.contrast_verifier import verify_contrast_issues
from backend.src.services.lessons_store import get_known_false_positive_patterns, record_false_positive_removal
from backend.src.shared.i18n.criteria_pt import translate_issues
from backend.src.shared.models import (
    SUPPORTED_FRAMEWORKS,
    AccessibilityIssue,
    AgentMetrics,
    AgentResult,
    ChecklistItem,
    Confidence,
    TaskType,
)

logger = logging.getLogger(__name__)

# Guardrail: max issues apos merge de todos os sub-agentes
MAX_ISSUES = 150

FRAMEWORK_AGENT_BY_TECH = {
    "react": "react_framework",
    "angular": "angular_framework",
    "vue": "vue_framework",
    "svelte": "svelte_framework",
    "tailwind": "tailwind_css",
}

CORE_ANALYSIS_AGENTS = {
    "perceiver": "base WCAG perceptivel sempre relevante para página web",
    "operability": "base WCAG operavel sempre relevante para página web",
    "understandability": "base WCAG compreensivel sempre relevante para página web",
    "robustness": "base WCAG robusto sempre relevante para página web",
    "aria_specialist": "ARIA e semântica assistiva podem afetar qualquer página web",
    "section508": "conformidade legal geral para página web",
    "screen_reader": "compatibilidade com leitor de tela e essencial em página web",
    "wcag_semantics": "semântica HTML e tecnologias assistivas",
    "compliance_audit": "revisao consolidada WCAG/Section 508",
    "agentic_ai_ui": "interfaces de IA agêntica, live regions e modais HITL",
    "spatial_3d_xr": "WebXR XAUR 2026, Canvas Three.js/Babylon.js PAT DOM",
    "web_components": "Custom Elements FACE ElementInternals e shadowrootreferencetarget",
    "niche_domains": "Passkeys SC 3.3.8/3.3.9, Sonificação D3 e Kiosks ADA/EAA",
}


def _detect_page_language(html_content: str) -> str:
    """Extrai o idioma declarado no HTML, quando existir."""
    match = re.search(r"<html\b[^>]*\blang\s*=\s*['\"]?([a-zA-Z0-9_-]+)", html_content, re.I)
    return match.group(1).lower() if match else "unknown"


def _has_form_controls(html_content: str) -> bool:
    return bool(re.search(r"<(form|input|select|textarea|button)\b", html_content, re.I))


def _has_css_surface(html_content: str) -> bool:
    return bool(
        re.search(r"\b(class|style)\s*=", html_content, re.I)
        or re.search(r"<style\b|rel\s*=\s*['\"]stylesheet", html_content, re.I)
    )


def _has_dynamic_surface(html_content: str) -> bool:
    return bool(
        re.search(r"<script\b", html_content, re.I)
        or re.search(r"\b(aria-live|aria-busy)\s*=", html_content, re.I)
        or re.search(r"\bdata-[\w:-]+\s*=", html_content, re.I)
    )


def _has_widget_surface(html_content: str) -> bool:
    return bool(
        re.search(
            r"\brole\s*=\s*['\"]?(button|tab|tabpanel|dialog|menu|menuitem|listbox|option|combobox|switch|slider|tree|grid)",
            html_content,
            re.I,
        )
        or re.search(r"\baria-(expanded|pressed|selected|controls|haspopup|activedescendant)\s*=", html_content, re.I)
    )


def _has_mobile_surface(html_content: str) -> bool:
    return bool(
        re.search(r"<meta\b[^>]*name\s*=\s*['\"]viewport", html_content, re.I)
        or re.search(r"\bmedia\s*=", html_content, re.I)
        or re.search(r"@media\b", html_content, re.I)
    )


def _has_cognitive_surface(html_content: str) -> bool:
    text_len = len(re.sub(r"<[^>]+>", " ", html_content))
    return _has_form_controls(html_content) or text_len > 1200


def _has_data_table(html_content: str) -> bool:
    return bool(re.search(r"<table\b", html_content, re.I))


def _has_links(html_content: str) -> bool:
    return bool(re.search(r"<a\b[^>]*\bhref\s*=", html_content, re.I))


def _conditional_agent_reasons(html_content: str) -> dict[str, str]:
    """Seleciona agentes por evidencias estruturais do HTML, não por texto do prompt."""
    reasons: dict[str, str] = {}
    if _has_css_surface(html_content):
        reasons["css_analyzer"] = "HTML contem superficie CSS: classes, estilos inline, style ou stylesheet"
    if _has_dynamic_surface(html_content):
        reasons["ajax_dynamic"] = "HTML contem superficie dinamica: script, data-* ou aria-live/busy"
    if _has_cognitive_surface(html_content):
        reasons["cognitive"] = "página tem formulário ou volume de texto que exige avaliacao cognitiva"
    if _has_mobile_surface(html_content):
        reasons["mobile_a11y"] = "HTML contem viewport, media query ou superficie responsiva"
    if _has_form_controls(html_content):
        reasons["forms_a11y"] = "HTML contem controles de formulário/interacao"
    if _has_widget_surface(html_content):
        reasons["widgets_a11y"] = "HTML contem roles/estados ARIA de widgets interativos"
    if _has_data_table(html_content):
        reasons["tables_data"] = "HTML contem elemento <table>"
    if _has_links(html_content):
        reasons["link_checker"] = "HTML contem links (<a href>)"
    return reasons


_EFFORT_TIMEOUT_SECONDS: dict[str, float] = {
    # Achado real (2026-08-11, pesquisa de mercado + auditoria ao vivo): a
    # ligação tradeoff -> reasoning_effort (llm_client.py) faz o modelo
    # "pensar mais" por design em tarefas complexas -- pesquisa confirma que
    # raciocínio pode ser 5-10x mais lento que sem raciocínio, e o padrão de
    # mercado 2026 pra modelos com raciocínio é 180-300s de timeout conforme
    # a profundidade. Um timeout FIXO de 180s pra qualquer esforço penalizava
    # justamente as tarefas que MAIS precisam de qualidade (esforço alto) --
    # confirmado ao vivo: 11/23 agentes deram timeout numa rodada real após
    # essa mudança, todos "Timeout after 180.0s".
    "none": 180.0,
    "low": 210.0,
    "medium": 240.0,
    "high": 300.0,
}
_DEFAULT_AGENT_TIMEOUT = 180.0


def _get_agent_timeout() -> float:
    """Timeout por sub-agente, adaptado ao esforço de raciocínio corrente
    (ver _EFFORT_TIMEOUT_SECONDS) -- lê o mesmo tradeoff que decide o esforço
    em llm_client.py, então cresce exatamente quando o modelo de fato vai
    demorar mais. Nunca menor que o valor configurado em Settings (piso
    histórico), só cresce a partir dele conforme o esforço."""
    try:
        base = get_settings().agent_timeout_seconds
    except Exception:
        base = _DEFAULT_AGENT_TIMEOUT
    try:
        from backend.src.services.complexity_router import get_current_tradeoff
        from backend.src.services.llm_client import _reasoning_effort_for_tradeoff
        effort = _reasoning_effort_for_tradeoff(get_current_tradeoff())
        return max(base, _EFFORT_TIMEOUT_SECONDS.get(effort, base))
    except Exception:
        return base


async def _timed(name: str, coro_factory) -> tuple[AgentResult, float]:
    """
    Executa a coroutine de um agente (via `coro_factory`, uma função sem
    argumentos que cria uma coroutine NOVA a cada chamada) com timeout e
    captura de excecoes. Nunca propaga excecao — erros sao convertidos em
    AgentResult de falha. Retorna (AgentResult, duration_ms).

    Achado real (2026-08-11, "nada pode falhar" -- pedido do usuário,
    pesquisa 2026 de resiliência de API de LLM confirma retry+backoff como
    padrão pra timeout): se a primeira tentativa estourar o timeout, refaz
    UMA vez (fresh coroutine, mesmo timeout já adaptado ao esforço) antes de
    desistir -- muitos timeouts são fila/latência transitória do provider,
    não um problema real da tarefa em si. `coro_factory` (não uma coroutine
    já criada) é o que torna esse retry possível: uma coroutine só pode ser
    aguardada uma vez.
    """
    loop = asyncio.get_running_loop()
    start = loop.time()
    chat_progress.emit({"type": "agent", "phase": "start", "agent": name})
    timeout = _get_agent_timeout()
    result: AgentResult | None = None

    for attempt in range(2):
        retry_token = None
        if attempt == 1:
            # Achado real (2026-08-11, confirmado ao vivo contra dequeuniversity
            # mars page apos o fix de timeout adaptativo+retry): retry com o
            # MESMO esforco de raciocinio nao ajuda quando o agente e
            # genuinamente lento por conteudo grande/denso (ex.: robustness,
            # aria_specialist estouraram 240s DUAS vezes seguidas) -- o
            # segundo timeout so soma tempo de espera sem mudar o resultado.
            # Retry rebaixa o tradeoff em +3 (uma escala de esforco abaixo,
            # ver _reasoning_effort_for_tradeoff em llm_client.py) SO para essa
            # tentativa, dentro do Task isolado deste agente (ContextVar nao
            # vaza pros outros agentes rodando em paralelo) -- troca um pouco
            # de qualidade por uma chance real de terminar dentro do timeout,
            # em vez de garantidamente falhar de novo com o mesmo esforco.
            from backend.src.services.complexity_router import get_current_tradeoff, set_current_tradeoff
            retry_token = set_current_tradeoff(get_current_tradeoff() + 3)
        try:
            result = await asyncio.wait_for(coro_factory(), timeout=timeout)
            break
        except asyncio.TimeoutError:
            if attempt == 0:
                logger.warning(
                    "[Orchestrator] Agente '%s' estourou o timeout (%.0fs) na 1a tentativa; refazendo uma vez com esforço reduzido.",
                    name, timeout,
                )
                continue
            result = AgentResult(agent=name, success=False, data={}, error=f"Timeout after {timeout}s (2 tentativas)")
        except Exception as exc:
            result = AgentResult(agent=name, success=False, data={}, error=str(exc))
            break
        finally:
            if retry_token is not None:
                from backend.src.services.complexity_router import reset_current_tradeoff
                reset_current_tradeoff(retry_token)

    assert result is not None
    duration_ms = (loop.time() - start) * 1000
    chat_progress.emit({
        "type": "agent",
        "phase": "done",
        "agent": name,
        "ok": result.success,
        "issues": len(result.data.get("issues", [])) if result.success else 0,
    })
    return result, duration_ms


def _extract_issues(result: AgentResult) -> list[AccessibilityIssue]:
    """Extrai issues de um AgentResult. Falha do agente eh distinta de lista vazia."""
    if not result.success:
        logger.warning(
            "[Orchestrator] Sub-agente '%s' reportou falha: %s",
            result.agent,
            result.error,
        )
        return []
    return [AccessibilityIssue(**i) for i in result.data.get("issues", [])]


def _extract_checklist(result: AgentResult) -> list[ChecklistItem]:
    if not result.success:
        return []
    return [ChecklistItem(**i) for i in result.data.get("checklist", [])]


_CRITERION_CODE_RE = re.compile(r"^\s*(\d+(?:\.\d+)+)")


def _deduplicate_issues(issues: list[AccessibilityIssue]) -> list[AccessibilityIssue]:
    """Remove issues duplicados pelo mesmo criterion+element.

    Chave normalizada pelo CÓDIGO do criterion (ex.: "1.4.3"), não a string
    inteira. Achado real: dois agentes descrevendo o mesmo achado às vezes
    variam a fraseologia do nome ("1.4.3 Contrast Minimum" vs "1.4.3 Contrast
    (Minimum)") -- variação normal entre chamadas de LLM independentes, mas
    que com chave por string inteira deixava o duplicado escapar da dedup.
    Sem código reconhecível (formato inesperado), cai no fallback da string
    completa em minúsculas -- ainda melhor que nenhuma normalização.
    """
    seen: set[str] = set()
    unique: list[AccessibilityIssue] = []
    for issue in issues:
        match = _CRITERION_CODE_RE.match(issue.criterion)
        criterion_key = match.group(1) if match else issue.criterion.strip().lower()
        key = f"{criterion_key}|{issue.element.strip().lower()}"
        if key not in seen:
            seen.add(key)
            unique.append(issue)
    return unique


def _summarize_issues_for_delegation(issues: list[AccessibilityIssue], limit: int = 60) -> str:
    """Resumo textual e compacto dos issues da rodada 1 pro coordenador de
    delegacao -- criterion + severity + element, sem os campos longos
    (description/suggestion), pra manter o prompt pequeno e barato."""
    lines = [f"- [{i.severity}] {i.criterion} -- {i.element[:120]}" for i in issues[:limit]]
    if len(issues) > limit:
        lines.append(f"... e mais {len(issues) - limit} issue(s) nao listados aqui")
    return "\n".join(lines) if lines else "(nenhum issue encontrado na rodada 1)"


MAX_DELEGATION_ROUNDS = 2


async def _run_delegation_round(
    unique: list[AccessibilityIssue],
    skipped_reasons: dict[str, str],
    all_available_agents: dict,
) -> tuple[list[AccessibilityIssue], list[AgentMetrics], list[dict[str, str]]]:
    """Rodada 2+ (opcional, limitada): delegacao dinamica agente-a-agente,
    como um LOOP real com condicao de parada -- nao uma rodada extra fixa.

    A cada volta: um coordenador (LLM) le os achados ATUALIZADOS + os agentes
    ainda nao acionados e decide se delega mais algum. O loop para quando (a)
    o coordenador nao delega mais nada (convergencia natural), (b) todos os
    agentes pulados ja foram delegados, ou (c) MAX_DELEGATION_ROUNDS e
    atingido (backstop -- nunca um loop aberto). Cada delegacao ja acionada
    sai da lista de candidatos da proxima volta, entao o loop sempre progride
    ou para -- nunca repete a mesma decisao.

    Retorna tambem `delegation_edges` (grafo explicito: quem delegou pra quem,
    em qual rodada, e por que) -- ver Graph Engineering em AgentResult.data['pipeline_graph'].
    """
    metrics: list[AgentMetrics] = []
    delegation_edges: list[dict[str, str]] = []
    remaining_skipped = dict(skipped_reasons)

    for round_num in range(1, MAX_DELEGATION_ROUNDS + 1):
        if not remaining_skipped:
            break
        issues_summary = _summarize_issues_for_delegation(unique)
        coordinator_result = await run_delegation_coordinator(issues_summary, remaining_skipped)
        delegations = coordinator_result.data.get("delegations", []) if coordinator_result.success else []
        if not delegations:
            logger.info("[Orchestrator] Loop de delegacao convergiu na rodada %d (nada mais a delegar).", round_num)
            break

        logger.info(
            "[Orchestrator] Delegacao dinamica (rodada %d/%d): %d agente(s) pulado(s) acionado(s): %s",
            round_num, MAX_DELEGATION_ROUNDS, len(delegations),
            ", ".join(d["target_agent"] for d in delegations),
        )

        delegated_issues: list[AccessibilityIssue] = []
        for delegation in delegations:
            target = delegation["target_agent"]
            coro_factory = all_available_agents.get(target)
            if coro_factory is None:
                logger.warning("[Orchestrator] Delegacao ignorada: agente '%s' nao existe no catalogo", target)
                continue
            result, duration_ms = await _timed(target, coro_factory)
            issues_found = len(result.data.get("issues", []))
            metrics.append(
                AgentMetrics(
                    agent=result.agent,
                    duration_ms=round(duration_ms, 1),
                    issues_found=issues_found,
                    success=result.success,
                    delegated_by="delegation_coordinator",
                )
            )
            delegated_issues.extend(_extract_issues(result))
            delegation_edges.append({
                "from": "delegation_coordinator",
                "to": target,
                "round": str(round_num),
                "reason": delegation["reason"],
            })
            remaining_skipped.pop(target, None)
            logger.info(
                "[Orchestrator] Agente delegado '%s' concluido (rodada %d) -- %d issues novos (motivo: %s)",
                target, round_num, issues_found, delegation["reason"],
            )

        unique = _deduplicate_issues(unique + delegated_issues)
    else:
        if remaining_skipped:
            logger.info(
                "[Orchestrator] Loop de delegacao parou no limite de %d rodadas (backstop) -- %d agente(s) ainda pulado(s): %s",
                MAX_DELEGATION_ROUNDS, len(remaining_skipped), list(remaining_skipped),
            )

    return unique, metrics, delegation_edges


def _build_pipeline_graph(
    routing_reasons: dict[str, str],
    skipped_reasons: dict[str, str],
    delegation_edges: list[dict[str, str]],
) -> dict[str, list[dict[str, str]]]:
    """Representacao explicita do grafo de execucao desta analise (Graph
    Engineering): nos (cada agente, com seu estado -- selecionado, pulado ou
    delegado -- e o motivo real da decisao) e arestas (classifier -> cada
    agente selecionado; delegation_coordinator -> cada agente delegado, com a
    rodada e o motivo). Dado observavel, nao so controle de fluxo implicito
    no codigo -- permite inspecionar/depurar a topologia real de uma analise
    especifica sem ler logs."""
    delegated_targets = {edge["to"] for edge in delegation_edges}
    nodes = [
        {"agent": name, "state": "selected", "reason": reason}
        for name, reason in routing_reasons.items()
    ] + [
        {"agent": name, "state": "delegated" if name in delegated_targets else "skipped", "reason": reason}
        for name, reason in skipped_reasons.items()
        if name not in delegated_targets
    ] + [
        {"agent": name, "state": "delegated", "reason": "acionado pelo delegation_coordinator"}
        for name in delegated_targets
    ]
    edges = [
        {"from": "classifier", "to": name, "reason": reason}
        for name, reason in routing_reasons.items()
    ] + delegation_edges
    return {"nodes": nodes, "edges": edges}


async def _run_gap_research_step(unique: list[AccessibilityIssue]) -> tuple[list[AccessibilityIssue], AgentMetrics | None]:
    """Verificacao automatica de lacuna: quando um sub-agente reportou baixa
    confianca (confidence=low) num achado, delega pro agente real de Deep
    Research (pesquisa normativa na web) pra confirmar/refutar contra a fonte
    primaria, em vez de deixar essa incerteza sem resolucao. Anexa a resposta
    pesquisada em `why_technical` -- reforco aditivo, nunca sobrescreve
    severidade/confianca sozinho (isso continua sendo o a11y_expert_reviewer).
    Best-effort: falha ou nenhum issue de baixa confianca -> devolve `unique`
    inalterado e nenhuma metrica."""
    low_confidence = [i for i in unique if i.confidence == Confidence.LOW]
    if not low_confidence:
        return unique, None

    result = await run_gap_research_check(low_confidence)
    if not result.success or not result.data.get("answer"):
        return unique, AgentMetrics(agent="gap_research", duration_ms=0.0, issues_found=0, success=False)

    answer = result.data["answer"]
    covered_ids = set(result.data.get("issue_ids", []))
    updated = []
    for issue in unique:
        if issue.id in covered_ids:
            note = f"\n\n[Verificação normativa automática]: {answer}"
            issue = issue.model_copy(update={"why_technical": (issue.why_technical or "") + note})
        updated.append(issue)

    return updated, AgentMetrics(agent="gap_research", duration_ms=0.0, issues_found=len(covered_ids), success=True)


async def _run_analysis_pipeline(
    html_content: str,
    screenshot_base64: str | None = None,
    focus_screenshots: list[str] | None = None,
    only_agents: list[str] | None = None,
    batch_collect: bool = False,
) -> tuple[list[AccessibilityIssue], list[AgentMetrics], int, dict[str, list[dict[str, str]]]]:
    """
    Executa os sub-agentes especializados em paralelo com controle de concorrencia.
    Cada agente tem timeout individual. Falhas isoladas não afetam os demais.
    Retorna (issues, metrics, failed_count, pipeline_graph).

    `batch_collect=True` (Batch Inference, ver batch_collector.py): em vez de
    chamar o provider de verdade, cada `call_llm` dos agentes de análise grava
    a chamada e devolve "[]" -- os issues retornados aqui são descartáveis, só
    a lista de chamadas coletadas (que o chamador lê via `batch_collector`)
    importa. O CLASSIFICADOR roda normal (fora do escopo da coleta), porque a
    seleção de agente depende do resultado dele.
    """
    # Comprime o HTML para economizar tokens nos sub-agentes
    from backend.src.services.context_compressor import compress as compress_html
    html_content = compress_html(html_content)

    # Catalogo de agentes possiveis (lambdas adiam a criacao das coroutines)
    all_available_agents = {
        "perceiver": lambda: run_perceiver(html_content),
        "operability": lambda: run_operability(html_content),
        "understandability": lambda: run_understandability(html_content),
        "robustness": lambda: run_robustness(html_content),
        "aria_specialist": lambda: run_aria_specialist(html_content),
        "section508": lambda: run_section508(html_content),
        "css_analyzer": lambda: run_css_analyzer(html_content),
        "ajax_dynamic": lambda: run_ajax_dynamic(html_content),
        "cognitive": lambda: run_cognitive(html_content),
        "screen_reader": lambda: run_screen_reader(html_content),
        "mobile_a11y": lambda: run_mobile_a11y(html_content),
        "forms_a11y": lambda: run_forms_a11y(html_content),
        "widgets_a11y": lambda: run_widgets_a11y(html_content),
        "tables_data": lambda: run_tables_data(html_content),
        "link_checker": lambda: run_link_checker(html_content),
        "wcag_semantics": lambda: run_wcag_semantics(html_content),
        "compliance_audit": lambda: run_compliance_audit(html_content),
        "agentic_ai_ui": lambda: run_agentic_ai_ui_agent(html_content),
        "spatial_3d_xr": lambda: run_spatial_3d_xr_agent(html_content),
        "web_components": lambda: run_web_components_agent(html_content),
        "niche_domains": lambda: run_niche_domains_agent(html_content),
        "react_framework": lambda: run_react_framework(html_content),
        "angular_framework": lambda: run_angular_framework(html_content),
        "vue_framework": lambda: run_vue_framework(html_content),
        "svelte_framework": lambda: run_svelte_framework(html_content),
        "tailwind_css": lambda: run_tailwind_css(html_content),
    }
    if screenshot_base64:
        all_available_agents["visual_a11y"] = lambda: run_visual_a11y(html_content, screenshot_base64, focus_screenshots)

    classifier_success = True
    duration_classifier = 0.0
    routing_reasons: dict[str, str] = {}
    skipped_reasons: dict[str, str] = {}
    language = _detect_page_language(html_content)

    if only_agents:
        # Pula a classificação inteiramente para maior velocidade e evita restrições automáticas
        only_lower = {a.lower().replace("_", "").replace("-", "") for a in only_agents}
        agents = [
            (name, func) for name, func in all_available_agents.items()
            if name.lower().replace("_", "").replace("-", "") in only_lower
        ]
        routing_reasons = {
            name: "selecionado explicitamente via only_agents"
            for name, _ in agents
        }
        logger.info("[Orchestrator] Executando apenas os agentes selecionados via only_agents: %s", only_agents)
    else:
        # Fluxo normal: executa o classificador de frameworks E o classificador
        # de complexidade em paralelo (ambos tier "fast", independentes um do
        # outro) -- o segundo define, via ContextVar, o dial custo/qualidade
        # que todo `call_llm(model_tier="alto")` desta pipeline vai usar ao
        # resolver "Alto" (ver complexity_router.py). Decidido pelo modelo a
        # partir do conteúdo real, nunca por um limiar fixo de tamanho.
        loop = asyncio.get_running_loop()
        start_classifier = loop.time()
        chat_progress.emit({"type": "phase", "text": "Classificando tecnologias no HTML..."})
        classifier_result, _tradeoff = await asyncio.gather(
            run_classifier(html_content),
            classify_and_set_tradeoff(html_content),
        )
        duration_classifier = (loop.time() - start_classifier) * 1000
        classifier_success = classifier_result.success

        # Usa SUPPORTED_FRAMEWORKS como fonte unica de verdade (mesma usada pelo classifier.py).
        # Se o classificador falhar, não acionamos frameworks "no escuro"; o
        # fallback fica nos agentes base + condicionais por estrutura HTML.
        active_frameworks: set[str] = set()
        if classifier_result.success:
            active_frameworks = set(classifier_result.data.get("technologies", []))
            logger.info("[Orchestrator] Classificador detectou frameworks ativos: %s", active_frameworks)
        else:
            logger.warning(
                "[Orchestrator] Classificador falhou (%s). Continuando com base + condicionais por estrutura; frameworks pulados.",
                classifier_result.error,
            )

        routing_reasons.update(CORE_ANALYSIS_AGENTS)
        routing_reasons.update(_conditional_agent_reasons(html_content))

        if screenshot_base64:
            routing_reasons["visual_a11y"] = "screenshot fornecido; avaliacao visual solicitada pelo pipeline"

        for tech in sorted(active_frameworks):
            agent_name = FRAMEWORK_AGENT_BY_TECH.get(tech)
            if agent_name:
                routing_reasons[agent_name] = f"classificador detectou framework: {tech}"

        if classifier_result.success:
            inactive = set(SUPPORTED_FRAMEWORKS) - active_frameworks
            for tech in sorted(inactive):
                agent_name = FRAMEWORK_AGENT_BY_TECH.get(tech)
                if agent_name:
                    skipped_reasons[agent_name] = f"classificador não detectou framework: {tech}"
        else:
            for agent_name in FRAMEWORK_AGENT_BY_TECH.values():
                skipped_reasons[agent_name] = "classificador falhou; sem evidencia suficiente para framework especifico"

        for name in all_available_agents:
            if name not in routing_reasons and name not in skipped_reasons:
                skipped_reasons[name] = "sem evidencia estrutural suficiente para este agente condicional"

        agents = [
            (name, all_available_agents[name])
            for name in all_available_agents
            if name in routing_reasons
        ]

    logger.info(
        "[Orchestrator] Roteamento seletivo: lang=%s selecionados=%d [%s]",
        language,
        len(agents),
        ", ".join(name for name, _ in agents),
    )
    for name, reason in routing_reasons.items():
        logger.info("[Orchestrator] Agente selecionado: %s -- %s", name, reason)
    for name, reason in skipped_reasons.items():
        logger.info("[Orchestrator] Agente pulado: %s -- %s", name, reason)

    max_concurrent = get_settings().a11y_max_concurrent_agents
    logger.info("[Orchestrator] Disparando sub-agentes em paralelo (max_concurrent=%d, timeout=%.0fs)", max_concurrent, _get_agent_timeout())
    chat_progress.emit({"type": "phase", "text": "Analisando a página com especialistas em acessibilidade..."})

    semaphore = asyncio.Semaphore(max_concurrent)

    async def _run_with_semaphore(name: str, coro_factory) -> tuple[AgentResult, float]:
        async with semaphore:
            return await _timed(name, coro_factory)

    tuples: list[tuple[AgentResult, float]]
    if batch_collect:
        collect_token = batch_collector.enable()
        try:
            tuples = await asyncio.gather(
                *[_run_with_semaphore(name, func) for name, func in agents]
            )
        finally:
            batch_collector.disable(collect_token)
    else:
        tuples = await asyncio.gather(
            *[_run_with_semaphore(name, func) for name, func in agents]
        )

    all_issues: list[AccessibilityIssue] = []
    metrics: list[AgentMetrics] = []

    # Adiciona métrica do classificador se ele tiver rodado
    if not only_agents:
        metrics.append(
            AgentMetrics(
                agent="classifier",
                duration_ms=round(duration_classifier, 1),
                issues_found=0,
                success=classifier_success,
            )
        )

    for result, duration_ms in tuples:
        issues_found = len(result.data.get("issues", []))
        metrics.append(
            AgentMetrics(
                agent=result.agent,
                duration_ms=round(duration_ms, 1),
                issues_found=issues_found,
                success=result.success,
            )
        )
        all_issues.extend(_extract_issues(result))
        if not result.success:
            logger.warning(
                "[Orchestrator] Agente '%s' falhou (%.0fms): %s",
                result.agent,
                duration_ms,
                result.error,
            )
        else:
            logger.debug(
                "[Orchestrator] Agente '%s' concluido em %.0fms -- %d issues",
                result.agent,
                duration_ms,
                issues_found,
            )

    # Deduplicar (rodada 1)
    unique = _deduplicate_issues(all_issues)

    # Delegacao dinamica agente-a-agente (loop limitado -- ver
    # MAX_DELEGATION_ROUNDS): um coordenador le os achados atualizados e
    # decide, via LLM, se algum agente pulado deveria ser chamado -- real
    # orientado por evidencia de conteudo, nao regra fixa. Nao roda se nao
    # houver agentes pulados (ex.: only_agents) ou se nao houver issues pra
    # avaliar.
    delegation_edges: list[dict[str, str]] = []
    if not only_agents and skipped_reasons and unique:
        unique, delegation_metrics, delegation_edges = await _run_delegation_round(unique, skipped_reasons, all_available_agents)
        metrics.extend(delegation_metrics)

    pipeline_graph = _build_pipeline_graph(routing_reasons, skipped_reasons, delegation_edges)

    # Verificacao automatica de lacuna (gap-check): achados de baixa
    # confianca sao verificados contra fonte normativa real via Deep
    # Research, em vez de ficarem sem resolucao. Nao roda em batch_collect
    # (coleta de chamadas pra Batch Inference, nao analise de verdade).
    if not batch_collect:
        unique, gap_research_metric = await _run_gap_research_step(unique)
        if gap_research_metric is not None:
            metrics.append(gap_research_metric)

    # Guardrail de volume
    if len(unique) > MAX_ISSUES:
        logger.warning("[Orchestrator] Issues truncados de %d para %d", len(unique), MAX_ISSUES)
        unique = unique[:MAX_ISSUES]

    # i18n -- traduz criterion_pt e severity_pt em um único ponto
    unique = translate_issues(unique)
    logger.debug("[Orchestrator] i18n aplicado em %d issues", len(unique))

    # Expert Review
    if unique:
        chat_progress.emit({"type": "phase", "text": "Revisão especializada: removendo falsos positivos e repontuando..."})
        known_patterns = get_known_false_positive_patterns()
        pre_review = unique
        expert_result = await run_a11y_expert_reviewer(unique, known_false_positive_patterns=known_patterns)
        if expert_result.success:
            reviewed = [AccessibilityIssue(**i) for i in expert_result.data.get("issues", [])]
            removed = expert_result.data.get("removed_false_positives", 0)
            if removed > 0:
                logger.info(
                    "[Orchestrator] ExpertReviewer removeu %d falsos positivos (%d -> %d issues)",
                    removed,
                    len(unique),
                    len(reviewed),
                )
                # Memória de lições (ver lessons_store.py): grava os padroes
                # confirmados como falso positivo NESTA analise, pra
                # analises futuras (de OUTRAS paginas) se beneficiarem do
                # mesmo reforco que acabou de ser dado ao known_patterns
                # acima.
                reviewed_ids = {i.id for i in reviewed}
                for removed_issue in pre_review:
                    if removed_issue.id not in reviewed_ids:
                        record_false_positive_removal(
                            removed_issue.criterion, removed_issue.element, removed_issue.description,
                        )
            unique = reviewed
            metrics.append(
                AgentMetrics(
                    agent="a11y_expert_reviewer",
                    duration_ms=0.0,
                    issues_found=len(unique),
                    success=True,
                )
            )
        else:
            logger.warning(
                "[Orchestrator] ExpertReviewer falhou (%s) -- usando issues sem revisao",
                expert_result.error,
            )
            metrics.append(
                AgentMetrics(
                    agent="a11y_expert_reviewer",
                    duration_ms=0.0,
                    issues_found=len(unique),
                    success=False,
                )
            )

    # Verificacao deterministica de contraste
    chat_progress.emit({"type": "phase", "text": "Verificando contraste de cores..."})
    unique, contrast_removed = verify_contrast_issues(unique, source_html=html_content)
    if contrast_removed:
        logger.info(
            "[Orchestrator] ContrastVerifier removeu %d falso(s) positivo(s) de contraste",
            contrast_removed,
        )

    failed = sum(1 for m in metrics if not m.success)
    logger.info(
        "[Orchestrator] Pipeline concluido -- %d issues, %d/%d agentes OK",
        len(unique),
        len(metrics) - failed,
        len(metrics),
    )

    if failed > 0:
        first_failed = next((m for m in metrics if not m.success), None)
        logger.warning(
            "[Orchestrator] %d/%d agentes falharam. Exemplo: agente='%s'",
            failed,
            len(metrics),
            first_failed.agent if first_failed else "?",
        )

    return unique, metrics, failed, pipeline_graph


async def orchestrate(
    html_content: str,
    task_type: TaskType,
    *,
    target: str = "",
    product_name: str = "Produto Avaliado",
    screenshot_base64: str | None = None,
    focus_screenshots: list[str] | None = None,
    only_agents: list[str] | None = None,
    batch_collect: bool = False,
) -> AgentResult:
    """
    Pipeline principal com sub-agentes especializados.

    Fluxo ReAct:
      Reason  -> escolhe o que fazer baseado em task_type
      Act     -> executa os sub-agentes corretos
      Observe -> valida resultado antes de passar ao proximo passo

    target/product_name: usados apenas pelos entregaveis VPAT e TESTS.
    `batch_collect`: ver docstring de `_run_analysis_pipeline` (Batch Inference).
    """
    logger.info("[Orchestrator] Iniciando pipeline task_type=%s", task_type)

    # STEP 1: Análise especializada em paralelo (sempre executada)
    issues, metrics, failed_count, pipeline_graph = await _run_analysis_pipeline(
        html_content,
        screenshot_base64=screenshot_base64,
        focus_screenshots=focus_screenshots,
        only_agents=only_agents,
        batch_collect=batch_collect,
    )
    total_agents = len(metrics)

    # Se TODOS os agentes falharam, retornar success=False com detalhes dos metrics
    if total_agents > 0 and failed_count == total_agents:
        logger.warning(
            "[Orchestrator] Todos os %d agentes falharam -- retornando resultado vazio",
            total_agents,
        )
        return AgentResult(
            agent="orchestrator",
            success=False,
            error=f"Todos os {total_agents} agentes falharam -- nenhum resultado disponivel.",
            data={
                "issues": [],
                "agent_metrics": [m.model_dump() for m in metrics],
            },
        )

    if task_type == TaskType.ANALYZE:
        # Aviso parcial: alguns agentes falharam mas outros tiveram sucesso
        partial_warning: str | None = None
        if failed_count > 0:
            partial_warning = f"{failed_count}/{total_agents} agentes falharam -- resultado pode estar incompleto."
            logger.warning("[Orchestrator] Análise parcial: %s", partial_warning)

        logger.info("[Orchestrator] Pipeline ANALYZE concluido")
        result_data: dict = {
            "issues": [i.model_dump() for i in issues],
            "agent_metrics": [m.model_dump() for m in metrics],
            "pipeline_graph": pipeline_graph,
        }
        if partial_warning:
            result_data["warning"] = partial_warning
        return AgentResult(
            agent="orchestrator",
            success=True,
            data=result_data,
        )

    # STEP 2: Fix (se solicitado)
    if task_type == TaskType.FIX:
        fix_result = await run_fixer(html_content, issues)
        if not fix_result.success:
            logger.error("[Orchestrator] FixerAgent falhou: %s", fix_result.error)
        return fix_result

    # Entregaveis de QA/agile derivados dos issues (so precisam da análise).
    if task_type == TaskType.VPAT:
        return await run_vpat_reporter(issues, target=target, product_name=product_name)

    if task_type == TaskType.TESTS:
        return await run_test_generator(issues, target=target)

    # STEP 3: Checklist
    checklist_result = await run_checklist(issues, html_content)
    if not checklist_result.success:
        logger.error("[Orchestrator] ChecklistAgent falhou: %s", checklist_result.error)
        return checklist_result

    checklist_items = _extract_checklist(checklist_result)

    if task_type == TaskType.CHECKLIST:
        logger.info("[Orchestrator] Pipeline CHECKLIST concluido")
        return checklist_result

    # STEP 4: Report completo
    report_result = await run_reporter(issues, checklist_items)
    logger.info("[Orchestrator] Pipeline REPORT concluido")
    return report_result
