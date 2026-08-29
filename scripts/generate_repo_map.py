"""Repository Intelligence: gera um indice estruturado e consultavel dos
sub-agentes de `backend/src/agents/` a partir do proprio codigo-fonte.

Diferenca de um README/AI_MODULE_SPEC.md: aqueles sao prosa para humanos lerem
por inteiro; este script deriva `docs/REPO_MAP.json` diretamente dos arquivos
(regex sobre `def run_*`, `"id": "prefixo-<n>"`, `"guideline": "..."` e a
primeira linha do SYSTEM_PROMPT) -- um agente (ou uma sessao futura deste
mesmo Claude Code) consulta um JSON pequeno em vez de ler 33 modulos ou 400
linhas de markdown so para responder "quem cobre ARIA?".

`docs/REPO_MAP.json` e um artefato gerado, nunca editado a mao -- rode este
script de novo apos adicionar/remover/renomear um agente.
`tests/backend/unit/test_repo_map.py` falha se o JSON commitado divergir do
que este script geraria agora, prevenindo que o mapa fique obsoleto em
silencio (mesma filosofia de Evidence-Based Completion do resto do projeto).
"""

import ast
import json
import re
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
_AGENTS_DIR = _REPO_ROOT / "backend" / "src" / "agents"
_OUTPUT_PATH = _REPO_ROOT / "docs" / "REPO_MAP.json"

# O codebase usa duas convencoes de entry-point: `run_<especialista>` para os
# sub-agentes por criterio, e `orchestrate` para o modulo que os coordena.
_ENTRY_POINT_RE = re.compile(r"^(?:async def|def) (run_\w+|orchestrate)\(", re.MULTILINE)
_ID_PREFIX_RE = re.compile(r'"id"\s*:\s*"([a-z0-9][a-z0-9_-]*)-<n>"')
_GUIDELINE_RE = re.compile(r'"guideline"\s*:\s*"([^"]+)"')
_SYSTEM_PROMPT_RE = re.compile(r'SYSTEM_PROMPT\s*=\s*(?:f)?"""\n(.*)\n', re.MULTILINE)


def _extract_responsibility(source: str) -> str:
    """Docstring do modulo via `ast` (evita falso-positivo em regex sobre a
    linha de FECHAMENTO de um `SYSTEM_PROMPT = \"\"\"...\"\"\"`, que tambem
    comeca com `\"\"\"`). Sem docstring, cai na primeira linha de conteudo do
    SYSTEM_PROMPT como aproximacao -- o objetivo e um resumo de uma linha, nao
    uma descricao completa (essa fica no AI_MODULE_SPEC.md)."""
    try:
        module_doc = ast.get_docstring(ast.parse(source))
    except SyntaxError:
        module_doc = None
    if module_doc:
        return module_doc.strip().splitlines()[0].strip()
    prompt_match = _SYSTEM_PROMPT_RE.search(source)
    if prompt_match:
        return prompt_match.group(1).strip()
    return ""


def build_repo_map() -> dict[str, Any]:
    agents: list[dict[str, Any]] = []
    for agent_dir in sorted(_AGENTS_DIR.iterdir()):
        if not agent_dir.is_dir() or agent_dir.name.startswith("_"):
            continue
        module_file = agent_dir / f"{agent_dir.name}.py"
        if not module_file.is_file():
            continue
        source = module_file.read_text(encoding="utf-8", errors="ignore")
        entry_points = _ENTRY_POINT_RE.findall(source)
        id_prefixes = sorted(set(_ID_PREFIX_RE.findall(source)))
        guidelines = sorted(set(_GUIDELINE_RE.findall(source)))
        agents.append({
            "name": agent_dir.name,
            "file": str(module_file.relative_to(_REPO_ROOT)).replace("\\", "/"),
            "entry_points": entry_points,
            "id_prefixes": id_prefixes,
            "guidelines": guidelines,
            "responsibility": _extract_responsibility(source),
        })
    return {
        "$schema_note": (
            "Gerado por scripts/generate_repo_map.py -- nao editar a mao. "
            "Rode 'python scripts/generate_repo_map.py' apos mudar um agente."
        ),
        "agents": agents,
    }


def main() -> None:
    repo_map = build_repo_map()
    _OUTPUT_PATH.write_text(
        json.dumps(repo_map, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"[repo_map] {len(repo_map['agents'])} agentes indexados em {_OUTPUT_PATH}")


if __name__ == "__main__":
    main()
