import os
from pathlib import Path

import pytest

from backend.src.config.settings import get_settings
from backend.src.security.secret_store import load_secrets


@pytest.fixture(autouse=True)
def _isolated_env_file(tmp_path, monkeypatch):
    """The settings route writes to the relative path "backend/.env" (or ".env").
    Running against the real project would mutate the developer's actual .env file
    (which holds real API keys) -- chdir into an isolated tmp directory so every test
    here writes its own throwaway file instead.

    `Settings.secret_key` has no default, so if anything busts get_settings()'s lru_cache
    while chdir'd here (e.g. the /settings POST route calls cache_clear()), the next
    get_settings() call would fail to find SECRET_KEY (no .env in tmp_path) even though
    it's set for the real project -- pin it via env var, which BaseSettings reads
    regardless of cwd, so a cache rebuild mid-test still succeeds."""
    monkeypatch.setenv("SECRET_KEY", "test-secret-key")
    monkeypatch.setenv("QA_SECRET_STORE_PATH", str(tmp_path / "secrets.json"))
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


class TestSettingsRouteInjection:
    def test_settings_without_trailing_slash_does_not_redirect(self, client):
        resp = client.get("/settings", follow_redirects=False)
        assert resp.status_code == 200

    def test_settings_post_without_trailing_slash_does_not_redirect(self, client):
        resp = client.post("/settings", json={"llm_provider": "openai"}, follow_redirects=False)
        assert resp.status_code == 200

    def test_newline_in_llm_provider_is_rejected(self, client):
        resp = client.post("/settings/", json={
            "llm_provider": "openai\nGITHUB_TOKEN=attacker-controlled",
        })
        assert resp.status_code == 400
        assert "quebras de linha" in resp.json()["detail"]

    def test_newline_in_llm_api_key_is_rejected(self, client):
        resp = client.post("/settings/", json={
            "llm_provider": "openai",
            "llm_api_key": "sk-real\nEXTRA_VAR=injected",
        })
        assert resp.status_code == 400

    def test_carriage_return_is_also_rejected(self, client):
        resp = client.post("/settings/", json={
            "llm_provider": "openai",
            "llm_model": "gpt-x\r\nINJECTED=1",
        })
        assert resp.status_code == 400

    def test_normal_update_still_works_and_env_file_has_no_injected_lines(self, client):
        resp = client.post("/settings/", json={
            "llm_provider": "openai",
            "llm_api_key": "sk-real-key",
            "llm_model": "alto",
        })
        assert resp.status_code == 200
        env_path = "backend/.env" if os.path.exists("backend/.env") else ".env"
        with open(env_path, encoding="utf-8") as f:
            content = f.read()
        assert "LLM_PROVIDER=openai" in content
        assert "sk-real-key" not in content
        assert load_secrets()["LLM_API_KEY"] == "sk-real-key"
        assert "sk-real-key" not in Path(os.environ["QA_SECRET_STORE_PATH"]).read_text(encoding="utf-8")

    def test_masked_key_resubmission_is_ignored_not_overwritten(self, client):
        client.post("/settings/", json={"llm_provider": "openai", "llm_api_key": "sk-real-key"})
        resp = client.post("/settings/", json={
            "llm_provider": "openai",
            "llm_api_key": "•" * 24,
        })
        assert resp.status_code == 200
        env_path = "backend/.env" if os.path.exists("backend/.env") else ".env"
        with open(env_path, encoding="utf-8") as f:
            content = f.read()
        assert "sk-real-key" not in content
        assert "•" not in content
        assert load_secrets()["LLM_API_KEY"] == "sk-real-key"


class TestChatLlmOverrides:
    """Regression: chat_llm_* overrides existed as backend Settings fields
    (used by chat_llm_config for the chat agent) but had no route exposing
    them at all -- the UI had no way to ever set them."""

    def test_get_settings_exposes_chat_llm_fields(self, client):
        resp = client.get("/settings/")
        assert resp.status_code == 200
        body = resp.json()
        assert "chat_llm_provider" in body
        assert "chat_llm_model" in body
        assert "chat_llm_base_url" in body
        assert "has_chat_llm_api_key" in body

    def test_saving_chat_llm_overrides_persists_to_env_file(self, client):
        resp = client.post("/settings/", json={
            "llm_provider": "openai",
            "chat_llm_provider": "anthropic",
            "chat_llm_api_key": "sk-chat-real-key",
            "chat_llm_model": "claude-opus-5",
            "chat_llm_base_url": "https://api.anthropic.com",
        })
        assert resp.status_code == 200

        env_path = "backend/.env" if os.path.exists("backend/.env") else ".env"
        with open(env_path, encoding="utf-8") as f:
            content = f.read()
        assert "CHAT_LLM_PROVIDER=anthropic" in content
        assert "sk-chat-real-key" not in content
        assert load_secrets()["CHAT_LLM_API_KEY"] == "sk-chat-real-key"
        assert "CHAT_LLM_MODEL=claude-opus-5" in content
        assert "CHAT_LLM_BASE_URL=https://api.anthropic.com" in content

        follow_up = client.get("/settings/")
        assert follow_up.json()["chat_llm_provider"] == "anthropic"
        assert follow_up.json()["has_chat_llm_api_key"] is True

    def test_clearing_chat_llm_provider_removes_it_from_env_file(self, client):
        client.post("/settings/", json={
            "llm_provider": "openai",
            "chat_llm_provider": "anthropic",
            "chat_llm_api_key": "sk-chat-real-key",
        })
        resp = client.post("/settings/", json={
            "llm_provider": "openai",
            "chat_llm_provider": "",
            "chat_llm_api_key": "",
        })
        assert resp.status_code == 200

        env_path = "backend/.env" if os.path.exists("backend/.env") else ".env"
        with open(env_path, encoding="utf-8") as f:
            content = f.read()
        assert "CHAT_LLM_PROVIDER=" not in content
        assert "CHAT_LLM_API_KEY=" not in content

    def test_newline_in_chat_llm_model_is_rejected(self, client):
        resp = client.post("/settings/", json={
            "llm_provider": "openai",
            "chat_llm_model": "claude\nINJECTED=1",
        })
        assert resp.status_code == 400


class TestServiceKeyRouteInjection:
    def test_newline_in_service_name_is_rejected(self, client):
        resp = client.post("/settings/service-key", json={
            "service_name": "github\nOTHER=1",
            "api_key": "token-123",
        })
        assert resp.status_code == 400

    def test_newline_in_api_key_is_rejected(self, client):
        resp = client.post("/settings/service-key", json={
            "service_name": "github",
            "api_key": "token\nOTHER=1",
        })
        assert resp.status_code == 400

    def test_unmapped_service_name_with_bad_characters_is_rejected(self, client):
        resp = client.post("/settings/service-key", json={
            "service_name": "weird service!! name",
            "api_key": "token-123",
        })
        assert resp.status_code == 400

    def test_known_service_still_updates_normally(self, client):
        resp = client.post("/settings/service-key", json={
            "service_name": "github",
            "api_key": "ghp_realtoken",
        })
        assert resp.status_code == 200
        assert resp.json()["env_var"] == "GITHUB_TOKEN"
        env_path = "backend/.env" if os.path.exists("backend/.env") else ".env"
        content = Path(env_path).read_text(encoding="utf-8") if Path(env_path).exists() else ""
        assert "ghp_realtoken" not in content
        assert load_secrets()["GITHUB_TOKEN"] == "ghp_realtoken"
