"""Real-eval configuration is testable without spending provider tokens."""
import pytest

from tests.backend.real_llm import conftest as config


def test_keys_are_selected_per_provider(monkeypatch):
    monkeypatch.setenv("FACTORY_API_KEY", "factory-canary")
    monkeypatch.setenv("OLLAMA_API_KEY", "ollama-canary")
    assert config.selected_key("factory") == "factory-canary"
    assert config.selected_key("ollama-cloud") == "ollama-canary"
    with pytest.raises(ValueError):
        config.selected_key("unknown")


def test_partial_result_cannot_pass_real_pipeline_gate():
    from backend.src.shared.models import AgentResult

    partial = AgentResult(agent="orchestrator", success=True,
                          data={"complete": False, "warning": "reviewer failed",
                                "agent_metrics": [{"success": False}]})
    with pytest.raises(AssertionError, match="reviewer failed"):
        config.assert_complete_result(partial)


def test_factory_fixture_restores_environment_and_disables_fallback(monkeypatch):
    from backend.src.config.settings import get_settings

    monkeypatch.setattr(config, "REAL_PROVIDER", "factory")
    monkeypatch.setenv("FACTORY_API_KEY", "factory-canary")
    monkeypatch.setenv("LLM_PROVIDER", "ollama-cloud")
    monkeypatch.setenv("LLM_MODEL", "original-model")
    fixture = config._real_provider.__wrapped__()
    next(fixture)
    settings = get_settings()
    assert settings.llm_provider == "factory"
    assert settings.llm_api_key == "factory-canary"
    assert settings.llm_model == "auto"
    assert settings.build_fallback_model() == {}
    assert not settings.a11y_response_cache_enabled
    with pytest.raises(StopIteration):
        next(fixture)
    assert get_settings().llm_model == "original-model"
