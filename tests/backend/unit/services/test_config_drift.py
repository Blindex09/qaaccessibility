"""Testes de Configuration Drift Detection (services/config_drift.py).

Cobre a classe de bug real encontrada em 2026-08-01: ANTHROPIC_BASE_URL setada
no ambiente do processo (por outra ferramenta na maquina do dev) e nao
declarada em backend/.env, mudando silenciosamente o endpoint resolvido.
"""

from pathlib import Path

from backend.src.services.config_drift import detect_config_drift


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


class TestProviderBaseUrlDrift:
    def test_flags_undeclared_base_url_override(self, tmp_path, monkeypatch):
        _write(tmp_path / ".env.example", "LLM_PROVIDER=\nLLM_API_KEY=x\n")
        _write(tmp_path / "backend" / ".env", "LLM_PROVIDER=anthropic\n")
        monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com")

        warnings = detect_config_drift(project_root=tmp_path)

        assert any("ANTHROPIC_BASE_URL" in w for w in warnings)

    def test_no_warning_when_base_url_declared_in_dotenv(self, tmp_path, monkeypatch):
        _write(tmp_path / ".env.example", "# ANTHROPIC_BASE_URL=\n")
        _write(tmp_path / "backend" / ".env", "ANTHROPIC_BASE_URL=https://custom.proxy\n")
        monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://custom.proxy")

        warnings = detect_config_drift(project_root=tmp_path)

        assert not any("ANTHROPIC_BASE_URL" in w for w in warnings)

    def test_no_warning_when_env_var_absent(self, tmp_path, monkeypatch):
        _write(tmp_path / ".env.example", "LLM_PROVIDER=\n")
        _write(tmp_path / "backend" / ".env", "LLM_PROVIDER=openai\n")
        for var in (
            "OPENAI_BASE_URL",
            "ANTHROPIC_BASE_URL",
            "GEMINI_BASE_URL",
            "XAI_BASE_URL",
            "OLLAMA_BASE_URL",
            "OLLAMA_CLOUD_BASE_URL",
        ):
            monkeypatch.delenv(var, raising=False)

        assert detect_config_drift(project_root=tmp_path) == []


class TestUndocumentedProjectVars:
    def test_flags_undocumented_project_prefixed_key(self, tmp_path):
        _write(tmp_path / ".env.example", "LLM_PROVIDER=\nLLM_API_KEY=x\n")
        _write(tmp_path / "backend" / ".env", "LLM_PROVIDER=openai\nLLM_SOME_RETIRED_FLAG=1\n")

        warnings = detect_config_drift(project_root=tmp_path)

        assert any("LLM_SOME_RETIRED_FLAG" in w for w in warnings)

    def test_ignores_keys_outside_project_prefixes(self, tmp_path):
        _write(tmp_path / ".env.example", "LLM_PROVIDER=\n")
        _write(tmp_path / "backend" / ".env", "LLM_PROVIDER=openai\nSOME_UNRELATED_TOOL_VAR=1\n")

        warnings = detect_config_drift(project_root=tmp_path)

        assert not any("SOME_UNRELATED_TOOL_VAR" in w for w in warnings)

    def test_documented_commented_key_is_not_flagged(self, tmp_path):
        _write(tmp_path / ".env.example", "# QA_API_TOKEN=\n")
        _write(tmp_path / "backend" / ".env", "QA_API_TOKEN=some-token\n")

        warnings = detect_config_drift(project_root=tmp_path)

        assert not any("QA_API_TOKEN" in w for w in warnings)


class TestNoConfigFiles:
    def test_returns_empty_list_when_no_files_exist(self, tmp_path, monkeypatch):
        # Isola de BASE_URL reais do ambiente do desenvolvedor -- mesma licao do
        # test_models_live_catalog.py::TestEndpointResolution.
        for var in (
            "OPENAI_BASE_URL",
            "ANTHROPIC_BASE_URL",
            "GEMINI_BASE_URL",
            "XAI_BASE_URL",
            "OLLAMA_BASE_URL",
            "OLLAMA_CLOUD_BASE_URL",
        ):
            monkeypatch.delenv(var, raising=False)

        assert detect_config_drift(project_root=tmp_path) == []
