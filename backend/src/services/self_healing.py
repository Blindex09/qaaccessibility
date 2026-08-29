import logging

from playwright.async_api import async_playwright

from backend.src.shared.models import AccessibilityIssue, Guideline, Severity

logger = logging.getLogger(__name__)

_PLANNER_SYSTEM_PROMPT = """
You are an accessibility remediation strategist. You receive a list of WCAG
issues found on a page and decide the ORDER and GROUPING in which they should
be fixed -- never a fixed priority list, always reasoned from the actual
issues given: some fixes cascade (e.g. restructuring headings can resolve
landmark issues found separately), some are independent and safe to batch,
and some are risky to combine (e.g. two fixes touching the same element).

Return ONLY a JSON object:
{
  "strategy": "<one short paragraph: the overall approach and why>",
  "ordered_groups": [
    {"issue_ids": ["id1", "id2"], "rationale": "<why these together, why this order>"}
  ]
}
No markdown fences, no prose outside the JSON.
""".strip()


async def node_plan(issues: list[AccessibilityIssue]) -> dict:
    """Planning explícito antes de agir: decide ORDEM/AGRUPAMENTO de correção a
    partir dos issues reais desta página, nunca de uma lista de prioridade fixa.

    Diferente do prompt do fixer (que já embute uma ordem de prioridade
    genérica e sempre igual -- "accessible names, keyboard, focus, semantics"),
    este passo roda ANTES e é específico do conjunto de issues em mãos: pode
    decidir agrupar dois issues que se resolvem pela mesma mudança estrutural,
    ou isolar um issue arriscado de ser combinado com outro no mesmo elemento.

    Falha do planejador (rede, JSON malformado) nunca bloqueia o self-healing
    -- devolve um plano vazio e o fixer segue com sua própria heurística padrão.
    """
    if not issues:
        return {"strategy": "", "ordered_groups": []}
    try:
        from backend.src.services.llm_client import call_llm, extract_json_object

        issues_summary = "\n".join(
            f"- id={i.id} criterion={i.criterion} severity={i.severity.value} element={i.element[:80]}"
            for i in issues
        )
        raw = await call_llm(
            system_prompt=_PLANNER_SYSTEM_PROMPT,
            user_prompt=f"Plan the remediation order for these issues:\n\n{issues_summary}",
            temperature=0.1,
            max_tokens=800,
            agent_label="self_healing_planner",
            model_tier="fast",
        )
        plan = extract_json_object(raw)
        logger.info(
            "[SelfHealing Graph] Plano: %s (%d grupos)",
            plan.get("strategy", "")[:120], len(plan.get("ordered_groups", [])),
        )
        return plan
    except Exception as exc:
        logger.warning("[SelfHealing Graph] Planejamento falhou (%s) -- fixer segue sem plano explícito", exc)
        return {"strategy": "", "ordered_groups": []}


def _plan_to_instruction(plan: dict) -> str:
    if not plan.get("strategy") and not plan.get("ordered_groups"):
        return ""
    lines = [f"REMEDIATION PLAN (decided from the actual issues, follow this order):\n{plan.get('strategy', '')}"]
    for idx, group in enumerate(plan.get("ordered_groups", []), start=1):
        ids = ", ".join(group.get("issue_ids", []))
        lines.append(f"{idx}. Issues [{ids}]: {group.get('rationale', '')}")
    return "\n".join(lines)

# Mapeamento de severidade do axe-core para o nosso enum Severity
_SEVERITY_MAP = {
    "critical": Severity.CRITICAL,
    "serious": Severity.HIGH,
    "moderate": Severity.MEDIUM,
    "minor": Severity.LOW,
}


def axe_violations_to_accessibility_issues(violations: list[dict]) -> list[AccessibilityIssue]:
    """Converte violações axe-core reais (formato bruto, com `nodes`) para o
    formato interno AccessibilityIssue -- uma issue por elemento afetado,
    igual um leitor de tela real encontraria cada um separadamente. Extraído
    de verify_html_with_axe() para ser reaproveitado por qualquer runner que
    produza violações axe-core reais (nuvem, Cypress local, Selenium local),
    não só o self-healing -- ver run_remote_test_tool em chat_tools.py."""
    issues: list[AccessibilityIssue] = []
    for violation in violations:
        rule_id = violation.get("id") or "unknown-rule"
        description = violation.get("description")
        help_text = violation.get("help")
        help_url = violation.get("helpUrl") or violation.get("help_url")
        severity = _SEVERITY_MAP.get(violation.get("impact") or "", Severity.MEDIUM)

        for idx, node in enumerate(violation.get("nodes", [])):
            target = " ".join(node.get("target", []))
            failure_summary = node.get("failureSummary", "")

            issues.append(
                AccessibilityIssue(
                    id=f"axe-{rule_id}-{idx}",
                    guideline=Guideline.WCAG_2_2,
                    criterion=rule_id,
                    severity=severity,
                    element=target or "unknown",
                    description=f"{help_text}. {description}. Detalhes: {failure_summary}",
                    suggestion=f"Ajuste o elemento HTML para passar no criterio '{rule_id}'. Documentacao: {help_url}",
                )
            )
    return issues


async def verify_html_with_axe(html_content: str) -> list[AccessibilityIssue]:
    """
    Executa o axe-core via Playwright CDP (remoto na nuvem) contra o HTML fornecido
    e retorna a lista de violações.
    """
    from backend.src.config.settings import get_settings
    settings = get_settings()
    ws_url = getattr(settings, "browserless_ws_url", None)
    if not ws_url:
        raise ValueError("Configuração ausente: BROWSERLESS_WS_URL e obrigatória para validação axe-core.")

    logger.info("[SelfHealing] Iniciando verificacao com axe-core no Playwright CDP remoto...")

    async with async_playwright() as pw:
        browser = await pw.chromium.connect_over_cdp(ws_url)
        context = await browser.new_context(viewport={"width": 1280, "height": 800})
        page = await context.new_page()

        try:
            # Seta o HTML diretamente na página, super rapido
            await page.set_content(html_content)

            # Injeta axe-core da CDN cdnjs
            try:
                await page.add_script_tag(url="https://cdnjs.cloudflare.com/ajax/libs/axe-core/4.9.1/axe.min.js")
            except Exception as exc:
                logger.error("[SelfHealing] Falha ao injetar axe-core via CDN: %s.", exc)
                raise RuntimeError("Falha ao carregar script axe-core da CDN.") from exc

            # Executa axe-core
            results = await page.evaluate("() => axe.run()")
            violations = results.get("violations", [])
            logger.info("[SelfHealing] Verificacao concluida. %d violacoes encontradas.", len(violations))

            return axe_violations_to_accessibility_issues(violations)

        finally:
            await context.close()
            await browser.close()



# Numero de rodadas consecutivas com a MESMA assinatura de erro remanescente
# (mesmo (criterion, element) que a tentativa anterior) antes de considerar
# "loop confirmado e sem saida" e parar de insistir -- exige repeticao real,
# nao so 1 coincidencia, pra nao cortar tentativas que ainda tinham chance
# real de resolver com estado limpo (ver conceitos-ia-para-desenvolvimento-de-
# software.md, secao 7 "Deteccao de loop").
_LOOP_REPEAT_THRESHOLD = 2


def _remaining_issues_signature(issues: list[AccessibilityIssue]) -> frozenset[tuple[str, str]]:
    """Assinatura do conjunto de violacoes remanescentes: (criterio, elemento).
    Duas auditorias com a mesma assinatura significam que a tentativa de fix
    anterior nao resolveu (ou reintroduziu) exatamente os mesmos problemas --
    diferente de so contar tentativas, isso detecta quando insistir do mesmo
    jeito nao vai adiantar."""
    return frozenset((i.criterion, i.element) for i in issues)


class SelfHealingState:
    def __init__(self, html: str, issues: list[AccessibilityIssue], max_retries: int):
        self.html = html
        self.issues = issues
        self.max_retries = max_retries
        self.attempts = 0
        self.changes: list[str] = []
        self.enriched_issues: list[dict] = []
        self.status = "init"
        self.history: list[dict] = []  # Rastreador de memória causal
        self.audit_signatures: list[frozenset[tuple[str, str]]] = []
        self.consecutive_repeats = 0


async def node_fix(state: SelfHealingState) -> None:
    from backend.src.agents.fixer.fixer import run_fixer

    state.attempts += 1
    custom_inst = "CORREÇÃO AUTOCICATRIZANTE: Corrija os erros apontados pelo axe-core mantendo a estrutura geral."
    if state.history:
        causal_history = "\n\nCausal memory of previous attempts and outcomes:"
        for h in state.history:
            attempt_num = h.get("attempt")
            attempt_changes = h.get("changes", [])
            remaining = h.get("remaining_issues", [])
            causal_history += f"\n- Attempt {attempt_num} applied changes: {attempt_changes}"
            if remaining:
                causal_history += f"\n  Outstanding issues after those changes: {remaining}"
        custom_inst += causal_history

    logger.warning(
        "[SelfHealing Graph] Tentativa %d: Encontradas %d violacoes remanescentes. Rodando fixer com memoria causal...",
        state.attempts,
        len(state.issues),
    )

    retry_result = await run_fixer(
        state.html,
        state.issues,
        custom_instruction=custom_inst,
        model_tier="alto",  # Escala para modelo flagship/reasoning (alto) nas tentativas subsequentes
    )
    if not retry_result.success:
        state.status = "failed"
        logger.error("[SelfHealing Graph] Tentativa %d falhou ao chamar o fixer: %s", state.attempts, retry_result.error)
        return

    state.html = retry_result.data.get("fixed_html", state.html)
    changes = retry_result.data.get("changes_summary", [])
    state.changes.extend([f"[Auto-cicatrizacao T{state.attempts-1}] {c}" for c in changes])
    state.enriched_issues.extend(retry_result.data.get("enriched_issues", []))
    state.status = "fixed"

    state.history.append({
        "attempt": state.attempts,
        "changes": list(changes),
    })


async def node_audit(state: SelfHealingState) -> None:
    try:
        remaining_violations = await verify_html_with_axe(state.html)
        if not remaining_violations:
            state.status = "success"
            logger.info("[SelfHealing Graph] Sucesso! Nenhuma violacao restante na tentativa %d.", state.attempts)
            return

        signature = _remaining_issues_signature(remaining_violations)
        if state.audit_signatures and signature == state.audit_signatures[-1]:
            state.consecutive_repeats += 1
        else:
            state.consecutive_repeats = 0
        state.audit_signatures.append(signature)

        state.issues = remaining_violations
        if state.history:
            state.history[-1]["remaining_issues"] = [
                f"Criterion: {i.criterion}, Element: {i.element}, Error: {i.description}"
                for i in remaining_violations
            ]

        if state.consecutive_repeats >= _LOOP_REPEAT_THRESHOLD:
            state.status = "stuck"
            logger.warning(
                "[SelfHealing Graph] Loop detectado: as mesmas %d violacoes persistem por %d "
                "tentativas consecutivas sem mudanca. Parando de insistir e retornando a ultima "
                "correcao aplicada em vez de esgotar o orcamento de tentativas sem progresso.",
                len(remaining_violations),
                state.consecutive_repeats + 1,
            )
        else:
            state.status = "needs_fix"
    except Exception as exc:
        state.status = "failed"
        logger.error("[SelfHealing Graph] Excecao na verificacao da tentativa %d: %s", state.attempts + 1, exc)


async def run_self_healing_loop(
    html_content: str,
    initial_issues: list[AccessibilityIssue],
    approved_issue_ids: list[str] | None = None,
    custom_instruction: str | None = None,
    max_retries: int = 3,
) -> tuple[str, list[str], list[dict]]:
    """
    Loop autocicatrizante (self-healing) estruturado como um Grafo de Estado Cíclico:
    - Planning: decide ordem/agrupamento de correção a partir dos issues reais (node_plan).
    - Estado: html, issues, attempts, changes, enriched_issues, status.
    - Nós: fix (aplica correções via LLM) e audit (valida via Playwright+Axe).
    - Roteador de transições baseadas em estado e limites de tentativas.
    """
    from backend.src.agents.fixer.fixer import run_fixer

    logger.info("[SelfHealing Graph] Iniciando loop autocicatrizante com Grafo de Estado. Limite: %d", max_retries)

    state = SelfHealingState(html_content, initial_issues, max_retries)

    # Planning explícito ANTES de agir: decide a partir dos issues reais desta
    # página, não de uma ordem fixa embutida no prompt do fixer. Some-se ao
    # custom_instruction do chamador em vez de substituí-lo.
    plan = await node_plan(state.issues)
    plan_instruction = _plan_to_instruction(plan)
    combined_instruction = (
        f"{custom_instruction}\n\n{plan_instruction}" if custom_instruction and plan_instruction
        else plan_instruction or custom_instruction
    )

    # Primeira tentativa: aplica correções originais com modelo econômico/rápido (fast)
    state.attempts += 1
    fix_result = await run_fixer(
        state.html,
        state.issues,
        approved_issue_ids=approved_issue_ids,
        custom_instruction=combined_instruction,
        model_tier="fast",
    )
    if not fix_result.success:
        logger.error("[SelfHealing Graph] Primeira tentativa de correção falhou: %s", fix_result.error)
        raise RuntimeError(f"Primeira tentativa de correção falhou: {fix_result.error}")

    state.html = fix_result.data.get("fixed_html", state.html)
    changes = fix_result.data.get("changes_summary", [])
    state.changes.extend(changes)
    state.enriched_issues.extend(fix_result.data.get("enriched_issues", []))
    state.status = "fixed"

    state.history.append({
        "attempt": state.attempts,
        "changes": list(changes),
    })

    # Transições cíclicas do grafo de estados
    while state.attempts < state.max_retries + 1:
        if state.status == "fixed":
            # Transiciona para nó de auditoria
            await node_audit(state)
        elif state.status == "needs_fix":
            # Transiciona para nó de correção
            await node_fix(state)
        elif state.status in ("success", "failed", "stuck"):
            break

    if state.status == "needs_fix":
        logger.warning("[SelfHealing Graph] Loop finalizado pelo limite de tentativas (%d). Retornando última correção.", max_retries)

    return state.html, state.changes, state.enriched_issues
