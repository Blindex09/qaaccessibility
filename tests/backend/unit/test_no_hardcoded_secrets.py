"""Regressao: nenhuma credencial de provider embutida em arquivo versionado.

Bug real corrigido: cinco scripts em `scripts/` traziam a mesma chave da Ollama
Cloud como fallback literal --

    API_KEY = os.getenv("OLLAMA_CLOUD_API_KEY") or os.getenv(...) or "<chave>"

-- comitada e publica no historico do repositorio. O hook `detect-private-key`
do pre-commit nao pega isso: ele procura blocos de chave privada PEM, nao
credenciais de API. Este teste fecha essa lacuna dentro do gate de CI.

Se este teste falhar: NAO basta apagar o literal. A chave ja esta no historico
do git a partir do commit que a introduziu, entao ela precisa ser ROTACIONADA
no provider. Remover do working tree so impede o proximo vazamento.
"""

import re
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]

# Formato "<32 hex>.<sufixo>" -- o das chaves da Ollama Cloud, e o mesmo de
# varios outros providers que emitem id publico + segredo separados por ponto.
_PROVIDER_KEY_SHAPE = re.compile(r"['\"][0-9a-f]{32}\.[A-Za-z0-9_-]{16,}['\"]")

# Atribuicao direta de segredo a um literal longo e sem espacos.
_SECRET_ASSIGNMENT = re.compile(
    r"""(?ix)
    \b[A-Za-z_]*(?:API_KEY|APIKEY|SECRET|TOKEN|PASSWORD)\b \s* [:=] \s*
    ['"]([A-Za-z0-9+/_.\-]{24,})['"]
    """
)

# Placeholders declaradamente falsos: existem para documentar ou para o CI
# rodar sem cofre, e nao sao credencial de ninguem.
_OBVIOUS_PLACEHOLDER = re.compile(
    r"(?i)(your|my|example|sample|dummy|fake|test|placeholder|changeme|xxx|not-used|"
    r"replace|insert|<|\.\.\.|abcdef|123456|session-token|sk-proj-xxx)"
)

_SKIP_SUFFIXES = {".lock", ".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".xlsx", ".zip", ".map"}
_SKIP_NAMES = {"package-lock.json", "poetry.lock"}
# Este proprio arquivo descreve os formatos que procura.
_SKIP_PATHS = {"tests/backend/unit/test_no_hardcoded_secrets.py"}


def _tracked_text_files() -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    files = []
    for rel in out.split("\0"):
        if not rel or rel in _SKIP_PATHS:
            continue
        path = PROJECT_ROOT / rel
        if path.suffix.lower() in _SKIP_SUFFIXES or path.name in _SKIP_NAMES:
            continue
        if not path.is_file():
            continue
        files.append(path)
    return files


def _findings(path: Path) -> list[str]:
    try:
        content = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return []
    hits = []
    for line_no, line in enumerate(content.splitlines(), 1):
        if _OBVIOUS_PLACEHOLDER.search(line):
            continue
        if _PROVIDER_KEY_SHAPE.search(line) or _SECRET_ASSIGNMENT.search(line):
            try:
                nome = path.relative_to(PROJECT_ROOT).as_posix()
            except ValueError:  # arquivo fora do repo (fixture de teste)
                nome = path.as_posix()
            hits.append(f"{nome}:{line_no}: {line.strip()[:120]}")
    return hits


def test_nenhum_arquivo_versionado_traz_credencial_embutida():
    achados = [hit for path in _tracked_text_files() for hit in _findings(path)]
    assert not achados, (
        "Credencial embutida em arquivo versionado:\n  "
        + "\n  ".join(achados)
        + "\n\nLeia o cabecalho deste arquivo: alem de remover o literal, "
        "a chave precisa ser ROTACIONADA no provider -- ela ja esta no historico do git."
    )


@pytest.mark.parametrize(
    "linha",
    [
        'API_KEY = os.getenv("X") or "56fe647438c0474babb266897d888f95.BgnWogEAJIRSEjTtRydKTyVP"',
        'OLLAMA_API_KEY = "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6.QWERTYUIOPASDFGH"',
        'MEU_TOKEN = "gAAAAABmZ9QkR3sT7yWpLxVnKcHdEfGhIjKlMnOpQrSt"',
    ],
)
def test_o_detector_realmente_pega_o_formato_que_vazou(tmp_path, linha):
    """Sem isto o teste acima poderia passar por nao detectar nada, nao por estar limpo."""
    alvo = tmp_path / "vazamento.py"
    alvo.write_text(linha + "\n", encoding="utf-8")
    assert _findings(alvo), f"o detector deixou passar: {linha}"


def test_o_detector_nao_reclama_de_placeholder_de_documentacao():
    for linha in [
        'OPENAI_API_KEY=sk-proj-xxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'SECRET_KEY: ci-secret-key-not-used-in-production',
        'EXPO_PUBLIC_QA_API_TOKEN = "session-token"',
    ]:
        assert _OBVIOUS_PLACEHOLDER.search(linha), linha
