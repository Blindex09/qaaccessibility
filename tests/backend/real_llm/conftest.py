"""
Conftest da suite real-llm.

Diferente do resto de tests/backend (100% mockado/determinístico), esta suite
chama o Ollama Cloud de verdade, tier "alto" (model_router.resolve_alto_model),
para validar a pirâmide completa de evals (component -> production observability)
contra um provider real, não um AsyncMock.

Opt-in obrigatório: chamadas reais custam tempo e tokens, então esta suite só
roda com RUN_REAL_LLM_TESTS=1 explícito (nunca em CI por padrão). Sem
OLLAMA_API_KEY no ambiente, os testes são pulados com um motivo claro em vez
de falhar com erro de rede.
"""
import os

import pytest

from backend.src.config.settings import get_settings

RUN_REAL_LLM_TESTS = os.getenv("RUN_REAL_LLM_TESTS", "").strip() == "1"
HAS_OLLAMA_KEY = bool(os.getenv("OLLAMA_API_KEY") or os.getenv("OLLAMA_CLOUD_API_KEY"))

pytestmark = pytest.mark.real_llm


def pytest_collection_modifyitems(config, items):
    if RUN_REAL_LLM_TESTS and HAS_OLLAMA_KEY:
        return
    reason = (
        "real_llm suite desativada -- defina RUN_REAL_LLM_TESTS=1 e "
        "OLLAMA_API_KEY para rodar evals reais contra o Ollama Cloud"
        if not RUN_REAL_LLM_TESTS
        else "OLLAMA_API_KEY/OLLAMA_CLOUD_API_KEY não configurada no ambiente"
    )
    skip_marker = pytest.mark.skip(reason=reason)
    for item in items:
        if "real_llm" in str(item.fspath).replace("\\", "/"):
            item.add_marker(skip_marker)


@pytest.fixture(scope="session", autouse=True)
def _real_ollama_provider():
    """Força o provider global para ollama-cloud, tier alto, e desliga o response cache.

    O cache de respostas (a11y_response_cache_enabled, ver settings.py) guarda o texto cru
    devolvido pelo provider ANTES de qualquer validação de que é JSON parseável -- observado em
    produção nesta sessão: uma resposta truncada do modelo real vira um hit reaproveitado por
    até 5 minutos (TTL), fazendo um problema transiente do provider parecer uma falha
    determinística e persistente do agente. Numa suite que existe para medir o comportamento
    real do modelo a cada chamada, cache é ruído -- desligamos para sempre bater na rede real.
    """
    prev_provider = os.environ.get("LLM_PROVIDER")
    prev_model = os.environ.get("LLM_MODEL")
    prev_cache = os.environ.get("A11Y_RESPONSE_CACHE_ENABLED")
    os.environ["LLM_PROVIDER"] = "ollama-cloud"
    os.environ.pop("LLM_MODEL", None)  # None -> model_router resolve o "alto" dinamicamente
    os.environ["A11Y_RESPONSE_CACHE_ENABLED"] = "false"
    get_settings.cache_clear()
    yield
    if prev_provider is None:
        os.environ.pop("LLM_PROVIDER", None)
    else:
        os.environ["LLM_PROVIDER"] = prev_provider
    if prev_model is not None:
        os.environ["LLM_MODEL"] = prev_model
    if prev_cache is None:
        os.environ.pop("A11Y_RESPONSE_CACHE_ENABLED", None)
    else:
        os.environ["A11Y_RESPONSE_CACHE_ENABLED"] = prev_cache
    get_settings.cache_clear()


@pytest.fixture(scope="session")
def alto_model_id() -> str:
    from backend.src.services.model_router import resolve_alto_model

    return resolve_alto_model("ollama-cloud")


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
