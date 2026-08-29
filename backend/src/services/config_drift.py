"""Deteccao de configuration drift entre o contrato documentado (`.env.example`)
e o ambiente vivo do processo.

Cobre a classe de bug encontrada em 2026-08-01: uma variavel de override de
endpoint (ex.: ANTHROPIC_BASE_URL) setada no shell/ambiente por outra
ferramenta, nao declarada em `backend/.env`, muda silenciosamente o endpoint
resolvido por `agent/models_dev.py::_resolve_endpoint` e `run_agent.py` sem
nenhum aviso -- o comportamento em runtime diverge do que o `.env` do projeto
documenta. `detect_config_drift()` e um check informativo (nunca levanta
excecao): o objetivo e aparecer no log, nao derrubar o processo por causa do
ambiente de outra ferramenta na maquina do dev.
"""

import logging
import os
import re
from pathlib import Path

logger = logging.getLogger(__name__)

_ENV_KEY_RE = re.compile(r"^([A-Z][A-Z0-9_]*)=")

# Vars de override de endpoint reconhecidas pelos providers suportados
# (agent/models_dev.py::_resolve_endpoint, run_agent.py::_run_openai/_run_chat_completions).
# Setadas no ambiente do processo sem estarem em backend/.env = drift silencioso.
PROVIDER_BASE_URL_VARS = (
    "OPENAI_BASE_URL",
    "ANTHROPIC_BASE_URL",
    "GEMINI_BASE_URL",
    "XAI_BASE_URL",
    "OLLAMA_BASE_URL",
    "OLLAMA_CLOUD_BASE_URL",
)

# Prefixos de variaveis de configuracao do proprio projeto -- fora desse
# escopo, nao ha como distinguir "nao documentada" de "variavel de outra
# ferramenta na maquina do dev" (ex.: PATH, JAVA_HOME), entao nao reportamos.
_PROJECT_ENV_PREFIXES = ("LLM_", "CHAT_LLM_", "QA_", "A11Y_", "AGENT_TIMEOUT_")


def _parse_documented_keys(path: Path) -> set[str]:
    """Chaves documentadas em um arquivo .env-like, incluindo linhas comentadas
    (`# CHAVE=...`) -- o `.env.example` do projeto documenta opcionais assim."""
    if not path.is_file():
        return set()
    keys: set[str] = set()
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        stripped = line.strip().lstrip("#").strip()
        match = _ENV_KEY_RE.match(stripped)
        if match:
            keys.add(match.group(1))
    return keys


def _parse_active_keys(path: Path) -> set[str]:
    """Chaves ativas (nao comentadas) em um arquivo .env real."""
    if not path.is_file():
        return set()
    keys: set[str] = set()
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = _ENV_KEY_RE.match(stripped)
        if match:
            keys.add(match.group(1))
    return keys


def detect_config_drift(project_root: Path | None = None) -> list[str]:
    """Compara `.env.example` (contrato) x `backend/.env` x ambiente do processo.

    Devolve avisos legiveis (lista vazia se nao houver drift). Duas checagens:
    1. Vars de override de endpoint de provider ativas no ambiente mas
       ausentes de `backend/.env` -- exatamente a classe de bug que causou
       falha de isolamento em `test_models_live_catalog.py`.
    2. Vars com prefixo do projeto (`LLM_`, `QA_`, ...) presentes em
       `backend/.env` mas nao documentadas em `.env.example` -- config
       obsoleta ou nunca documentada.
    """
    root = project_root or Path(__file__).resolve().parents[4]
    documented = _parse_documented_keys(root / ".env.example")
    dotenv_keys = _parse_active_keys(root / "backend" / ".env")
    warnings: list[str] = []

    for var in PROVIDER_BASE_URL_VARS:
        if os.getenv(var) and var not in dotenv_keys:
            warnings.append(
                f"{var} esta definida no ambiente do processo mas nao em "
                f"backend/.env -- o endpoint resolvido para o provider "
                f"correspondente diverge silenciosamente do que o .env do "
                f"projeto documenta. Declare em backend/.env se for "
                f"intencional, ou remova do ambiente."
            )

    for var in sorted(dotenv_keys - documented):
        if var.startswith(_PROJECT_ENV_PREFIXES):
            warnings.append(
                f"{var} esta definida em backend/.env mas nao aparece em "
                f".env.example -- pode ser configuracao obsoleta ou nunca "
                f"documentada."
            )

    return warnings


def log_config_drift() -> None:
    """Loga cada aviso de drift como WARNING. Chamado no startup do backend."""
    for warning in detect_config_drift():
        logger.warning("[ConfigDrift] %s", warning)
