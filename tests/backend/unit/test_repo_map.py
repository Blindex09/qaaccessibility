"""Repository Intelligence: garante que docs/REPO_MAP.json (gerado por
scripts/generate_repo_map.py) nunca fica dessincronizado do codigo-fonte dos
agentes -- o mesmo problema de "doc que fica obsoleta" que um indice vivo
deveria resolver, so que agora com um teste que prova a sincronia.
"""

import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO_ROOT / "scripts"))

from generate_repo_map import build_repo_map  # noqa: E402 -- precisa do sys.path acima

_REPO_MAP_PATH = _REPO_ROOT / "docs" / "REPO_MAP.json"


class TestRepoMapInSync:
    def test_committed_repo_map_matches_generator_output(self):
        committed = json.loads(_REPO_MAP_PATH.read_text(encoding="utf-8"))
        regenerated = build_repo_map()
        assert committed == regenerated, (
            "docs/REPO_MAP.json esta desatualizado -- rode "
            "'python scripts/generate_repo_map.py' e commite o resultado."
        )

    def test_every_agent_file_exists(self):
        repo_map = json.loads(_REPO_MAP_PATH.read_text(encoding="utf-8"))
        for agent in repo_map["agents"]:
            assert (_REPO_ROOT / agent["file"]).is_file(), agent["file"]

    def test_every_agent_has_at_least_one_entry_point(self):
        repo_map = json.loads(_REPO_MAP_PATH.read_text(encoding="utf-8"))
        missing = [a["name"] for a in repo_map["agents"] if not a["entry_points"]]
        assert not missing, f"Agentes sem entry_point 'run_*' detectavel: {missing}"

    def test_id_prefixes_are_unique_across_agents(self):
        # Cada agente reporta issues com um prefixo de ID proprio (ex.:
        # "perceiver-1"). Prefixos duplicados entre agentes diferentes
        # quebrariam a rastreabilidade de qual agente gerou qual issue.
        repo_map = json.loads(_REPO_MAP_PATH.read_text(encoding="utf-8"))
        seen: dict[str, str] = {}
        for agent in repo_map["agents"]:
            for prefix in agent["id_prefixes"]:
                assert prefix not in seen, (
                    f"Prefixo '{prefix}' usado tanto por '{seen.get(prefix)}' "
                    f"quanto por '{agent['name']}'"
                )
                seen[prefix] = agent["name"]
