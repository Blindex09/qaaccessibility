"""Testes do catálogo dinâmico de modelos (live-first, static-fallback).

Valida que fetch_live_models consulta as APIs reais e que list_agentic_models
prefere o catálogo live com fallback gracioso para o estático offline.
Padrão 2026: live-first, static-fallback (confirmado nas docs oficiais de
OpenAI, Anthropic, Gemini, xAI e Ollama em 2026-07-28).
"""

from unittest.mock import patch

from agent import models_dev

# --------------------------------------------------------------------------- #
# fetch_live_models — consulta as APIs reais
# --------------------------------------------------------------------------- #


class _FakeResponse:
    """Mock de requests.Response para testes do catálogo live."""

    def __init__(self, payload: dict, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code

    def json(self) -> dict:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class TestFetchLiveModels:
    def setup_method(self):
        models_dev.clear_live_cache()

    def teardown_method(self):
        models_dev.clear_live_cache()

    def test_openai_parse_extracts_model_ids(self):
        fake = _FakeResponse({"data": [
            {"id": "gpt-5.6-sol"},
            {"id": "gpt-5.6-luna"},
            {"id": "gpt-5.6-terra"},
        ]})
        with patch("agent.models_dev.requests.get", return_value=fake):
            result = models_dev.fetch_live_models("openai", api_key="test-key")
        assert "gpt-5.6-sol" in result
        assert "gpt-5.6-luna" in result
        # Todos tool-capable (OpenAI-compatible assume True)
        assert all(info.tool_call for info in result.values())

    def test_live_parser_excludes_preview_models(self):
        fake = _FakeResponse({"data": [
            {"id": "gpt-5.6-luna-preview"},
            {"id": "gpt-5.6-luna"},
        ]})
        with patch("agent.models_dev.requests.get", return_value=fake):
            result = models_dev.fetch_live_models("openai", api_key="test-key")
        assert "gpt-5.6-luna-preview" not in result
        assert "gpt-5.6-luna" in result

    def test_anthropic_parse_extracts_capabilities(self):
        fake = _FakeResponse({"data": [
            {
                "id": "claude-opus-4-6",
                "display_name": "Claude Opus 4.6",
                "max_input_tokens": 200000,
                "created_at": "2026-02-04T00:00:00Z",
                "capabilities": {
                    "thinking": {"supported": True},
                    "structured_outputs": {"supported": True},
                },
            },
        ]})
        with patch("agent.models_dev.requests.get", return_value=fake):
            result = models_dev.fetch_live_models("anthropic", api_key="test-key")
        info = result["claude-opus-4-6"]
        assert info.reasoning is True
        assert info.tool_call is True
        assert info.context_window == 200000

    def test_gemini_parse_extracts_token_limits(self):
        fake = _FakeResponse({"models": [
            {
                "name": "models/gemini-3.6-flash",
                "displayName": "Gemini 3.6 Flash",
                "inputTokenLimit": 1000000,
                "supportedGenerationMethods": ["generateContent", "embedContent"],
                "thinking": True,
            },
        ]})
        with patch("agent.models_dev.requests.get", return_value=fake):
            result = models_dev.fetch_live_models("gemini", api_key="test-key")
        info = result["gemini-3.6-flash"]
        assert info.context_window == 1000000
        assert info.tool_call is True  # generateContent presente
        assert info.reasoning is True

    def test_returns_empty_on_network_failure(self):
        with patch("agent.models_dev.requests.get", side_effect=ConnectionError("offline")):
            result = models_dev.fetch_live_models("openai", api_key="test-key")
        assert result == {}

    def test_returns_empty_for_unknown_provider(self):
        assert models_dev.fetch_live_models("unknown-provider") == {}

    def test_caches_live_catalog_within_ttl(self):
        call_count = [0]
        fake = _FakeResponse({"data": [{"id": "gpt-5.6"}]})

        def counting_get(*args, **kwargs):
            call_count[0] += 1
            return fake

        with patch("agent.models_dev.requests.get", side_effect=counting_get):
            models_dev.fetch_live_models("openai", api_key="k")
            models_dev.fetch_live_models("openai", api_key="k")
            models_dev.fetch_live_models("openai", api_key="k")
        # Cache: só 1 chamada de rede para 3 invocações
        assert call_count[0] == 1

    def test_clear_live_cache_invalidates(self):
        call_count = [0]
        fake = _FakeResponse({"data": [{"id": "gpt-5.6"}]})

        def counting_get(*args, **kwargs):
            call_count[0] += 1
            return fake

        with patch("agent.models_dev.requests.get", side_effect=counting_get):
            models_dev.fetch_live_models("openai", api_key="k")
            models_dev.clear_live_cache()
            models_dev.fetch_live_models("openai", api_key="k")
        assert call_count[0] == 2  # cache limpo -> nova chamada


# --------------------------------------------------------------------------- #
# list_agentic_models / get_model_info — live-first, static-fallback
# --------------------------------------------------------------------------- #


class TestLiveFirstStaticFallback:
    def setup_method(self):
        models_dev.clear_live_cache()

    def teardown_method(self):
        models_dev.clear_live_cache()

    def test_list_prefers_live_when_available(self):
        fake = _FakeResponse({"data": [{"id": "live-only-model"}]})
        with patch("agent.models_dev.requests.get", return_value=fake):
            models_dev.clear_live_cache()
            result = models_dev.list_agentic_models("openai")
        # Live tem 1 modelo; estático tem vários — deve retornar o live
        assert "live-only-model" in result
        assert len(result) == 1

    def test_list_falls_back_to_static_when_live_empty(self):
        with patch("agent.models_dev.requests.get", side_effect=ConnectionError("offline")):
            result = models_dev.list_agentic_models("openai")
        # Fallback: catálogo estático tem modelos OpenAI
        assert len(result) > 0
        assert "gpt-5.6-sol" in result

    def test_get_model_info_prefers_live(self):
        fake = _FakeResponse({"data": [{"id": "gpt-5.6-sol"}]})
        with patch("agent.models_dev.requests.get", return_value=fake):
            models_dev.clear_live_cache()
            info = models_dev.get_model_info("openai", "gpt-5.6-sol")
        assert info is not None
        assert info.id == "gpt-5.6-sol"

    def test_get_model_info_falls_back_to_static(self):
        with patch("agent.models_dev.requests.get", side_effect=ConnectionError("offline")):
            info = models_dev.get_model_info("openai", "gpt-5.6-sol")
        assert info is not None
        assert info.id == "gpt-5.6-sol"

    def test_get_model_info_returns_none_for_truly_unknown(self):
        with patch("agent.models_dev.requests.get", side_effect=ConnectionError("offline")):
            info = models_dev.get_model_info("openai", "totally-nonexistent-model")
        assert info is None


# --------------------------------------------------------------------------- #
# Resolução de endpoint e auth (contrato)
# --------------------------------------------------------------------------- #


class TestEndpointResolution:
    def _clear_base_url_env(self, monkeypatch):
        # Isola de BASE_URL reais do ambiente do desenvolvedor (ex.: ANTHROPIC_BASE_URL
        # setado por outra ferramenta local) -- sem isso, o teste valida o env da
        # máquina, não o default do código.
        for var in (
            "OPENAI_BASE_URL",
            "ANTHROPIC_BASE_URL",
            "GEMINI_BASE_URL",
            "XAI_BASE_URL",
            "OLLAMA_CLOUD_BASE_URL",
            "OLLAMA_BASE_URL",
        ):
            monkeypatch.delenv(var, raising=False)

    def test_openai_default_endpoint(self, monkeypatch):
        self._clear_base_url_env(monkeypatch)
        assert models_dev._resolve_endpoint("openai", None) == "https://api.openai.com/v1/models"

    def test_anthropic_default_endpoint(self, monkeypatch):
        self._clear_base_url_env(monkeypatch)
        assert models_dev._resolve_endpoint("anthropic", None) == "https://api.anthropic.com/v1/models"

    def test_gemini_default_endpoint(self, monkeypatch):
        self._clear_base_url_env(monkeypatch)
        assert "generativelanguage.googleapis.com/v1beta/models" in models_dev._resolve_endpoint("gemini", None)

    def test_xai_default_endpoint(self, monkeypatch):
        self._clear_base_url_env(monkeypatch)
        assert models_dev._resolve_endpoint("xai", None) == "https://api.x.ai/v1/models"

    def test_custom_base_url_override(self):
        assert models_dev._resolve_endpoint("openai", "https://custom.proxy/v1/models") == "https://custom.proxy/v1/models"

    def test_unknown_provider_returns_none(self):
        assert models_dev._resolve_endpoint("unknown", None) is None


class TestAuthHeaders:
    def test_openai_uses_bearer(self):
        headers = models_dev._resolve_auth_header("openai", "sk-test")
        assert headers["Authorization"] == "Bearer sk-test"

    def test_anthropic_uses_x_api_key(self):
        headers = models_dev._resolve_auth_header("anthropic", "sk-ant")
        assert headers["x-api-key"] == "sk-ant"
        assert headers["anthropic-version"] == "2023-06-01"

    def test_gemini_no_auth_header(self):
        headers = models_dev._resolve_auth_header("gemini", "key")
        # Gemini usa query param, não header de auth
        assert "Authorization" not in headers
        assert "x-api-key" not in headers

    def test_no_key_no_auth(self, monkeypatch):
        # Garante que nenhuma OPENAI_API_KEY do ambiente interfere
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
        headers = models_dev._resolve_auth_header("openai", None)
        assert "Authorization" not in headers
