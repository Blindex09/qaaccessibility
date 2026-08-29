"""
tests/backend/unit/test_models_dev_catalog.py
Bug real de auditoria (2026-07-26): o catalogo de modelos tinha entradas
deprecated/sunsetting continuando selecionaveis (gpt-5.3-chat-latest,
kimi-k2.5) e faltava o flagship atual da Moonshot (kimi-k3), confirmado
contra a documentacao oficial de cada provedor.
"""
from agent.models_dev import _CATALOG, _resolve_endpoint, list_agentic_models

_DEPRECATED_OR_RETIRED_MODEL_IDS = {
    # OpenAI -- modelos pré-2026 e snapshots depraca-dos/desligados
    "o1", "o1-preview", "o1-mini", "o3-mini", "gpt-4o", "gpt-4o-mini", "gpt-4", "gpt-3.5-turbo",
    "gpt-5.3-chat-latest", "gpt-5.2-chat-latest",
    "gpt-5-chat-latest", "gpt-4o-2024-05-13", "o1-2024-12-17",
    "gpt-5-2025-08-07", "gpt-5-mini-2025-08-07", "o3-2025-04-16", "o3-pro-2025-06-10",
    # xAI -- retirados em 15/mai/2026, redirecionam silenciosamente para outro modelo/preço
    "grok-4-1-fast-reasoning", "grok-4-1-fast-non-reasoning",
    "grok-4-fast-reasoning", "grok-4-fast-non-reasoning",
    "grok-4-0709", "grok-code-fast-1", "grok-3", "grok-imagine-image-pro",
    # Kimi/Moonshot -- descontinuados/sunsetting per platform.kimi.ai/docs/models
    "kimi-k2.5", "kimi-latest", "kimi-thinking-preview", "kimi-k3", "kimi-k3:cloud",
}


def test_catalogo_nao_tem_modelos_deprecados_conhecidos():
    for provider, models in _CATALOG.items():
        for model_id in models:
            assert model_id not in _DEPRECATED_OR_RETIRED_MODEL_IDS, (
                f"{provider}/{model_id} está deprecado/retirado, não deveria "
                "continuar selecionável no catálogo"
            )


def test_catalogo_nao_expoe_modelos_preview():
    for provider, models in _CATALOG.items():
        assert not any("preview" in model_id.lower() or "beta" in model_id.lower() for model_id in models), (
            f"{provider} ainda expõe modelo preview/beta"
        )


def test_kimi_k3_bloqueado_e_nao_selecionavel():
    ollama_models = list_agentic_models("ollama-cloud")
    assert not any("kimi-k3" in model_id for model_id in ollama_models), (
        "kimi-k3 foi descontinuado/removido e não deve constar no catálogo"
    )


def test_ollama_cloud_endpoint_nunca_cai_pro_localhost_sem_base_url(monkeypatch):
    """Bug real (2026-08-10): sem base_url explícito, o catálogo live de
    'ollama-cloud' caía pro Ollama LOCAL (localhost:11434) em vez da nuvem
    (https://ollama.com/v1) -- a chamada real de chat (run_agent.py) já tinha
    o default correto, só o catálogo de metadados (fetch_live_models) errava,
    fazendo a listagem de modelos falhar sempre (conexão recusada) mesmo com
    a análise em si funcionando normalmente contra a nuvem."""
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    endpoint = _resolve_endpoint("ollama-cloud", None)
    assert endpoint == "https://ollama.com/v1/models"
    assert "localhost" not in endpoint


def test_explicit_deprecated_models_contem_modelos_pre_2026():
    from agent.models_dev import _EXPLICIT_DEPRECATED_MODELS

    esperados = {"o1", "o1-preview", "o1-mini", "o3-mini", "gpt-4o", "gpt-4o-mini", "gpt-4", "gpt-3.5-turbo"}
    assert esperados.issubset(_EXPLICIT_DEPRECATED_MODELS), (
        "Todos os modelos pré-2026 solicitados devem estar em _EXPLICIT_DEPRECATED_MODELS"
    )


def test_parse_openai_models_desconsidera_modelos_pre_2026():
    from agent.models_dev import _parse_openai_models

    mock_response = {
        "data": [
            {"id": "o1"},
            {"id": "o1-preview"},
            {"id": "o1-mini"},
            {"id": "o3-mini"},
            {"id": "gpt-4o"},
            {"id": "gpt-4o-mini"},
            {"id": "gpt-4"},
            {"id": "gpt-3.5-turbo"},
            {"id": "gpt-4-turbo"},
            {"id": "o1-2024-12-17"},
            {"id": "gpt-4o-2024-05-13"},
            {"id": "gpt-5.6-old-created", "created": 1735689600},  # timestamp de 2025
            {"id": "gpt-5.6-sol", "created": 1767225600},
            {"id": "gpt-5.5-pro", "created": 1767225600},
            {"id": "gpt-5.4-pro", "created": 1767225600},
        ]
    }

    parsed = _parse_openai_models(mock_response)

    assert "o1" not in parsed
    assert "o1-preview" not in parsed
    assert "o1-mini" not in parsed
    assert "o3-mini" not in parsed
    assert "gpt-4o" not in parsed
    assert "gpt-4o-mini" not in parsed
    assert "gpt-4" not in parsed
    assert "gpt-3.5-turbo" not in parsed
    assert "gpt-4-turbo" not in parsed
    assert "gpt-5.6-old-created" not in parsed

    assert "gpt-5.6-sol" in parsed
    assert "gpt-5.5-pro" in parsed
    assert "gpt-5.4-pro" in parsed



def test_ollama_cloud_catalog_ids_batem_com_a_api_ao_vivo():
    """Achado real (2026-08-11): os IDs anteriores deste catálogo tinham
    sufixos inventados/desatualizados (ex.: "kimi-k3:cloud", quando a API ao
    vivo devolve só "kimi-k3") que NUNCA batiam com o que
    ollama_cloud_adapter.discover_ollama_cloud_descriptors() de fato retorna
    -- confirmado contra uma chamada real à API nesta data (18 modelos). Sem
    bater o ID exato, o merge de custo estático em get_model_info() nunca
    disparava: o preço pesquisado ficava morto no código. Trava aqui que os
    IDs usados como chave no catálogo estático são exatamente os IDs reais
    (sem sufixo ":cloud" inventado, com o sufixo de snapshot real do
    DeepSeek Flash)."""
    live_ids_confirmados_2026_08_11 = {
        "glm-5.2", "nemotron-3-nano:30b", "gpt-oss:120b",
        "minimax-m3", "deepseek-v4-pro", "glm-5.1", "kimi-k2.6", "gpt-oss:20b",
        "kimi-k2.7-code", "minimax-m2.7", "mistral-large-3:675b", "gemma4:31b",
        "qwen3.5:397b", "nemotron-3-super", "nemotron-3-ultra", "deepseek-v4-flash:0731",
    }
    catalog_ids = set(_CATALOG["ollama-cloud"])
    missing = live_ids_confirmados_2026_08_11 - catalog_ids
    assert not missing, f"IDs reais da API ausentes do catálogo estático: {missing}"


def test_ollama_cloud_costs_sao_precos_reais_pesquisados_no_laboratorio_original():
    """Achado real (2026-08-11): a Ollama Cloud não publica $/token próprio
    (cobra por assinatura/GPU-time, ver model_router.py::_SUBSCRIPTION_BASED_PROVIDERS) --
    os cost_input/cost_output do catálogo pra "ollama-cloud" vêm do preço
    oficial publicado pelo laboratório ORIGINAL de cada modelo (Moonshot/Kimi,
    Zhipu/GLM, MiniMax, DeepSeek, Alibaba/Qwen, NVIDIA/Nemotron, OpenAI/gpt-oss,
    Mistral), pesquisado nesta data. Antes dessa correção, todas as entradas
    caíam silenciosamente no default genérico de ModelInfo (0.15/0.6),
    mascarado como se fosse dado real -- trava aqui que os valores pesquisados
    não regridem pro default por engano. Lê direto de _CATALOG (não
    get_model_info) de propósito: testa o dado estático que EU editei, sem
    depender de rede/live-fetch numa suíte unitária."""
    researched = {
        "kimi-k2.6": (0.95, 4.00),
        "kimi-k2.7-code": (0.95, 4.00),
        "deepseek-v4-flash:0731": (0.14, 0.28),
        "deepseek-v4-pro": (0.435, 0.87),
        "glm-5.1": (0.952, 2.99),
        "glm-5.2": (1.40, 4.40),
        "minimax-m2.7": (0.24, 0.96),
        "minimax-m3": (0.30, 1.20),
        "qwen3.5:397b": (0.60, 3.60),
        "gemma4:31b": (0.09, 0.34),
        "nemotron-3-ultra": (0.50, 2.20),
        "nemotron-3-super": (0.085, 0.40),
        "nemotron-3-nano:30b": (0.05, 0.20),
        "gpt-oss:20b": (0.030, 0.130),
        "gpt-oss:120b": (0.037, 0.100),
        "mistral-large-3:675b": (0.50, 1.50),
    }
    for model_id, (cost_input, cost_output) in researched.items():
        info = _CATALOG["ollama-cloud"].get(model_id)
        assert info is not None, f"{model_id} deveria existir no catálogo estático ollama-cloud"
        assert info.cost_input == cost_input, f"{model_id}: cost_input esperado {cost_input}, veio {info.cost_input}"
        assert info.cost_output == cost_output, f"{model_id}: cost_output esperado {cost_output}, veio {info.cost_output}"
