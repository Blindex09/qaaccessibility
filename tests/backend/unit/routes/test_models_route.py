from unittest.mock import patch


class TestModelsRoute:
    def test_lists_six_chat_providers_with_models(self, client):
        from types import SimpleNamespace
        mock_info = SimpleNamespace(release_date="2026-01-01")
        with patch("agent.models_dev.fetch_models_dev", return_value={}), patch(
            "agent.models_dev.list_agentic_models",
            side_effect=lambda p: [f"{p}-a", f"{p}-b"] if p != "agentic" else [],
        ), patch(
            "agent.models_dev.get_model_info",
            return_value=mock_info
        ):
            resp = client.get("/models")

        assert resp.status_code == 200
        data = resp.json()
        ids = [p["id"] for p in data["providers"]]
        # "agentic" (lógico) vem primeiro; depois os 5 providers concretos
        assert ids == ["agentic", "openai", "anthropic", "gemini", "xai", "ollama-cloud"]
        assert "Groq" not in [p["label"] for p in data["providers"]]
        # "agentic" é um provider lógico: só expõe "alto", sem modelos concretos
        agentic = data["providers"][0]
        assert agentic["id"] == "agentic"
        assert agentic["models"] == ["alto"]
        # os providers concretos vêm depois com modelos
        first_concrete = data["providers"][1]
        assert first_concrete["id"] == "openai"
        assert first_concrete["models"][0] == "alto"

    def test_resilient_when_catalog_fails(self, client):
        with patch("agent.models_dev.fetch_models_dev", side_effect=RuntimeError("offline")), patch(
            "agent.models_dev.list_agentic_models", side_effect=RuntimeError("no data")
        ), patch(
            "backend.src.services.ollama_cloud_adapter.discover_ollama_cloud_descriptors", side_effect=RuntimeError("no ollama data")
        ):
            resp = client.get("/models")
        assert resp.status_code == 200
        # Falha graceful -> sem concretos, mas "alto" continua disponivel
        # (o servidor resolve em tempo de chamada; sem catalogo cai no default).
        assert all(p["models"] == ["alto"] for p in resp.json()["providers"])
