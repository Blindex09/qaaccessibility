"""Defesa contra a volta de relogio fixo no codigo (regra 8 e tempo-e-lacos.md).

Nenhum prazo fixo pode cortar trabalho em andamento. Este teste varre o codigo do backend e recusa:
- asyncio.wait_for com prazo (a espera de trabalho usa run_until_stalled, que so desiste se a execucao travar);
- subprocess com timeout (comando lento nao e morto);
- chamada de rede com um numero de segundos como timeout (so estabelecer a conexao tem limite: tupla
  (conexao, None) ou httpx.Timeout(None, connect=...)).

Excecoes declaradas e justificadas ficam em _PERMITIDOS.
"""

import ast
from pathlib import Path

_RAIZ = Path(__file__).resolve().parents[3] / "backend" / "src"

# arquivo -> motivo
_PERMITIDOS = {
    # Consulta de catalogo de modelos: metadado, nao trabalho do modelo (declarado no CLAUDE.md do projeto).
    "services/ollama_cloud_adapter.py": "metadado do catalogo de modelos",
    # Espera com shield, so para avisar progresso a cada intervalo; nao cancela o trabalho.
    "agents/squad/coordinator.py": "wait_for com shield apenas para checar cancelamento",
}

_ESPERAS_DE_AVISO = ("asyncio.wait", "ev.wait")


def _violacoes() -> list[str]:
    achados: list[str] = []
    for caminho in sorted(_RAIZ.rglob("*.py")):
        relativo = caminho.relative_to(_RAIZ).as_posix()
        if relativo in _PERMITIDOS:
            continue
        arvore = ast.parse(caminho.read_text(encoding="utf-8"))
        for no in ast.walk(arvore):
            if not isinstance(no, ast.Call):
                continue
            nome = ast.unparse(no.func)
            if nome.endswith("wait_for"):
                achados.append(f"{relativo}:{no.lineno} {nome} com prazo")
            for kw in no.keywords:
                if kw.arg != "timeout":
                    continue
                if nome.startswith("subprocess."):
                    achados.append(f"{relativo}:{no.lineno} {nome} com timeout")
                elif nome in _ESPERAS_DE_AVISO or "page." in nome or "locator" in nome:
                    continue
                elif isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, (int, float)):
                    achados.append(f"{relativo}:{no.lineno} {nome} com {kw.value.value}s fixos")
    return achados


def test_nenhum_relogio_fixo_corta_trabalho_em_andamento():
    assert _violacoes() == []


def test_nenhum_modelo_e_escolhido_pelo_nome_no_roteador():
    """Regras 2 e 9: o roteador nao decide nivel nem capacidade por palavra do identificador do modelo."""
    fonte = (_RAIZ / "services" / "model_router.py").read_text(encoding="utf-8")
    for palavra in ('"nano"', '"flash"', '"haiku"', '"codex"', "is_fast_name"):
        assert palavra not in fonte
