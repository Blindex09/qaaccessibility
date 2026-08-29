"""Garante que backend/src/resources/agent_knowledge.md (gerado por
scripts/generate_agent_knowledge.py) nunca fica dessincronizado do
SYSTEM_PROMPT dos agentes de analise -- a mesma divergencia entre "o que os
agentes sabem" e "o que o chat sabe" que este arquivo existe para fechar.
"""

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO_ROOT / "scripts"))

from generate_agent_knowledge import build_agent_knowledge  # noqa: E402 -- precisa do sys.path acima

_OUTPUT_PATH = _REPO_ROOT / "backend" / "src" / "resources" / "agent_knowledge.md"


class TestAgentKnowledgeInSync:
    def test_committed_file_matches_generator_output(self):
        committed = _OUTPUT_PATH.read_text(encoding="utf-8")
        regenerated = build_agent_knowledge()
        assert committed == regenerated, (
            "backend/src/resources/agent_knowledge.md esta desatualizado -- "
            "rode 'python scripts/generate_agent_knowledge.py' e commite o "
            "resultado."
        )

    def test_covers_every_analysis_agent_prompt(self):
        from generate_agent_knowledge import _AGENTS_DIR, _EXCLUDED_AGENTS

        content = build_agent_knowledge()
        agent_dirs = [
            d.name for d in _AGENTS_DIR.iterdir()
            if d.is_dir() and not d.name.startswith("_") and d.name not in _EXCLUDED_AGENTS
        ]
        assert agent_dirs, "nenhum agente de analise encontrado -- checar _EXCLUDED_AGENTS"
        # 1 secao "## " por agente coberto (mesma contagem, nao precisa bater nome
        # exato -- o titulo vem da 1a frase do prompt, nao do nome do diretorio).
        assert content.count("\n## ") == len(agent_dirs)

    def test_registered_in_chat_rag_corpus(self):
        from backend.src.services.a11y_knowledge import _CORPUS_FILES
        assert "agent_knowledge.md" in _CORPUS_FILES

    def test_pipeline_coordination_agents_never_leak_into_the_domain_corpus(self):
        """Achado real (2026-08-27): `delegation_coordinator` (decide, via LLM,
        se um especialista pulado deve rodar mesmo assim) tem um SYSTEM_PROMPT
        que casa com o regex de extracao (comeca com "You are the...") mas nao
        e conhecimento de dominio -- e instrucao de roteamento do pipeline
        ("Return a JSON object", "target_agent"). Sem exclusao explicita, o
        gerador incluia esse conteudo como se fosse uma secao de especialista
        de verdade no corpus do RAG do chat, poluindo as passagens que o chat
        pode recuperar para responder perguntas de acessibilidade do usuario.
        `squad` (contratos/orquestracao do SquadPlan, sem SYSTEM_PROMPT proprio
        de deteccao) e o mesmo tipo de risco. Trava os dois fora do corpus."""
        from generate_agent_knowledge import _EXCLUDED_AGENTS

        content = build_agent_knowledge()
        assert {"delegation_coordinator", "squad"} <= _EXCLUDED_AGENTS
        assert "\n## delegation coordinator" not in content
        assert "target_agent" not in content
        assert "Return a JSON object" not in content
