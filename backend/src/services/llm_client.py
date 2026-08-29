import asyncio
import json
import logging
import re
import time
import uuid
from collections.abc import Callable
from typing import Any, TypeVar

from pydantic import ValidationError

import backend.src.services.a11y_domain_tools  # noqa: F401 -- side-effect import, registra o toolset de dominio (a11y_tools) no tools/registry.py
from backend.src.config.settings import get_settings
from backend.src.services import agent_hooks, batch_collector
from backend.src.services.response_cache import (
    get_cached_response,
    make_cache_key,
    set_cached_response,
)
from run_agent import AIAgent

T = TypeVar("T")

logger = logging.getLogger(__name__)

_MD_FENCE_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)

# Contrato de saida dos 25 agentes de analise (AccessibilityIssue, campos que o
# LLM de fato preenche -- exclui criterion_pt/severity_pt/fixed_element_html/url,
# que sao preenchidos por estagios posteriores do pipeline, nao pelo modelo).
# "Strict mode" da OpenAI/Anthropic exige additionalProperties=false + todo
# campo em "required" (opcionais viram tipo nullable) -- ver
# ISSUES_RESPONSE_SCHEMA abaixo. Wrapper em objeto ("issues": [...]) porque a
# Responses API da OpenAI exige schema raiz do tipo "object", nao "array";
# extract_json_array ja sabia devolver o primeiro valor-lista de um dict, essa
# forma sempre foi um caminho suportado no parsing.
_ISSUE_SCHEMA_PROPERTIES: dict[str, dict[str, Any]] = {
    "id": {"type": "string"},
    "guideline": {"type": "string", "enum": ["WCAG 2.2", "WAI-ARIA", "ADA/Section 508"]},
    "criterion": {"type": "string"},
    "severity": {"type": "string", "enum": ["critical", "high", "medium", "low"]},
    # Confidence signal: confianca de deteccao, eixo distinto de severity
    # (impacto SE for real). Opcional/nullable -- agentes/respostas antigas
    # nao preenchem ainda.
    "confidence": {"type": ["string", "null"], "enum": ["high", "medium", "low", None]},
    "level": {"type": ["string", "null"]},
    "element": {"type": "string"},
    "description": {"type": "string"},
    "description_technical": {"type": ["string", "null"]},
    "why_simple": {"type": ["string", "null"]},
    "why_technical": {"type": ["string", "null"]},
    "suggestion": {"type": "string"},
    "suggestion_technical": {"type": ["string", "null"]},
    "wcag_url": {"type": ["string", "null"]},
}

ISSUES_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "issues": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": _ISSUE_SCHEMA_PROPERTIES,
                "required": list(_ISSUE_SCHEMA_PROPERTIES.keys()),
                "additionalProperties": False,
            },
        },
    },
    "required": ["issues"],
    "additionalProperties": False,
}


def _reasoning_effort_for_tradeoff(tradeoff: int) -> str:
    """Traduz o dial de tradeoff custo/qualidade (0-10, decidido pelo
    classificador real de complexidade em complexity_router.py) pro nível de
    esforço de raciocínio (`reasoning_effort`) da chamada.

    Achado real (pesquisa 2026-08-11, ARES/Claude 4.6 effort routing):
    escolher o MODELO certo pela complexidade da tarefa (já implementado em
    model_router.py) é só metade do roteamento adaptativo -- a outra metade é
    fazer esse mesmo modelo "pensar mais ou menos" conforme a tarefa. Antes
    desta função, TODA chamada do projeto desligava o raciocínio
    incondicionalmente (`disable_reasoning = True` fixo em `call_llm`),
    mesmo em tarefas que o próprio classificador de complexidade já tinha
    marcado como precisando de mais cuidado -- nenhuma tarefa nunca recebia
    esforço extra de raciocínio, só o modelo mudava. Mercado reporta 40-60%
    de economia adicional com esse roteamento por esforço, em cima da
    economia só de troca de modelo.

    Extremos preservam o comportamento histórico: tradeoff>=8 (favorece
    custo ao máximo) continua desligando raciocínio por completo -- é
    exatamente o "none" fixo que já existia antes desta mudança, agora só
    aplicado quando a tarefa realmente pede velocidade/custo máximos, não
    sempre.
    """
    if tradeoff >= 8:
        return "none"
    if tradeoff >= 6:
        return "low"
    if tradeoff >= 3:
        return "medium"
    return "high"


def _provider_rejected_parameter(error: str, parameter: str) -> bool:
    """True quando o provider recusou um parametro especifico do request (HTTP 400).

    Deteccao tecnica de formato de erro (nome do parametro + marcador de "nao
    suportado" na mensagem), sem vocabulario de dominio -- so cobre o contrato
    de API dos provedores OpenAI-compativeis. Permite enviar controles
    modernos (ex.: temperature, reasoning_effort) e cair fora deles quando
    algum provider ainda nao aceitar o campo.
    """
    if not parameter:
        return False
    error_lower = str(error or "").lower()
    parameter_lower = parameter.lower()
    param_variants = [parameter_lower, parameter_lower.replace("_", ".")]
    if "_" in parameter_lower:
        param_variants.append(parameter_lower.split("_")[0])

    matches_param = any(v in error_lower for v in param_variants)
    matches_marker = any(
        marker in error_lower
        for marker in (
            "unsupported parameter",
            "unsupported value",
            "unsupported_value",
            "not supported",
            "does not support",
            "unknown parameter",
            "unrecognized parameter",
            "invalid parameter",
            "invalid_request_error",
        )
    )
    return matches_param and matches_marker


def _provider_rejected_temperature(error: str) -> bool:
    """True quando o provider recusou o parametro 'temperature' (HTTP 400)."""
    return _provider_rejected_parameter(error, "temperature")


def _strip_markdown_fences(text: str) -> str:
    """Remove markdown code fences that LLMs sometimes wrap around JSON output."""
    if not text:
        return ""
    t = text.strip()
    # Padrões para limpar cercas de código (```, ''', """)
    t = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", t, flags=re.MULTILINE)
    t = re.sub(r"```$", "", t, flags=re.MULTILINE)
    t = re.sub(r"^'''\s*", "", t, flags=re.MULTILINE)
    t = re.sub(r"'''$", "", t, flags=re.MULTILINE)
    t = re.sub(r'^"""\s*', "", t, flags=re.MULTILINE)
    t = re.sub(r'"""$', "", t, flags=re.MULTILINE)
    # Remove marcas residuais
    t = t.replace("```", "").replace("'''", "").replace('"""', "")
    return t.strip()


def _is_json_truncated(text: str) -> bool:
    """True quando o texto parece ser um JSON array/objeto truncado."""
    cleaned = _strip_markdown_fences(text).strip()
    if not cleaned:
        return True
    # Array aberto mas não fechado
    if cleaned.startswith("[") and not cleaned.rstrip().endswith("]"):
        return True
    # Objeto aberto mas não fechado
    if cleaned.startswith("{") and not cleaned.rstrip().endswith("}"):
        return True
    # Array/objeto com conteúdo mas sem fechamento completo (heuristica: ultimo char não eh ]})
    if cleaned.startswith("[") or cleaned.startswith("{"):
        last_char = cleaned.rstrip()[-1] if cleaned.rstrip() else ""
        if last_char not in ("]", "}"):
            return True
    return False


def _extract_partial_json_array(text: str) -> list | None:
    """
    Tenta extrair um JSON array PARCIAL de texto truncado.
    Remove a ultima entrada incompleta e fecha o array.
    Retorna None se não conseguir.
    """
    cleaned = _strip_markdown_fences(text).strip()
    if not cleaned.startswith("["):
        return None

    # Tenta achar o ultimo objeto completo antes do corte
    # Procura por '},' ou '}]' ou '}\n' e pega ate la
    # Estrategia: procura do fim para o inicio por um objeto completo
    try:
        # Remove o texto apos o ultimo '}' valido
        last_brace = cleaned.rfind("}")
        if last_brace == -1:
            return None

        # Pega tudo ate o ultimo '}' + fecha o array
        partial = cleaned[: last_brace + 1]
        # Se termina com '},' ou '}' sem array, fecha com ']'
        if partial.rstrip().endswith(","):
            partial = partial.rstrip()[:-1]  # remove trailing comma
        partial = partial.rstrip() + "]"

        parsed = json.loads(partial)
        if isinstance(parsed, list):
            return parsed
    except (json.JSONDecodeError, IndexError):
        pass

    return None


def extract_json_array(raw: str) -> list:
    """
    Robustly extract a JSON array from raw LLM output.
    Handles: markdown fences, leading/trailing prose, partial output.
    Raises ValueError if no valid array can be extracted.
    """
    cleaned = _strip_markdown_fences(raw)
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, list):
            # Achado real (2026-08-10): o modelo às vezes envolve o array
            # esperado num wrapper redundante -- [{"issues": []}] em vez de []
            # -- sobretudo ao expressar "nenhum problema encontrado". Sem isso,
            # o item único (o dict wrapper) era desempacotado como se fosse um
            # item real do array (AccessibilityIssue(**{"issues": []}) falha
            # com "Field required" em todos os campos). Desembrulha só o
            # padrão bem específico (1 item, 1 chave, valor é lista) -- não
            # colide com um array real de issues (vários dicts multi-campo).
            if (
                len(parsed) == 1
                and isinstance(parsed[0], dict)
                and len(parsed[0]) == 1
                and isinstance(next(iter(parsed[0].values())), list)
            ):
                return next(iter(parsed[0].values()))
            return parsed
        if isinstance(parsed, dict):
            for val in parsed.values():
                if isinstance(val, list):
                    return val
    except json.JSONDecodeError:
        pass

    # Tenta extrair array parcial (truncado)
    partial = _extract_partial_json_array(cleaned)
    if partial is not None:
        return partial

    start = cleaned.find("[")
    end = cleaned.rfind("]")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError:
            pass

    raise ValueError(f"No valid JSON array found in LLM output: {raw[:200]!r}")


def extract_json_object(raw: str) -> dict:
    """
    Robustly extract a JSON object from raw LLM output.
    Handles: markdown fences, leading/trailing prose.
    Raises ValueError if no valid object can be extracted.
    """
    cleaned = _strip_markdown_fences(raw)
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            result = json.loads(cleaned[start : end + 1])
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError:
            pass

    raise ValueError(f"No valid JSON object found in LLM output: {raw[:200]!r}")


async def call_llm(
    system_prompt: str,
    user_prompt: str,
    *,
    temperature: float = 0.2,
    max_tokens: int = 16384,
    request_id: str = "",
    agent_label: str = "",
    toolsets: list[str] | None = None,
    max_iterations: int = 1,
    model_tier: str = "alto",
    response_schema: dict[str, Any] | None = None,
) -> str:
    """
    Executa um especialista de acessibilidade como leaf subagent do AIAgent.

    Cada chamada cria um AIAgent filho seguindo o padrão canonico de subagente
    do AIAgent (ver tools/delegate_tool.py): contexto isolado (task_id proprio),
    system prompt focado via ephemeral_system_prompt, e toolset restrito.

    enabled_toolsets=[] -> leaf classificador SEM tools: o schema de ferramentas
    não e enviado ao modelo (economia de tokens) e o subagente não pode emitir
    tool-calls espurias em vez do JSON esperado. Tools de dominio (Playwright,
    XLSX) serao expostas numa fase posterior, elevando max_iterations.

    AIAgent cuida de: provider routing, failover e compressao de contexto. Retry
    com backoff exponencial em erro transitorio (conexao/timeout/429/5xx) vem
    dos SDKs oficiais por padrao -- nao duplicado aqui de proposito (ver nota
    em config/settings.py::a11y_max_concurrent_agents).
    """
    settings = get_settings()
    log_ctx = f" request_id={request_id}" if request_id else ""
    label = agent_label or "leaf"
    # enabled_toolsets=[] -> leaf sem tools; lista não-vazia -> subagente com
    # tools de dominio (precisa de max_iterations>1 para o loop tool->resposta).
    enabled_toolsets = toolsets if toolsets is not None else []

    api_key = settings.llm_api_key
    base_url = settings.llm_base_url or None

    # Import com resolucao de provider concreto (ex.: agentic/auto -> openai, anthropic, etc.)
    from backend.src.services.model_router import resolve_model_and_provider
    from backend.src.shared.error_formatter import format_human_friendly_error

    # user_prompt e list quando multimodal (texto + image_url blocks, ver
    # visual_a11y.py) -- sinaliza pro roteamento que "Alto" precisa de um
    # modelo com suporte a imagem, em vez de resolver qualquer flagship e
    # falhar com 400 "this model does not support image input" rio abaixo.
    needs_vision = isinstance(user_prompt, list)

    # Mesmo tradeoff que decide o modelo/provider (model_router.py) decide
    # agora também o esforço de raciocínio -- tier "fast"/classifier usa a
    # mesma regra de tradeoff=9 já aplicada em resolve_model() pra manter os
    # dois eixos (modelo e esforço) consistentes entre si.
    label_lower = (agent_label or "").lower().strip()
    if model_tier == "fast" or label_lower == "classifier":
        effort_tradeoff = 9
    else:
        from backend.src.services.complexity_router import get_current_tradeoff

        effort_tradeoff = get_current_tradeoff()
    initial_reasoning_effort = _reasoning_effort_for_tradeoff(effort_tradeoff)
    logger.info(
        "[Effort] agent_label=%s tradeoff=%d -> reasoning_effort=%s",
        label_lower or "leaf",
        effort_tradeoff,
        initial_reasoning_effort,
    )

    provider, model = resolve_model_and_provider(
        settings.llm_provider,
        settings.llm_model,
        tier=model_tier,
        agent_label=label,
        needs_vision=needs_vision,
        needs_structured_outputs=response_schema is not None,
    )
    if needs_vision and not model:
        raise Exception(
            "Nenhum modelo com suporte a analise de imagem esta disponivel para o "
            "provider/modo atual. A analise visual sera pulada; os demais agentes "
            "de acessibilidade nao sao afetados."
        )
    if response_schema is not None and not model:
        raise Exception(
            "Ollama Cloud não suporta Structured Outputs nativos e nenhum "
            "fallback OpenCode Go/GPT 5.6 Luna está configurado. Configure "
            "OPENCODE_GO_API_KEY para continuar com uma resposta estruturada."
        )

    # Candidatos a tentar, em ordem. Por padrao, so o par ja resolvido. Quando o
    # roteamento caiu no fallback de Structured Outputs (provider="opencode-go"),
    # troca por toda a cadeia verificada (ver docs/auditoria-prompt-caching-
    # structured-output-2026-08-26.md): se o primeiro modelo estiver fora do ar,
    # o proximo da cadeia e tentado automaticamente antes de desistir -- nunca
    # fica sem garantia de JSON so porque um unico modelo falhou.
    candidates: list[tuple[str, str, str | None, str | None]] = [(provider, model, api_key, base_url)]
    if provider == "opencode-go" and response_schema is not None:
        from backend.src.services.model_router import resolve_structured_output_chain

        chain_models = resolve_structured_output_chain()
        if chain_models:
            import os

            chain_api_key = os.getenv("OPENCODE_GO_API_KEY") or os.getenv("OPENCODE_API_KEY")
            chain_base_url = base_url or "https://opencode.ai/zen/go/v1"
            candidates = [("opencode-go", m, chain_api_key, chain_base_url) for m in chain_models]

    fallback_model = settings.build_fallback_model()

    async def _attempt(cand_provider: str, cand_model: str, cand_api_key: str | None, cand_base_url: str | None) -> str:
        cand_task_id = f"a11y-{label}-{uuid.uuid4().hex[:8]}"
        call_start = time.monotonic()

        def _record_outcome(success: bool, error: str = "") -> None:
            # Telemetria real de confiabilidade/latencia -- alimenta o roteamento
            # "Alto" (ver ollama_cloud_adapter.score_ollama_cloud_model). So conta
            # chamadas que de fato bateram no provider (nunca cache hit nem o
            # sentinel "[]" do batch collector, tratados antes deste ponto).
            from backend.src.services.model_reliability import record_call_outcome

            duration_ms = (time.monotonic() - call_start) * 1000
            record_call_outcome(cand_provider, cand_model, success, duration_ms)
            # Hooks plugáveis (agent_hooks.py) -- observadores externos (telemetria
            # custom, auditoria, testes) podem se registrar sem tocar neste arquivo.
            agent_hooks.fire(
                agent_hooks.POST_LLM_CALL, cand_provider, cand_model, cand_task_id, label, success, duration_ms
            )
            if not success:
                agent_hooks.fire(agent_hooks.ON_ERROR, cand_provider, cand_model, cand_task_id, label, error)

        agent_hooks.fire(agent_hooks.PRE_LLM_CALL, cand_provider, cand_model, cand_task_id, label)

        logger.info(
            "[AIAgent]%s subagent=%s model=%s provider=%s base_url=%s fallback=%s",
            log_ctx,
            cand_task_id,
            cand_model,
            cand_provider,
            cand_base_url,
            bool(fallback_model),
        )

        async def _run(
            apply_temperature: bool, reasoning_effort: str | None, cur_system_prompt: str, cur_user_prompt: str
        ) -> dict:
            eff_sys = cur_system_prompt
            eff_schema = response_schema
            if cand_provider in ("ollama-cloud", "ollama_cloud"):
                from backend.src.services.ollama_cloud_adapter import adapt_ollama_cloud_request

                eff_sys, eff_schema = adapt_ollama_cloud_request(cur_system_prompt, response_schema)

            request_overrides: dict[str, Any] = {}
            if apply_temperature:
                request_overrides["temperature"] = temperature
            if reasoning_effort is not None:
                request_overrides["reasoning_effort"] = reasoning_effort
            agent = AIAgent(
                model=cand_model,
                provider=cand_provider,
                api_key=cand_api_key,
                base_url=cand_base_url,
                max_iterations=max_iterations,
                quiet_mode=True,
                max_tokens=max_tokens,
                request_overrides=request_overrides,
                fallback_model=fallback_model,
                ephemeral_system_prompt=eff_sys,
                enabled_toolsets=enabled_toolsets,
                log_prefix=f"[a11y:{label}]",
                response_schema=eff_schema,
            )
            return await asyncio.to_thread(
                agent.run_conversation,
                user_message=cur_user_prompt,
                task_id=cand_task_id,
            )

        apply_temperature = True
        reasoning_effort: str | None = initial_reasoning_effort
        cur_system_prompt = system_prompt
        cur_user_prompt = user_prompt
        res = await _run(apply_temperature, reasoning_effort, cur_system_prompt, cur_user_prompt)

        # Self-heal: se o provider recusou 'temperature' (modelo de reasoning), refaz
        # UMA vez sem ela, deixando o provider aplicar seu proprio default em vez de
        # falhar o subagente. Provider-agnostico, sem lista de modelos hardcoded.
        for _ in range(2):
            if not res.get("failed"):
                break
            error = res.get("error") or ""
            if apply_temperature and _provider_rejected_temperature(error):
                apply_temperature = False
                logger.info("[AIAgent]%s provider recusou 'temperature'; refazendo sem ela", log_ctx)
                res = await _run(apply_temperature, reasoning_effort, cur_system_prompt, cur_user_prompt)
                continue
            if reasoning_effort is not None and _provider_rejected_parameter(error, "reasoning_effort"):
                reasoning_effort = None
                logger.info(
                    "[AIAgent]%s provider recusou 'reasoning_effort'; refazendo sem ele",
                    log_ctx,
                )
                res = await _run(apply_temperature, reasoning_effort, cur_system_prompt, cur_user_prompt)
                continue
            break

        if res.get("failed"):
            error_msg = res.get("error", "Erro desconhecido na chamada do AIAgent")
            friendly_error = format_human_friendly_error(error_msg)
            logger.error("[AIAgent]%s Erro na chamada: %s", log_ctx, error_msg)
            _record_outcome(False, error_msg)
            raise Exception(friendly_error)

        content = (res.get("final_response") or "").strip()
        if content in {"", "(empty)"}:
            logger.warning(
                "[AIAgent]%s resposta vazia do subagente; refazendo com instrucao JSON estrita",
                log_ctx,
            )
            original_system_prompt = cur_system_prompt
            original_user_prompt = cur_user_prompt
            cur_system_prompt = (
                original_system_prompt + "\n\nRECOVERY MODE: Your previous answer had no visible content. "
                "Return ONLY the requested JSON payload. Do not include reasoning, "
                "markdown, comments, or prose. If there are no findings, return [] exactly."
            )
            cur_user_prompt = (
                original_user_prompt + "\n\nReturn the final answer now as valid JSON only. "
                "If the expected result is a list, return a JSON array."
            )
            apply_temperature = True
            reasoning_effort = initial_reasoning_effort
            res = await _run(apply_temperature, reasoning_effort, cur_system_prompt, cur_user_prompt)
            for _ in range(2):
                if not res.get("failed"):
                    break
                error = res.get("error") or ""
                if apply_temperature and _provider_rejected_temperature(error):
                    apply_temperature = False
                    logger.info(
                        "[AIAgent]%s provider recusou 'temperature' no retry; refazendo sem ela",
                        log_ctx,
                    )
                    res = await _run(apply_temperature, reasoning_effort, cur_system_prompt, cur_user_prompt)
                    continue
                if reasoning_effort is not None and _provider_rejected_parameter(error, "reasoning_effort"):
                    reasoning_effort = None
                    logger.info(
                        "[AIAgent]%s provider recusou 'reasoning_effort' no retry; refazendo sem ele",
                        log_ctx,
                    )
                    res = await _run(apply_temperature, reasoning_effort, cur_system_prompt, cur_user_prompt)
                    continue
                break
            if res.get("failed"):
                error_msg = res.get("error", "Erro desconhecido na chamada do AIAgent")
                logger.error("[AIAgent]%s Erro na chamada apos retry: %s", log_ctx, error_msg)
                _record_outcome(False, error_msg)
                raise Exception(f"Erro na chamada do AIAgent: {error_msg}")
            content = (res.get("final_response") or "").strip()
            if content in {"", "(empty)"}:
                _record_outcome(False, "resposta vazia apos recovery retry")
                raise ValueError("AIAgent returned an empty final response after recovery retry")

        logger.info("[AIAgent]%s Resposta recebida (%d chars)", log_ctx, len(content))
        _record_outcome(True)
        return content

    last_exc: Exception | None = None
    for idx, (cand_provider, cand_model, cand_api_key, cand_base_url) in enumerate(candidates):
        # Cache de resposta: só para leaf single-shot sem tools (mesmo escopo do
        # response_schema de Structured Outputs) -- chat/tools nunca cacheia. A
        # chave usa o candidato JA RESOLVIDO (não a tier bruta nem a cadeia
        # inteira), senão um fallback automatico de modelo poderia devolver a
        # resposta cacheada de outro modelo. `is True` (não truthy simples) de
        # proposito: muitos testes usam settings=MagicMock() sem configurar este
        # campo, e um MagicMock não configurado é truthy -- ativaria cache em
        # quase toda a suite existente e causaria contaminação entre testes que
        # reusam o mesmo prompt "s"/"u".
        cacheable = settings.a11y_response_cache_enabled is True and not enabled_toolsets
        cache_key = (
            make_cache_key(
                cand_provider, cand_model, system_prompt, user_prompt, str(temperature), str(bool(response_schema))
            )
            if cacheable
            else ""
        )
        if cacheable:
            cached = get_cached_response(cache_key)
            if cached is not None:
                logger.info("[AIAgent]%s cache hit para agent_label=%s", log_ctx, label)
                return cached

            # Batch Inference (2026, ver batch_collector.py): modo de coleta ligado
            # pelo orchestrator só em torno do gather dos agentes de análise. Em
            # vez de ligar pro provider, grava a chamada e devolve o sentinel "[]"
            # -- todo agente já trata "nenhum issue encontrado" como o caminho
            # normal e testado, então nenhum dos 25 precisa saber que isto está
            # acontecendo. O resultado real chega depois via cache (mesma chave),
            # quando o batch terminar e o pipeline rodar de novo com a coleta
            # desligada. So a primeira tentativa da cadeia participa do batch --
            # coerente com o design existente, batch nunca falha, sempre devolve
            # o sentinel.
            if batch_collector.is_collecting():
                batch_collector.record(cache_key, cand_provider, cand_model, system_prompt, user_prompt)
                return "[]"

        try:
            content = await _attempt(cand_provider, cand_model, cand_api_key, cand_base_url)
        except Exception as exc:
            last_exc = exc
            if idx < len(candidates) - 1:
                logger.warning(
                    "[AIAgent]%s modelo verificado %s/%s da cadeia de structured output falhou (%s); "
                    "tentando o proximo da cadeia.",
                    log_ctx,
                    cand_provider,
                    cand_model,
                    exc,
                )
                continue
            raise
        if cacheable:
            set_cached_response(cache_key, content, settings.a11y_response_cache_ttl_seconds)
        return content

    assert last_exc is not None  # candidates sempre tem >= 1 item
    raise last_exc


async def call_llm_structured(
    system_prompt: str,
    user_prompt: str,
    build: Callable[[str], T],
    *,
    attempts: int = 2,
    temperature: float = 0.2,
    max_tokens: int = 16384,
    request_id: str = "",
    agent_label: str = "",
    response_schema: dict[str, Any] | None = None,
) -> T:
    """
    Chama o LLM e constroi um objeto tipado via `build(raw)`, com retry/repair.

    `build` faz parse + validação (ex.: lambda raw: VPATReport(**extract_json_object(raw))).
    Se o parse ou a validação Pydantic falhar, refaz a chamada UMA vez com uma
    instrucao corretiva anexada ao prompt. Elimina a variancia do output do LLM
    que ocasionalmente quebra o schema estrito -- inclusive JSON truncado no meio
    (achado real contra Ollama Cloud: ~1 a cada 15-20 chamadas em agentes de
    guideline single-shot; sobe bastante sob concorrencia alta), que sem este
    retry vira um AgentResult(success=False) definitivo em vez de se recuperar.

    Se o JSON estiver truncado (max_tokens atingido), aumenta o max_tokens e retry.

    Levanta a ultima excecao se todas as tentativas falharem.
    """
    last_error: Exception | None = None
    prompt = user_prompt
    current_max_tokens = max_tokens
    for attempt in range(1, attempts + 1):
        raw = await call_llm(
            system_prompt=system_prompt,
            user_prompt=prompt,
            temperature=temperature,
            max_tokens=current_max_tokens,
            request_id=request_id,
            agent_label=agent_label,
            response_schema=response_schema,
        )
        try:
            return build(raw)
        except (ValueError, ValidationError) as exc:
            last_error = exc
            error_str = str(exc)
            is_truncated = _is_json_truncated(raw) or "truncated" in error_str.lower() or "No valid JSON" in error_str

            logger.warning(
                "[AIAgent] %s parse/schema falhou (tentativa %d/%d): %s",
                agent_label or "leaf",
                attempt,
                attempts,
                exc,
            )

            if is_truncated and attempt < attempts:
                # Aumenta max_tokens para dar mais espaco ao modelo
                current_max_tokens = min(current_max_tokens * 2, 32768)
                logger.info(
                    "[AIAgent] %s JSON parece truncado; aumentando max_tokens para %d e retry",
                    agent_label or "leaf",
                    current_max_tokens,
                )
                prompt = (
                    user_prompt + "\n\nIMPORTANT: Your previous response was cut off by the output limit. "
                    "Continue the JSON array exactly where you left off. Do NOT restart. "
                    "Finish the array and close it properly with ']'"
                )
            else:
                prompt = (
                    user_prompt + "\n\nIMPORTANT: Your previous response was not valid JSON for the "
                    "required schema. Return ONLY the JSON, no markdown fences, no prose, "
                    "and include every required field exactly as specified."
                )

    assert last_error is not None  # attempts >= 1 garante atribuicao
    raise last_error


def refresh_settings() -> None:
    """Call after settings change to pick up new env/provider values."""
    from backend.src.services.model_router import clear_cache
    from backend.src.services.response_cache import clear_cache as clear_response_cache

    get_settings.cache_clear()
    clear_cache()  # "Alto" pode resolver para outro modelo apos trocar provider
    clear_response_cache()  # respostas cacheadas sob o provider/model antigo ficam invalidas
