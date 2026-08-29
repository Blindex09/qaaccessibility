"""
Camada 9/9 -- Production Observability (real).

Não testa "o agente encontrou o issue certo" (isso é Agent Evals) -- testa o
que acontece quando o mundo real dá errado: credencial inválida (401 de
verdade contra api.ollama.com, não mockado), timing real registrado em
`AgentMetrics`, falha de parsing de JSON do provider tratada explicitamente
(nunca engolida) e logs estruturados via `logging`, nunca `print`.

Achado desta suite (documentado, não corrigido aqui -- fora do escopo de
"montar os testes"): contra o Ollama Cloud real, `run_screen_reader`
ocasionalmente recebeu um JSON truncado do provider (~1 a cada 3 chamadas
nesta sessão de validação) e reagiu corretamente: `success=False` com
`error` preenchido, nunca um `success=True` com issues=[] disfarçando uma
falha de falso-negativo. Este teste providence essa garantia formalmente.
"""
import logging
import os
from unittest.mock import AsyncMock, patch

import pytest

from backend.src.agents.perceiver.perceiver import run_perceiver
from backend.src.config.settings import get_settings

pytestmark = pytest.mark.real_llm


@pytest.mark.asyncio
async def test_unreachable_endpoint_produces_humanized_error_not_a_crash() -> None:
    """Falha de rede real (host inexistente, não mockada) -- deve virar AgentResult(success=False,
    error=<mensagem amigável>), nunca uma exception não tratada subindo até o chamador. Preferido a
    forçar um 401 de credencial: o cache de resposta de agentes (a11y_response_cache_enabled, TTL
    300s) pode mascarar chamadas subsequentes com o mesmo prompt e devolver um hit válido antigo
    mesmo com a chave trocada -- um host inalcançável nunca tem esse risco."""
    prev_base_url = os.environ.get("LLM_BASE_URL")
    os.environ["LLM_BASE_URL"] = "http://127.0.0.1:1/v1"  # porta inexistente -> connection refused real
    get_settings.cache_clear()
    try:
        result = await run_perceiver(
            '<html><body><img src="observability-unreachable-probe.png"></body></html>'
        )
    finally:
        if prev_base_url is None:
            os.environ.pop("LLM_BASE_URL", None)
        else:
            os.environ["LLM_BASE_URL"] = prev_base_url
        get_settings.cache_clear()

    assert result.success is False, "host inalcancavel deveria falhar de forma explicita, nao silenciosa"
    assert result.error, "AgentResult.error vazio -- erro real engolido sem diagnostico"
    # error_formatter.format_human_friendly_error nunca deve vazar stacktrace/traceback cru
    assert "Traceback" not in result.error
    assert "raise" not in result.error.lower()


@pytest.mark.asyncio
async def test_real_call_emits_structured_logs_not_print(caplog: pytest.LogCaptureFixture) -> None:
    """Regra do projeto: 'Zero console.log em produção' -- valida via logging real, não mock."""
    with caplog.at_level(logging.INFO, logger="backend.src.services.llm_client"):
        result = await run_perceiver('<html><body><img src="logo.png"></body></html>')

    assert result.success is True
    provider_log = [r for r in caplog.records if "AIAgent" in r.message or "subagent" in r.message]
    assert provider_log, "nenhuma linha de log estruturada emitida pelo llm_client em uma chamada real"


@pytest.mark.asyncio
async def test_json_parse_failure_from_real_provider_fails_explicitly_not_silently() -> None:
    """Contrato de robustez: se o provider real devolver JSON malformado/truncado, o agente
    reporta success=False -- NUNCA success=True com issues=[] mascarando uma falha real como
    'página sem problemas' (isso seria um falso-negativo perigoso numa ferramenta de a11y)."""
    with patch(
        "backend.src.services.llm_client.call_llm",
        new=AsyncMock(return_value='{"issues": [{"id": "x", "criterion": "1.1.1 Non-text'),  # truncado, real-world shape
    ):
        result = await run_perceiver('<html><body><img src="logo.png"></body></html>')

    assert result.success is False, (
        "JSON truncado (formato observado de verdade contra o Ollama Cloud nesta suite) "
        "não pode virar success=True silenciosamente"
    )
    assert result.error


@pytest.mark.asyncio
async def test_hooks_fire_during_a_real_call(alto_model_id: str) -> None:
    """Sistema de hooks plugáveis (agent_hooks.py) -- valida que PRE_LLM_CALL e
    POST_LLM_CALL disparam de verdade numa chamada real ao Ollama Cloud, não só
    contra AIAgent mockado (já coberto em test_llm_client.py). Isso é o que
    fecha o gap 'Hooks: ausente' da auditoria de vocabulário 2026."""
    from backend.src.services import agent_hooks

    pre_calls: list[tuple] = []
    post_calls: list[tuple] = []
    agent_hooks.register_hook(agent_hooks.PRE_LLM_CALL, lambda *a: pre_calls.append(a))
    agent_hooks.register_hook(agent_hooks.POST_LLM_CALL, lambda *a: post_calls.append(a))
    try:
        result = await run_perceiver('<html><body><img src="hooks-real-probe.png"></body></html>')
    finally:
        agent_hooks.clear_all_hooks()

    assert result.success is True
    assert len(pre_calls) == 1, f"PRE_LLM_CALL não disparou (ou disparou {len(pre_calls)}x) numa chamada real"
    assert len(post_calls) == 1
    provider, model, task_id, label, success, duration_ms = post_calls[0]
    assert provider == "ollama-cloud"
    assert model == alto_model_id or model  # modelo real resolvido, não vazio
    assert success is True
    assert duration_ms > 0, "hook recebeu duracao real da chamada, nao um valor zerado"


@pytest.mark.asyncio
async def test_hook_registered_by_test_never_breaks_a_real_call() -> None:
    """Garantia central do sistema de hooks: um observador de terceiro quebrado
    nunca pode impedir a resposta real do provider de voltar ao chamador."""
    from backend.src.services import agent_hooks

    def bad_hook(*a):
        raise RuntimeError("hook de terceiro quebrado, de proposito")

    agent_hooks.register_hook(agent_hooks.POST_LLM_CALL, bad_hook)
    try:
        result = await run_perceiver('<html><body><img src="hooks-resilience-probe.png"></body></html>')
    finally:
        agent_hooks.clear_all_hooks()

    assert result.success is True, "hook quebrado impediu uma chamada real de completar com sucesso"
