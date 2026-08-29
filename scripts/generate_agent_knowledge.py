"""Deriva `backend/src/resources/agent_knowledge.md` do `SYSTEM_PROMPT` de cada
um dos agentes de analise (as regras/checks que eles usam para auditar HTML),
sem o boilerplate de formato de saida (exemplo few-shot, schema JSON,
instrucoes "Return ONLY..."). O arquivo gerado entra no corpus do RAG do chat
(`a11y_knowledge.py::_CORPUS_FILES`), ao lado de `a11y_reference.md`.

Resolve a divergencia entre "o que os agentes de analise sabem" e "o que o
chat sabe": qualquer mudanca num SYSTEM_PROMPT de agente flui para o chat na
proxima execucao deste script, sem edicao manual de prosa em outro arquivo.

`agent_knowledge.md` e artefato gerado, nunca editado a mao. Rode
'python scripts/generate_agent_knowledge.py' apos mudar um SYSTEM_PROMPT.
`tests/backend/unit/test_agent_knowledge_sync.py` falha se o arquivo commitado
divergir do que este script geraria agora.
"""

import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_AGENTS_DIR = _REPO_ROOT / "backend" / "src" / "agents"
_OUTPUT_PATH = _REPO_ROOT / "backend" / "src" / "resources" / "agent_knowledge.md"

_SYSTEM_PROMPT_RE = re.compile(r'SYSTEM_PROMPT\s*=\s*(?:f)?"""\n(.*?)\n"""', re.DOTALL)

# Corta o corpo do prompt no primeiro marcador de boilerplate de formato de
# saida -- tudo ANTES disso e conhecimento de dominio (o que entra no RAG);
# tudo DEPOIS e instrucao de schema JSON para o LLM, irrelevante para o chat.
_OUTPUT_BOILERPLATE_RE = re.compile(
    r"\n(?:EXAMPLE \(a correctly formatted issue|Return a JSON array\. Each issue must follow)"
)

# Estrutura de secao ([PAGE CONTEXT]/[ELEMENTS]/etc.) e formato de entrada, nao
# conhecimento de dominio -- ruido para o RAG.
_INPUT_STRUCTURE_RE = re.compile(
    r"^The HTML you receive is structured.*?(?=\n\n)", re.DOTALL | re.MULTILINE
)

# Titulo amigavel por agente = a primeira frase do prompt ("You are a X
# specialist"), extraida em vez de mantida numa lista paralela -- uma lista
# manual desatualizaria exatamente do jeito que este gerador existe para evitar.
_ROLE_SENTENCE_RE = re.compile(r"^You are (?:an?|the) (.+?)\.\s", re.DOTALL)

# Agentes cujo SYSTEM_PROMPT nao segue o padrao "retorna AccessibilityIssue[]"
# (ex.: classificador, corretor, gerador de relatorio) -- fora de escopo deste
# corpus, que e sobre "quais violacoes cada especialista de auditoria detecta".
_EXCLUDED_AGENTS = {
    "orchestrator", "classifier", "clarifier", "checklist", "fixer", "reporter",
    "vpat_reporter", "test_generator", "a11y_expert_reviewer", "deep_research",
    "gap_research", "squad", "delegation_coordinator", "design_review",
}

# Descricao de 1 linha dos agentes de coordenacao/entrega (_EXCLUDED_AGENTS
# acima) para o indice -- nao tem SYSTEM_PROMPT no formato "detecta issues",
# entao nao da pra derivar automaticamente como os especialistas de auditoria.
# Mantido aqui (nao numa prosa solta em outro arquivo) para nao desincronizar:
# adicionar um agente novo a _EXCLUDED_AGENTS sem entrada aqui quebra o teste
# de sincronia (test_agent_knowledge_sync.py) tao logo o script rode de novo.
_COORDINATION_AGENT_DESCRIPTIONS = {
    "orchestrator": "coordena a execucao paralela de todos os especialistas de auditoria, com roteamento condicional por evidencia estrutural do HTML e deduplicacao do resultado final.",
    "classifier": "detecta tecnologias/frameworks no HTML (React, Angular, Vue, Svelte, Tailwind) para decidir quais especialistas de framework o orchestrator deve rodar.",
    "clarifier": "faz a triagem semantica do primeiro turno do chat (dentro ou fora do escopo de acessibilidade) antes de qualquer ferramenta ser chamada.",
    "checklist": "gera o checklist estruturado (pass/fail/manual-verification por criterio WCAG) a partir dos issues de uma analise -- usado pela tool `generate_checklist` do chat, nao mais texto solto escrito pelo modelo.",
    "fixer": "aplica as correcoes de acessibilidade no HTML a partir dos issues encontrados, produzindo o HTML corrigido usado por `fix_and_zip_files`.",
    "reporter": "monta o relatorio narrativo de uma analise (resumo executivo, achados por severidade) a partir dos issues.",
    "vpat_reporter": "gera o VPAT WCAG 2.2 (Voluntary Product Accessibility Template) para procurement/Section 508 a partir da ultima analise.",
    "test_generator": "gera a suite de testes automatizados (Playwright + axe-core) pronta para o CI do time auditado, a partir da ultima analise.",
    "a11y_expert_reviewer": "revisao de segunda opiniao sobre os issues encontrados por outros agentes, reduzindo falsos positivos antes do resultado final.",
    "deep_research": "pesquisa normativa profunda (WCAG 2.2, WAI-ARIA APG) quando a pergunta do usuario exige contexto alem do que o RAG local cobre.",
    "gap_research": "verificacao automatica de achados de baixa confianca via deep_research, quando um especialista de auditoria nao tem certeza se um issue e real.",
    "squad": "monta e coordena o SquadPlan (escopo, analise, correcao opcional, QA, documentacao) do chat agentico, com tarefas dependentes/estados e portoes de aprovacao -- nao tem SYSTEM_PROMPT proprio, so contratos/orquestracao (ver docs/ARQUITETURA_SQUAD_ACESSIBILIDADE.md).",
    "delegation_coordinator": "decide, via LLM lendo os achados reais da rodada 1, se algum especialista pulado (sem evidencia estrutural de HTML) deve ganhar uma rodada de acompanhamento -- delegacao agente-a-agente real, nao mapeamento fixo issue-tipo -> agente. Nao detecta violacoes nem descreve regras WCAG por conta propria, entao fica fora deste corpus (o SYSTEM_PROMPT e sobre roteamento do pipeline, nao sobre acessibilidade).",
    "design_review": "antecipa riscos de acessibilidade a partir de um requisito/user story/descricao de componente em texto livre, ANTES de qualquer codigo existir (shift-left) -- unico agente do projeto que nao audita HTML/codigo ja escrito. Fora deste corpus porque a saida e DesignRiskFlag[] (risco+recomendacao), nao AccessibilityIssue[] detectado em HTML.",
}


def _extract_knowledge_body(source: str) -> str | None:
    match = _SYSTEM_PROMPT_RE.search(source)
    if not match:
        return None
    prompt = match.group(1)
    cutoff = _OUTPUT_BOILERPLATE_RE.search(prompt)
    body = prompt[:cutoff.start()] if cutoff else prompt
    body = _INPUT_STRUCTURE_RE.sub("", body).strip()
    return body or None


def _agent_title(knowledge_body: str, agent_name: str) -> str:
    role_match = _ROLE_SENTENCE_RE.match(knowledge_body)
    if role_match:
        return role_match.group(1).strip().rstrip(".")
    return agent_name.replace("_", " ").title()


def _split_into_subsections(knowledge_body: str) -> list[str]:
    """Quebra o corpo do prompt em blocos separados por linha em branco.

    Os prompts ja escrevem cada categoria de checagem ("ARIA RULES (...):",
    "STREAMING AND LIVE REGIONS (WCAG 4.1.3):", etc.) como um paragrafo
    separado por linha em branco das outras -- reaproveitar essa estrutura
    evita virar um unico chunk gigante (o RAG do chat chunka por heading
    markdown, e um agente inteiro num so `##` fica maior que o esperado pelo
    design de chunking existente). O primeiro bloco (intro "You are a X
    specialist...") fica sem sub-heading, direto sob o `##` do agente.
    """
    blocks = [b.strip() for b in re.split(r"\n\s*\n", knowledge_body) if b.strip()]
    return blocks


def _render_agent_section(title: str, knowledge_body: str) -> str:
    blocks = _split_into_subsections(knowledge_body)
    if len(blocks) <= 1:
        return f"## {title}\n{knowledge_body}"

    lines = [f"## {title}", blocks[0]]
    for block in blocks[1:]:
        first_line, _, rest = block.partition("\n")
        sub_title = first_line.strip().rstrip(":")
        if rest.strip():
            lines.append(f"### {sub_title}\n{rest.strip()}")
        else:
            # Bloco de uma linha so (sem corpo) -- nao vale a pena promover a
            # sub-heading; mantem como continuacao de texto simples.
            lines.append(block)
    return "\n\n".join(lines)


def _collect_specialist_entries() -> list[tuple[str, str, str]]:
    """(agent_name, title, knowledge_body) de cada especialista de auditoria
    incluido, na mesma ordem/filtro do loop principal -- usado tanto pelo
    indice quanto pelas secoes completas, para nunca divergir entre os dois."""
    entries = []
    for agent_dir in sorted(_AGENTS_DIR.iterdir()):
        if not agent_dir.is_dir() or agent_dir.name.startswith("_") or agent_dir.name in _EXCLUDED_AGENTS:
            continue
        module_file = agent_dir / f"{agent_dir.name}.py"
        if not module_file.is_file():
            continue
        source = module_file.read_text(encoding="utf-8", errors="ignore")
        knowledge_body = _extract_knowledge_body(source)
        if not knowledge_body:
            continue
        title = _agent_title(knowledge_body, agent_dir.name)
        entries.append((agent_dir.name, title, knowledge_body))
    return entries


def _render_index(entries: list[tuple[str, str, str]]) -> list[str]:
    """Indice rapido no topo do arquivo: o RAG (chunking por `##`/`###`) so
    devolve os trechos relevantes pra pergunta atual -- isso aqui e o
    complemento, um mapa de 'o que existe' pro chat saber o que oferecer/
    mencionar proativamente sem precisar da query certa pra achar via busca.
    Usa `###` (nao `##`) de proposito: o teste de sincronia conta headings
    `## ` para bater 1-para-1 com os agentes de auditoria (ver
    test_agent_knowledge_sync.py::test_covers_every_analysis_agent_prompt).
    """
    lines = ["### Índice de especialistas (auto-gerado, não editar a mão)", ""]
    lines.append("**Agentes de auditoria** (detectam violações; conhecimento completo nas seções `##` abaixo):")
    for _name, title, _body in entries:
        lines.append(f"- {title}")
    lines.append("")
    lines.append("**Agentes de coordenação/entrega** (fora deste corpus -- orquestram ou geram artefatos, não detectam violações por conta própria):")
    for name in sorted(_EXCLUDED_AGENTS):
        desc = _COORDINATION_AGENT_DESCRIPTIONS.get(name, "")
        lines.append(f"- `{name}`: {desc}")
    lines.append("")
    return lines


def build_agent_knowledge() -> str:
    entries = _collect_specialist_entries()
    sections: list[str] = [
        "# Conhecimento dos Agentes de Análise (gerado)",
        "",
        "> Gerado por `scripts/generate_agent_knowledge.py` a partir do "
        "`SYSTEM_PROMPT` de cada agente de análise -- **não editar a mão**. "
        "Rode o script de novo após mudar um prompt de agente.",
        "",
        *_render_index(entries),
    ]
    for _name, title, knowledge_body in entries:
        sections.append(_render_agent_section(title, knowledge_body))
        sections.append("")
    return "\n".join(sections).rstrip() + "\n"


def main() -> None:
    content = build_agent_knowledge()
    _OUTPUT_PATH.write_text(content, encoding="utf-8")
    agent_count = content.count("\n## ")
    print(f"[agent_knowledge] {agent_count} agentes indexados em {_OUTPUT_PATH}")


if __name__ == "__main__":
    main()
