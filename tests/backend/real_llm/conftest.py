"""
Conftest da suite real-llm.

Esta suite chama Ollama Cloud (padrão, tier "alto") ou Factory (modelo "auto"),
para validar a pirâmide completa de evals (component -> production observability)
contra um provider real, não um AsyncMock.

Opt-in obrigatório: chamadas reais custam tempo e tokens, então esta suite só
roda com RUN_REAL_LLM_TESTS=1 explícito (nunca em CI por padrão). Sem
chave do provider selecionado no ambiente, os testes são pulados com motivo claro em vez
de falhar com erro de rede.
"""
import os

import pytest

from backend.src.config.settings import get_settings

RUN_REAL_LLM_TESTS = os.getenv("RUN_REAL_LLM_TESTS", "").strip() == "1"
REAL_PROVIDER = os.getenv("REAL_LLM_PROVIDER", "ollama-cloud")


def selected_key(provider: str) -> str | None:
    if provider == "factory":
        return os.getenv("FACTORY_API_KEY")
    if provider == "ollama-cloud":
        return os.getenv("OLLAMA_API_KEY") or os.getenv("OLLAMA_CLOUD_API_KEY")
    raise ValueError(f"Provider de eval não suportado: {provider}")

pytestmark = pytest.mark.real_llm


def pytest_collection_modifyitems(config, items):
    if RUN_REAL_LLM_TESTS and selected_key(REAL_PROVIDER):
        return
    reason = (
        "real_llm suite desativada -- defina RUN_REAL_LLM_TESTS=1 e "
        "a chave do REAL_LLM_PROVIDER para rodar evals reais"
        if not RUN_REAL_LLM_TESTS
        else f"Chave do provider {REAL_PROVIDER} não configurada no ambiente"
    )
    skip_marker = pytest.mark.skip(reason=reason)
    for item in items:
        if "real_llm" in str(item.fspath).replace("\\", "/"):
            item.add_marker(skip_marker)


@pytest.fixture(scope="session", autouse=True)
def _real_provider():
    """Isola o provider escolhido, sem cache ou fallback para outro serviço.

    O cache de respostas (a11y_response_cache_enabled, ver settings.py) guarda o texto cru
    devolvido pelo provider ANTES de qualquer validação de que é JSON parseável -- observado em
    produção nesta sessão: uma resposta truncada do modelo real vira um hit reaproveitado por
    até 5 minutos (TTL), fazendo um problema transiente do provider parecer uma falha
    determinística e persistente do agente. Numa suite que existe para medir o comportamento
    real do modelo a cada chamada, cache é ruído -- desligamos para sempre bater na rede real.
    """
    from backend.src.config.settings import Settings
    from run_agent import AIAgent

    with pytest.MonkeyPatch.context() as config:
        config.setenv("LLM_PROVIDER", REAL_PROVIDER)
        config.setenv("LLM_API_KEY", selected_key(REAL_PROVIDER) or "")
        config.setenv("LLM_MODEL", os.getenv("REAL_LLM_MODEL", "auto" if REAL_PROVIDER == "factory" else "alto"))
        config.setenv("LLM_BASE_URL", "")
        config.setenv("A11Y_RESPONSE_CACHE_ENABLED", "false")
        config.setattr(Settings, "build_fallback_model", lambda self: {})
        config.setattr(AIAgent, "_resolve_auto_fallback", lambda self: None)
        get_settings.cache_clear()
        try:
            yield
        finally:
            get_settings.cache_clear()


@pytest.fixture(scope="session")
def alto_model_id() -> str:
    from backend.src.services.model_router import resolve_alto_model

    return os.getenv("REAL_LLM_MODEL") or ("auto" if REAL_PROVIDER == "factory" else resolve_alto_model(REAL_PROVIDER))


async def run_agent_with_retry(agent_fn, html_content: str, retries: int = 1):
    """Roda um agente real tolerando UMA falha transiente de parsing (JSON truncado pelo
    provider -- observado ocasionalmente contra o Ollama Cloud nesta sessão de validação).

    Não mascara regressão persistente: se falhar de novo após o retry, o AgentResult com
    success=False é devolvido como está, e quem chamou decide como falhar o teste.
    """
    result = await agent_fn(html_content)
    attempt = 0
    while not result.success and attempt < retries:
        attempt += 1
        result = await agent_fn(html_content)
    return result


def assert_complete_result(result) -> None:
    """Transport success must not hide partial specialist failure."""
    assert result.success is True, result.error
    assert result.data.get("complete") is True, result.data.get("warning")
    metrics = result.data.get("agent_metrics", [])
    assert metrics
    assert all(m["success"] for m in metrics), metrics
