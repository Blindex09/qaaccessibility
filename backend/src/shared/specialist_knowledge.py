"""Sourced knowledge slices for each analysis specialist.

The long references in resources/ (screen reader behaviour, ARIA patterns, dynamic content, CSS, frameworks,
mobile and documents, cognitive and compliance) are indexed for the chat. A specialist should not receive all
of them, only the sections of its own domain, so the context stays small. Which sections each specialist gets
is a fixed map of domain to document headings; nothing here reads the audited page or decides anything about it.

Each slice is capped in characters. Sections are added in the listed order, a section that does not fit is
cut at a line boundary, and the cap is measured by a test so the cost of this knowledge stays visible.
"""

from pathlib import Path

_RESOURCES = Path(__file__).resolve().parents[1] / "resources"

HTML = "leitor_de_tela_elementos_html.md"
ARIA = "leitor_de_tela_aria_e_padroes.md"
DYNAMIC = "leitor_de_tela_dinamico_js_react.md"
CSS = "leitor_de_tela_css_e_modos.md"
ACTIONS = "leitor_de_tela_acoes_teclas_e_eventos.md"
FRAMEWORKS = "acessibilidade_frameworks_e_componentes.md"
MOBILE_DOCS = "acessibilidade_mobile_documentos_e_midia.md"
COGNITIVE = "acessibilidade_cognitiva_conformidade_e_metodologia.md"
STRUCTURE = "leitor_de_tela_estrutura_foco_e_navegacao.md"

SOURCE_FILES = (HTML, ARIA, DYNAMIC, CSS, ACTIONS, FRAMEWORKS, MOBILE_DOCS, COGNITIVE, STRUCTURE)

_HEADER = (
    "SOURCED REFERENCE FOR THIS SPECIALIST (official documentation, written in Portuguese; answer in the language "
    "the task asks for). Use it to judge what is a real defect and what is only a recommendation. It never "
    "suppresses an evidenced defect, and what is marked as unconfirmed there stays pending manual verification."
)

# agent -> (character cap, [(document, heading prefix), ...])
SLICES: dict[str, tuple[int, list[tuple[str, str]]]] = {
    "screen_reader": (9500, [(HTML, "Como usar"), (HTML, "Estrutura de cab"), (HTML, "Links e bot"), (HTML, "Campos de formul"), (HTML, "Tabelas"), (HTML, "Imagens"), (HTML, "Áreas de página"), (STRUCTURE, "Títulos e hierarquia"), (STRUCTURE, "Navegação tabular")]),
    "aria_specialist": (6500, [(ARIA, "Princípios"), (ACTIONS, "O que é anunciado quando um estado muda")]),
    "forms_a11y": (7000, [(HTML, "Campos de formul"), (ARIA, "Casos de estado de formul"), (ACTIONS, "Atributos HTML"), (DYNAMIC, "Formulários e valida")]),
    "ajax_dynamic": (7000, [(DYNAMIC, "Como o leitor de tela percebe"), (DYNAMIC, "Foco"), (ACTIONS, "AJAX e conteúdo")]),
    "operability": (9500, [(ACTIONS, "Ativar um elemento"), (DYNAMIC, "Foco"), (ACTIONS, "Modos de leitura"), (STRUCTURE, "Ordem de foco")]),
    "widgets_a11y": (7000, [(ARIA, "Diálogo"), (ARIA, "Abas"), (ARIA, "Acordeão"), (ARIA, "Menu de aplicativo"), (ARIA, "Combobox")]),
    "component_contracts": (6000, [(ARIA, "Diálogo"), (ARIA, "Abas"), (ARIA, "Acordeão"), (ARIA, "Dicas")]),
    "interaction_pattern": (7500, [(ARIA, "Combobox"), (ARIA, "Menu de aplicativo"), (ARIA, "Controles básicos"), (ARIA, "Tabela e grade"), (STRUCTURE, "Grade (grid)")]),
    "tables_data": (9000, [(HTML, "Tabelas"), (ARIA, "Tabela e grade"), (STRUCTURE, "Tabelas: marcação"), (STRUCTURE, "Grade (grid)")]),
    "link_checker": (4000, [(HTML, "Links e bot")]),
    "wcag_semantics": (9500, [(HTML, "Estrutura de cab"), (HTML, "Áreas de página"), (HTML, "Texto em linha"), (STRUCTURE, "Títulos e hierarquia"), (STRUCTURE, "Listas")]),
    "css_analyzer": (8500, [(CSS, "Efeitos do CSS"), (STRUCTURE, "Ordem de foco")]),
    "perceiver": (5500, [(HTML, "Imagens"), (HTML, "Mídia"), (MOBILE_DOCS, "Mídia")]),
    "mobile_a11y": (7500, [(MOBILE_DOCS, "Mobile na web")]),
    "pdf_accessibility": (7000, [(MOBILE_DOCS, "PDF")]),
    "excel_accessibility": (5500, [(MOBILE_DOCS, "Word, Excel e PowerPoint")]),
    "cognitive": (8000, [(COGNITIVE, "Critérios de entrada")]),
    "understandability": (8000, [(COGNITIVE, "Critérios de entrada")]),
    "section508": (7000, [(COGNITIVE, "Seção 508"), (COGNITIVE, "WCAG 2.2: modelo")]),
    "compliance_audit": (7500, [(COGNITIVE, "WCAG 2.2: modelo"), (COGNITIVE, "Seção 508")]),
    "vpat_reporter": (5500, [(COGNITIVE, "WCAG 2.2: modelo"), (COGNITIVE, "Seção 508")]),
    "robustness": (5000, [(ARIA, "Princípios")]),
    "vue_framework": (4500, [(FRAMEWORKS, "Vue e Nuxt")]),
    "angular_framework": (4500, [(FRAMEWORKS, "Angular")]),
    "svelte_framework": (4500, [(FRAMEWORKS, "Svelte")]),
    "react_framework": (5500, [(DYNAMIC, "React"), (FRAMEWORKS, "React")]),
    "tailwind_css": (4500, [(FRAMEWORKS, "Tailwind")]),
    "web_components": (4500, [(FRAMEWORKS, "Web Components")]),
}


def _sections(document: str) -> list[tuple[str, str]]:
    text = (_RESOURCES / document).read_text(encoding="utf-8")
    sections: list[tuple[str, str]] = []
    title = ""
    buffer: list[str] = []
    for line in text.splitlines():
        if line.startswith("## "):
            if title:
                sections.append((title, "\n".join(buffer).strip()))
            title, buffer = line[3:].strip(), [line]
        elif title:
            buffer.append(line)
    if title:
        sections.append((title, "\n".join(buffer).strip()))
    return sections


def _cut_at_line(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit("\n", 1)[0]
    return cut if cut.strip() else text[:limit]


def slice_sections(agent: str) -> list[tuple[str, str, str]]:
    """The (document, heading, text) triples chosen for an agent, before the character cap."""
    _cap, wanted = SLICES[agent]
    found: list[tuple[str, str, str]] = []
    for document, prefix in wanted:
        for title, body in _sections(document):
            if title.startswith(prefix):
                found.append((document, title, body))
    return found


def specialist_knowledge(agent: str) -> str:
    """Prompt block for a specialist, or raise KeyError for an agent that has no slice."""
    cap, _wanted = SLICES[agent]
    parts: list[str] = []
    used = 0
    seen: set[tuple[str, str]] = set()
    for document, title, body in slice_sections(agent):
        if (document, title) in seen:
            continue
        seen.add((document, title))
        room = cap - used
        if room < 400:
            break
        piece = _cut_at_line(body, room)
        parts.append(piece)
        used += len(piece) + 2
    return "\n\n" + _HEADER + "\n\n" + "\n\n".join(parts)
