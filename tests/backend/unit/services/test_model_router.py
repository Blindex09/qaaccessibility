"""Testes do resolvedor "Alto" (selecao automatica do melhor modelo do provider)."""

from types import SimpleNamespace
from unittest.mock import patch

from backend.src.services import model_router


def _info(reasoning: bool, context: int, cost: float = 0.0):
    return SimpleNamespace(
        reasoning=reasoning, context_window=context, cost_input=cost, cost_output=cost,
        release_date="2026-01-01"
    )


class TestIsAlto:
    def test_alto_and_empty_are_alto(self):
        assert model_router.is_alto("alto")
        assert model_router.is_alto("ALTO")
        assert model_router.is_alto("")
        assert model_router.is_alto(None)

    def test_concrete_model_is_not_alto(self):
        assert not model_router.is_alto("gpt-5.5")


class TestResolveAltoModel:
    def setup_method(self):
        model_router.clear_cache()

    def teardown_method(self):
        model_router.clear_cache()

    def test_picks_reasoning_then_largest_context(self):
        infos = {
            "small": _info(reasoning=False, context=8000),
            "reasoner": _info(reasoning=True, context=128000),
            "big-no-reason": _info(reasoning=False, context=1000000),
        }
        with patch.object(model_router, "list_agentic_models", return_value=list(infos)), patch.object(
            model_router, "get_model_info", side_effect=lambda p, m: infos[m]
        ):
            assert model_router.resolve_alto_model("openai") == "reasoner"

    def test_tiebreak_prefers_cheaper(self):
        infos = {
            "pricey": _info(reasoning=True, context=128000, cost=10.0),
            "cheap": _info(reasoning=True, context=128000, cost=1.0),
        }
        with patch.object(model_router, "list_agentic_models", return_value=list(infos)), patch.object(
            model_router, "get_model_info", side_effect=lambda p, m: infos[m]
        ):
            assert model_router.resolve_alto_model("openai") == "cheap"

    def test_empty_when_no_agentic_models(self):
        with patch.object(model_router, "list_agentic_models", return_value=[]):
            assert model_router.resolve_alto_model("openai") == ""

    def test_filters_out_requires_extra_usage_models_by_default(self):
        infos = {
            "extra-usage-flagship": SimpleNamespace(reasoning=True, context_window=1000000, cost_input=1.0, cost_output=1.0, release_date="2026-01-01", requires_extra_usage=True),
            "other": SimpleNamespace(reasoning=True, context_window=128000, cost_input=0.1, cost_output=0.1, release_date="2026-01-01", requires_extra_usage=False),
        }
        with patch.object(model_router, "list_agentic_models", return_value=list(infos)), patch.object(
            model_router, "get_model_info", side_effect=lambda p, m: infos[m]
        ):
            assert model_router.resolve_alto_model("openai", allow_extra_usage=False) != "extra-usage-flagship"
            model_router.clear_cache()
            assert model_router.resolve_alto_model("openai", allow_extra_usage=True) == "extra-usage-flagship"

        # Claude 5 Fable requires extra usage credits
        model_router.clear_cache()
        assert model_router.resolve_alto_model("anthropic", allow_extra_usage=False) != "claude-fable-5"

    def test_empty_when_catalog_raises(self):
        with patch.object(model_router, "list_agentic_models", side_effect=RuntimeError("offline")):
            assert model_router.resolve_alto_model("openai") == ""

    def test_openai_alto_resolves_only_2026_models(self):
        resolved = model_router.resolve_alto_model("openai")
        assert resolved in {"gpt-5.6-sol", "gpt-5.6", "gpt-5.6-terra", "gpt-5.6-luna", "gpt-5.5-pro", "gpt-5.4-pro"}
        assert not resolved.startswith(("o1", "gpt-4", "gpt-3.5"))
        assert resolved not in {"o1", "o1-preview", "o1-mini", "o3-mini", "gpt-4o", "gpt-4o-mini", "gpt-4", "gpt-3.5-turbo"}

    def test_openai_alto_ignores_pre_2026_candidates(self):
        pre_2026_and_2026_infos = {
            "o1": SimpleNamespace(reasoning=True, context_window=128000, cost_input=15.0, cost_output=60.0, release_date="2024-12-17"),
            "gpt-4o": SimpleNamespace(reasoning=False, context_window=128000, cost_input=2.5, cost_output=10.0, release_date="2024-05-13"),
            "gpt-5.6-sol": SimpleNamespace(reasoning=True, context_window=131072, cost_input=0.15, cost_output=0.6, release_date="2026-07-09"),
        }
        with patch.object(model_router, "list_agentic_models", return_value=["o1", "gpt-4o", "gpt-5.6-sol"]), patch.object(
            model_router, "get_model_info", side_effect=lambda p, m: pre_2026_and_2026_infos.get(m)
        ):
            assert model_router.resolve_alto_model("openai") == "gpt-5.6-sol"


class TestResolveFastModel:
    def setup_method(self):
        model_router.clear_cache()

    def teardown_method(self):
        model_router.clear_cache()

    def test_picks_cheapest(self):
        infos = {
            "pricey": _info(reasoning=False, context=128000, cost=10.0),
            "cheap": _info(reasoning=False, context=8000, cost=1.0),
        }
        with patch.object(model_router, "list_agentic_models", return_value=list(infos)), patch.object(
            model_router, "get_model_info", side_effect=lambda p, m: infos[m]
        ):
            assert model_router.resolve_fast_model("openai") == "cheap"

    def test_prefers_fast_name_heuristics_when_no_cost(self):
        # Nomes que contêm nano/flash/lite/mini devem ser preferidos quando não há custo
        infos = {
            "heavy-model": _info(reasoning=False, context=128000, cost=0.0),
            "gpt-5-mini": _info(reasoning=False, context=8000, cost=0.0),
        }
        with patch.object(model_router, "list_agentic_models", return_value=list(infos)), patch.object(
            model_router, "get_model_info", side_effect=lambda p, m: infos[m]
        ):
            assert model_router.resolve_fast_model("openai") == "gpt-5-mini"

    def test_empty_when_no_candidates(self):
        with patch.object(model_router, "list_agentic_models", return_value=[]):
            assert model_router.resolve_fast_model("openai") == ""


class TestResolveCodeModel:
    def setup_method(self):
        model_router.clear_cache()

    def teardown_method(self):
        model_router.clear_cache()

    def test_prefers_models_with_code_substring(self):
        infos = {
            "general-model": _info(reasoning=True, context=128000, cost=1.0),
            "gpt-5.3-codex": _info(reasoning=False, context=128000, cost=2.0),
            "kimi-k2.7-code": _info(reasoning=True, context=128000, cost=3.0),
        }
        with patch.object(model_router, "list_agentic_models", return_value=list(infos)), patch.object(
            model_router, "get_model_info", side_effect=lambda p, m: infos[m]
        ):
            # Entre modelos de codigo, reasoning + context desempata
            assert model_router.resolve_code_model("openai") == "kimi-k2.7-code"

    def test_fallback_to_alto_when_no_code_model(self):
        infos = {
            "general-model": _info(reasoning=True, context=128000, cost=1.0),
            "other-general": _info(reasoning=False, context=64000, cost=0.5),
        }
        with patch.object(model_router, "list_agentic_models", return_value=list(infos)), patch.object(
            model_router, "get_model_info", side_effect=lambda p, m: infos[m]
        ), patch.object(
            model_router, "resolve_alto_model", return_value="best-alto"
        ):
            assert model_router.resolve_code_model("openai") == "best-alto"

    def test_filters_pre_2026_code_models(self):
        infos = {
            "old-codex": SimpleNamespace(reasoning=True, context_window=128000, cost_input=1.0, cost_output=1.0, release_date="2025-01-01"),
            "new-code": _info(reasoning=True, context=128000, cost=1.0),
        }
        with patch.object(model_router, "list_agentic_models", return_value=list(infos)), patch.object(
            model_router, "get_model_info", side_effect=lambda p, m: infos[m]
        ):
            assert model_router.resolve_code_model("openai") == "new-code"


class TestResolveModel:
    def setup_method(self):
        model_router.clear_cache()

    def test_concrete_passes_through(self):
        assert model_router.resolve_model("openai", "gpt-5.5") == "gpt-5.5"

    def test_alto_resolves(self):
        with patch.object(model_router, "resolve_alto_model", return_value="best-model"):
            assert model_router.resolve_model("openai", "alto") == "best-model"
            assert model_router.resolve_model("openai", "") == "best-model"

    def test_fast_tier_resolves(self):
        with patch.object(model_router, "resolve_fast_model", return_value="fast-model"):
            assert model_router.resolve_model("openai", "alto", tier="fast") == "fast-model"

    def test_code_tier_resolves(self):
        with patch.object(model_router, "resolve_code_model", return_value="code-model"):
            assert model_router.resolve_model("openai", "alto", tier="code") == "code-model"

    def test_fixer_label_uses_code_catalog_route(self):
        with patch.object(model_router, "resolve_code_model", return_value="code-model"), patch.object(
            model_router, "resolve_alto_model", return_value="best-model"
        ):
            assert model_router.resolve_model("openai", "alto", agent_label="fixer") == "code-model"

    def test_code_tier_falls_back_to_alto_when_no_code_candidate(self):
        with patch.object(model_router, "resolve_code_model", return_value=""), patch.object(
            model_router, "resolve_alto_model", return_value="best-model"
        ):
            assert model_router.resolve_model("openai", "alto", tier="code") == "best-model"

    def test_classifier_uses_fast_catalog_route(self):
        with patch.object(model_router, "resolve_fast_model", return_value="fast-model"), patch.object(
            model_router, "resolve_alto_model", return_value="best-model"
        ):
            assert model_router.resolve_model("openai", "alto", agent_label="classifier") == "fast-model"

    def test_fast_falls_back_to_alto_when_no_fast_candidate(self):
        with patch.object(model_router, "resolve_fast_model", return_value=""), patch.object(
            model_router, "resolve_alto_model", return_value="best-model"
        ):
            assert model_router.resolve_model("openai", "alto", tier="fast") == "best-model"

    def test_specialists_use_alto_catalog_route(self):
        with patch.object(model_router, "resolve_alto_model", return_value="best-model"):
            assert model_router.resolve_model("openai", "alto", agent_label="operability") == "best-model"
            assert model_router.resolve_model("anthropic", "alto", agent_label="visual_a11y") == "best-model"
            assert model_router.resolve_model("gemini", "alto", agent_label="self_healing") == "best-model"


class TestTradeoffThreading:
    """O tradeoff custo/qualidade e decidido pelo modelo (complexity_router),
    nunca fixo -- ver complexity_router.classify_and_set_tradeoff. resolve_model
    le o valor corrente quando o chamador nao passa um explicito."""

    def setup_method(self):
        model_router.clear_cache()

    def test_reads_current_tradeoff_from_complexity_router_when_not_given(self):
        from backend.src.services import complexity_router

        complexity_router.set_current_tradeoff(8)
        try:
            with patch.object(model_router, "resolve_alto_model", return_value="m") as mock_alto:
                model_router.resolve_model("openai", "alto", agent_label="perceiver")
            mock_alto.assert_called_once_with("openai", False, False, 8)
        finally:
            complexity_router.set_current_tradeoff(complexity_router.DEFAULT_TRADEOFF)

    def test_explicit_tradeoff_overrides_complexity_router(self):
        from backend.src.services import complexity_router

        complexity_router.set_current_tradeoff(8)
        try:
            with patch.object(model_router, "resolve_alto_model", return_value="m") as mock_alto:
                model_router.resolve_model("openai", "alto", agent_label="perceiver", tradeoff=2)
            mock_alto.assert_called_once_with("openai", False, False, 2)
        finally:
            complexity_router.set_current_tradeoff(complexity_router.DEFAULT_TRADEOFF)

    def test_fast_tier_always_uses_tradeoff_9_regardless_of_classifier(self):
        """O classificador de complexidade em si (e o de frameworks) sao sempre
        baratos por design -- nao devem herdar o tradeoff da pagina analisada."""
        from backend.src.services import complexity_router

        complexity_router.set_current_tradeoff(0)  # complexidade alta classificada
        try:
            with patch.object(model_router, "resolve_fast_model", return_value=""), patch.object(
                model_router, "resolve_alto_model", return_value="fallback-model"
            ) as mock_alto:
                model_router.resolve_model("openai", "alto", tier="fast")
            mock_alto.assert_called_once_with("openai", False, False, 9)
        finally:
            complexity_router.set_current_tradeoff(complexity_router.DEFAULT_TRADEOFF)


class TestAgenticAutoCostRouting:
    """Roteamento de custo REAL entre providers (não só entre modelos de um
    provider já escolhido) -- ver Task #19 / AI_MODULE_SPEC.md § Pendências
    de arquitetura. Antes desta mudança, provider='agentic'/'auto' sempre
    escolhia o primeiro provider com API key presente numa ordem fixa,
    ignorando preço por completo."""

    def setup_method(self):
        model_router.clear_cache()

    def teardown_method(self):
        model_router.clear_cache()

    def test_low_tradeoff_keeps_historical_priority_order_ignoring_price(self):
        infos = {
            ("openai", "gpt-openai-best"): _info(reasoning=True, context=128000, cost=10.0),
            ("anthropic", "claude-cheap"): _info(reasoning=True, context=128000, cost=0.1),
        }
        models = {"openai": "gpt-openai-best", "anthropic": "claude-cheap"}
        with patch.object(model_router, "_available_auto_providers", return_value=["openai", "anthropic"]), \
             patch.object(model_router, "resolve_alto_model", side_effect=lambda p, *a: models[p]), \
             patch.object(model_router, "get_model_info", side_effect=lambda p, m: infos[(p, m)]):
            provider, model = model_router.resolve_model_and_provider("agentic", "alto", tradeoff=3)
        assert (provider, model) == ("openai", "gpt-openai-best")

    def test_high_tradeoff_picks_cheapest_across_all_available_providers(self):
        infos = {
            ("openai", "gpt-openai-best"): _info(reasoning=True, context=128000, cost=10.0),
            ("anthropic", "claude-cheap"): _info(reasoning=True, context=128000, cost=0.1),
        }
        models = {"openai": "gpt-openai-best", "anthropic": "claude-cheap"}
        with patch.object(model_router, "_available_auto_providers", return_value=["openai", "anthropic"]), \
             patch.object(model_router, "resolve_alto_model", side_effect=lambda p, *a: models[p]), \
             patch.object(model_router, "get_model_info", side_effect=lambda p, m: infos[(p, m)]):
            provider, model = model_router.resolve_model_and_provider("agentic", "alto", tradeoff=9)
        assert (provider, model) == ("anthropic", "claude-cheap")

    def test_mid_tradeoff_still_prefers_reasoning_capable_candidate(self):
        # anthropic e' mais barato mas sem reasoning; tradeoff medio (custo
        # favorecido mas < 8) ainda prefere o candidato com reasoning=True.
        infos = {
            ("openai", "gpt-reasoner"): _info(reasoning=True, context=128000, cost=5.0),
            ("anthropic", "claude-no-reason-cheap"): _info(reasoning=False, context=128000, cost=0.1),
        }
        models = {"openai": "gpt-reasoner", "anthropic": "claude-no-reason-cheap"}
        with patch.object(model_router, "_available_auto_providers", return_value=["openai", "anthropic"]), \
             patch.object(model_router, "resolve_alto_model", side_effect=lambda p, *a: models[p]), \
             patch.object(model_router, "get_model_info", side_effect=lambda p, m: infos[(p, m)]):
            provider, model = model_router.resolve_model_and_provider("agentic", "alto", tradeoff=5)
        assert (provider, model) == ("openai", "gpt-reasoner")

    def test_very_high_tradeoff_ignores_reasoning_goes_straight_to_cheapest(self):
        infos = {
            ("openai", "gpt-reasoner"): _info(reasoning=True, context=128000, cost=5.0),
            ("anthropic", "claude-no-reason-cheap"): _info(reasoning=False, context=128000, cost=0.1),
        }
        models = {"openai": "gpt-reasoner", "anthropic": "claude-no-reason-cheap"}
        with patch.object(model_router, "_available_auto_providers", return_value=["openai", "anthropic"]), \
             patch.object(model_router, "resolve_alto_model", side_effect=lambda p, *a: models[p]), \
             patch.object(model_router, "get_model_info", side_effect=lambda p, m: infos[(p, m)]):
            provider, model = model_router.resolve_model_and_provider("agentic", "alto", tradeoff=8)
        assert (provider, model) == ("anthropic", "claude-no-reason-cheap")

    def test_no_providers_available_falls_back_to_best_effort_order(self):
        with patch.object(model_router, "_available_auto_providers", return_value=[]), \
             patch.object(model_router, "resolve_alto_model", side_effect=lambda p, *a: "m-openai" if p == "openai" else ""):
            provider, model = model_router.resolve_model_and_provider("agentic", "alto", tradeoff=3)
        assert (provider, model) == ("openai", "m-openai")

    def test_no_candidate_resolves_returns_empty_pair(self):
        with patch.object(model_router, "_available_auto_providers", return_value=["openai"]), \
             patch.object(model_router, "resolve_alto_model", return_value=""):
            provider, model = model_router.resolve_model_and_provider("agentic", "alto", tradeoff=3)
        assert (provider, model) == ("", "")

    def test_fast_tier_also_compares_cost_across_providers(self):
        infos = {
            ("openai", "gpt-fast-pricey"): _info(reasoning=False, context=8000, cost=1.0),
            ("gemini", "flash-cheap"): _info(reasoning=False, context=8000, cost=0.05),
        }
        models = {"openai": "gpt-fast-pricey", "gemini": "flash-cheap"}
        with patch.object(model_router, "_available_auto_providers", return_value=["openai", "gemini"]), \
             patch.object(model_router, "resolve_fast_model", side_effect=lambda p, *a: models[p]), \
             patch.object(model_router, "get_model_info", side_effect=lambda p, m: infos[(p, m)]):
            provider, model = model_router.resolve_model_and_provider("agentic", "alto", tier="fast")
        assert (provider, model) == ("gemini", "flash-cheap")

    def test_subscription_based_provider_treated_as_cheapest_regardless_of_placeholder_cost(self):
        """Ollama LOCAL roda o peso na própria máquina do usuário -- não há
        laboratório terceiro cobrando por chamada, então não existe $/token
        real a pesquisar (hardware/eletricidade já pago, não billing por
        chamada). Mesmo com um cost_input alto no info mockado (simulando uma
        placeholder), o provider local deve vencer o ranking por custo
        (custo marginal ~$0 por chamada extra).

        NOTA (pesquisa 2026-08-11, ollama.com/pricing + ollama.com/cloud,
        confirmado em duas buscas independentes): "ollama-cloud" NÃO tem mais
        esse tratamento -- a Ollama Cloud não publica $/token próprio (cobra
        por assinatura/GPU-time), mas os modelos que ela hospeda são pesos de
        laboratórios terceiros (Moonshot/Kimi, Zhipu/GLM, MiniMax, DeepSeek,
        Qwen) que TÊM preço oficial publicado -- usado no catálogo
        (agent/models_dev.py) em vez de um placeholder ou de custo zero."""
        infos = {
            ("openai", "gpt-mid"): _info(reasoning=True, context=128000, cost=1.0),
            ("ollama", "local-model"): _info(reasoning=True, context=128000, cost=999.0),
        }
        models = {"openai": "gpt-mid", "ollama": "local-model"}
        with patch.object(model_router, "_available_auto_providers", return_value=["openai", "ollama"]), \
             patch.object(model_router, "resolve_alto_model", side_effect=lambda p, *a: models[p]), \
             patch.object(model_router, "get_model_info", side_effect=lambda p, m: infos[(p, m)]):
            provider, model = model_router.resolve_model_and_provider("agentic", "alto", tradeoff=9)
        assert (provider, model) == ("ollama", "local-model")

    def test_concrete_model_skips_cost_routing_entirely(self):
        """Modelo concreto (não "Alto") não tem preço a comparar entre
        alternativas -- só precisa achar QUAL provider disponível tem esse
        modelo, comportamento antigo via resolve_provider preservado."""
        with patch.object(model_router, "_available_auto_providers") as mock_available:
            provider, model = model_router.resolve_model_and_provider("openai", "gpt-5.5-custom")
        mock_available.assert_not_called()
        assert provider == "openai"
        assert model == "gpt-5.5-custom"


class TestOpenCodeGoFallback:
    def setup_method(self):
        model_router.clear_cache()

    def teardown_method(self):
        model_router.clear_cache()

    def test_ollama_without_eligible_model_routes_to_opencode_go_when_configured(self):
        with patch.object(model_router, "resolve_model", return_value=""), patch.dict(
            "os.environ", {"OPENCODE_GO_API_KEY": "test-key"}, clear=False
        ):
            provider, model = model_router.resolve_model_and_provider("ollama-cloud", "alto")
        assert (provider, model) == ("opencode-go", "gpt-5.6-luna")

    def test_ollama_without_eligible_model_does_not_route_without_opt_in_key(self):
        with patch.object(model_router, "resolve_model", return_value=""), patch.dict(
            "os.environ", {}, clear=True
        ):
            provider, model = model_router.resolve_model_and_provider("ollama-cloud", "alto")
        assert (provider, model) == ("ollama-cloud", "")

    def test_structured_outputs_from_ollama_cloud_always_use_gpt_luna(self):
        with patch.dict(
            "os.environ", {"OPENCODE_GO_API_KEY": "test-key"}, clear=False
        ):
            provider, model = model_router.resolve_model_and_provider(
                "ollama-cloud",
                "alto",
                needs_structured_outputs=True,
            )
        assert (provider, model) == ("opencode-go", "gpt-5.6-luna")

    def test_structured_outputs_flag_does_not_change_ollama_local(self):
        with patch.object(model_router, "resolve_model", return_value="local-model"):
            provider, model = model_router.resolve_model_and_provider(
                "ollama",
                "alto",
                needs_structured_outputs=True,
            )
        assert (provider, model) == ("ollama", "local-model")


class TestStructuredOutputModelChain:
    """Cadeia de fallback verificada (auditoria
    docs/auditoria-prompt-caching-structured-output-2026-08-26.md): gpt-5.6-luna
    e o primeiro (Responses API, prompt caching 99,9%), os demais confirmam
    structured output + prompt caching real via Chat Completions."""

    def setup_method(self):
        model_router.clear_cache()

    def teardown_method(self):
        model_router.clear_cache()

    def test_empty_without_opt_in_key(self):
        with patch.dict("os.environ", {}, clear=True):
            assert model_router.resolve_structured_output_chain() == []

    def test_full_chain_when_configured(self):
        with patch.dict("os.environ", {"OPENCODE_GO_API_KEY": "test-key"}, clear=False):
            chain = model_router.resolve_structured_output_chain()
        assert chain == model_router.STRUCTURED_OUTPUT_MODEL_CHAIN
        assert chain[0] == "gpt-5.6-luna"
        assert chain[0] == model_router.OPENCODE_GO_MODEL

    def test_chain_has_no_duplicate_models(self):
        assert len(model_router.STRUCTURED_OUTPUT_MODEL_CHAIN) == len(
            set(model_router.STRUCTURED_OUTPUT_MODEL_CHAIN)
        )

    def test_recognizes_either_env_var_name(self):
        with patch.dict("os.environ", {"OPENCODE_API_KEY": "test-key"}, clear=True):
            assert model_router.resolve_structured_output_chain() == model_router.STRUCTURED_OUTPUT_MODEL_CHAIN
