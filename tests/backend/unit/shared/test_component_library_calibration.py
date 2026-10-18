"""Conhecimento de bibliotecas de componentes: fonte única, ligação aos agentes e regressões.

Cada teste aponta uma promessa de `docs/modules/conhecimento_de_componentes.md`.
O HTML dos casos reproduz o que o accessible-astro-components renderiza (lido da fonte
da biblioteca em 2026-10-17), não o que um catálogo genérico presumiria.
"""

import importlib
import re
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from backend.src.agents.orchestrator.orchestrator import _conditional_agent_reasons
from backend.src.services import a11y_knowledge
from backend.src.shared.component_library_calibration import (
    COMPONENT_LIBRARY_FULL,
    COMPONENT_LIBRARY_METHOD,
)

_FULL_AGENTS = ("component_contracts", "widgets_a11y")
_METHOD_AGENTS = (
    "forms_a11y",
    "aria_specialist",
    "interaction_pattern",
    "operability",
    "screen_reader",
    "link_checker",
)

# Renderizado pelo AccordionItem: details nativo, sem button, sem aria-expanded, sem id.
ASTRO_ACCORDION_HTML = """
<ul class="accordion"><li class="item"><details class="wrapper variant-default">
<summary class="title"><h3 class="heading h6">Pergunta</h3></summary>
<div class="content">Resposta</div></details></li></ul>
""".strip()

# Renderizado pelo Tooltip: botão com popovertarget e um span popover.
ASTRO_TOOLTIP_HTML = """
<button class="tooltip-trigger" id="t1-trigger" popovertarget="t1" aria-controls="t1" aria-describedby="t1" aria-expanded="false">
<span class="sr-only">Ajuda</span></button><span role="tooltip" id="t1" popover>Texto</span>
""".strip()

# Renderizado pelo Pagination: progresso textual, sem aria-current e sem lista numerada.
ASTRO_PAGINATION_HTML = """
<nav class="pagination" aria-label="Pagination"><ul class="list">
<li><span class="disabled">First</span></li><li><span class="disabled">Previous</span></li>
<li><span>Page 1 of 12</span></li>
<li><a href="/2" aria-label="Go to the next page">Next</a></li>
<li><a href="/12" aria-label="Go to the last page">Last</a></li></ul></nav>
""".strip()


def _prompt(agent: str) -> str:
    module = importlib.import_module(f"backend.src.agents.{agent}.{agent}")
    return str(module.SYSTEM_PROMPT)


class TestSingleSource:
    def test_method_and_catalog_come_from_the_resource_file(self):
        assert "Nativo primeiro" in COMPONENT_LIBRARY_METHOD
        assert "accessible-astro-components" in COMPONENT_LIBRARY_FULL
        assert "accessible-astro-components" not in COMPONENT_LIBRARY_METHOD
        assert COMPONENT_LIBRARY_FULL.startswith(COMPONENT_LIBRARY_METHOD)

    def test_chat_rag_corpus_indexes_the_library_knowledge(self):
        titles = {chunk.title for chunk in a11y_knowledge.load_corpus() if chunk.source == "component_library_knowledge.md"}
        assert any("Accordion" in title for title in titles)
        assert any("Tooltip" in title for title in titles)

    def test_every_component_the_starter_demonstrates_has_an_entry(self):
        catalog = COMPONENT_LIBRARY_FULL
        demonstrated = [
            "Accordion", "AccordionItem", "Avatar", "AvatarGroup", "Badge", "Breadcrumbs", "BreadcrumbsItem",
            "Button", "Card", "Checkbox", "DarkMode", "Fieldset", "Form", "Heading", "HighContrast", "Input",
            "Link", "Media", "Modal", "Notification", "Pagination", "ReducedMotion", "Radio", "Tabs",
            "TabsList", "TabsTab", "TabsPanel", "Textarea", "Tooltip", "Video", "SkipLink", "Drawer", "Toast",
        ]
        missing = [name for name in demonstrated if not re.search(rf"\b{name}\b", catalog)]
        assert missing == []

    def test_catalog_covers_every_import_of_the_real_starter_page_when_present(self):
        page = Path("C:/projetos IA/my-accessible-site/src/pages/accessible-components.astro")
        if not page.exists():
            pytest.skip("projeto my-accessible-site não está nesta máquina")
        source = page.read_text(encoding="utf-8")
        block = re.search(r"import \{([^}]*)\} from 'accessible-astro-components'", source, re.S)
        assert block is not None
        imported = [name.strip() for name in block.group(1).split(",") if name.strip()]
        missing = [name for name in imported if not re.search(rf"\b{name}\b", COMPONENT_LIBRARY_FULL)]
        assert missing == []


class TestWiringIntoAgents:
    @pytest.mark.parametrize("agent", _FULL_AGENTS)
    def test_composed_component_specialists_get_method_and_catalog(self, agent):
        assert COMPONENT_LIBRARY_FULL in _prompt(agent)

    @pytest.mark.parametrize("agent", _METHOD_AGENTS)
    def test_other_specialists_get_the_method_without_the_catalog_cost(self, agent):
        prompt = _prompt(agent)
        assert COMPONENT_LIBRARY_METHOD in prompt
        assert "### Accordion e AccordionItem" not in prompt

    def test_reviewer_gets_the_method_and_keeps_the_normative_contract_last(self):
        from backend.src.agents.a11y_expert_reviewer.a11y_expert_reviewer import SYSTEM_PROMPT
        from backend.src.shared.normative_calibration import NORMATIVE_CALIBRATION

        assert COMPONENT_LIBRARY_METHOD in SYSTEM_PROMPT
        assert SYSTEM_PROMPT.endswith(NORMATIVE_CALIBRATION)

    @pytest.mark.asyncio
    async def test_squad_roles_receive_the_method(self):
        from backend.src.agents.squad.role_agents import _runner
        from backend.src.agents.squad.roles import SquadRole

        model = AsyncMock(return_value={"summary": "ok", "handoff": {}})
        with patch.object(_runner, "call_llm_structured", model):
            await _runner.run_role(role=SquadRole.QA_LEAD, system_prompt="QA", context={})
        assert COMPONENT_LIBRARY_METHOD in model.call_args.kwargs["system_prompt"]

    def test_chat_prompt_builder_references_the_method(self):
        source = (Path(__file__).resolve().parents[4] / "backend" / "src" / "services" / "chat_runtime.py").read_text(encoding="utf-8")
        assert "COMPONENT_LIBRARY_METHOD" in source


class TestRealDefectsFoundByTheReading:
    """Cada caso abaixo é um desacordo real entre o conhecimento anterior e a biblioteca."""

    def test_native_details_summary_is_a_valid_disclosure_not_a_missing_button(self):
        prompt = _prompt("component_contracts")
        assert "native details/summary" in prompt
        assert "no aria-expanded or aria-controls required" in prompt

    def test_form_error_summary_does_not_demand_assertive_when_focus_is_moved(self):
        prompt = _prompt("forms_a11y")
        assert 'missing role="alert" or aria-live="assertive"' not in prompt
        assert 'aria-live="polite" with focus moved to it' in prompt

    def test_generic_catalog_accepts_native_disclosure_and_toggletip_and_text_pagination(self):
        text = (Path(a11y_knowledge.__file__).resolve().parents[1] / "resources" / "accessible_component_patterns.md").read_text(encoding="utf-8")
        assert "`summary` de um `details` nativo" in text
        assert "toggletip" in text
        assert "texto de progresso" in text

    def test_page_with_only_native_disclosure_still_reaches_the_component_specialist(self):
        reasons = _conditional_agent_reasons(ASTRO_ACCORDION_HTML)
        assert "component_contracts" in reasons

    def test_bare_native_dialog_after_a_tag_reaches_the_component_specialist(self):
        """Defeito anterior: o \\b inicial do seletor impedia casar '<dialog' depois de '>' ou espaço."""
        reasons = _conditional_agent_reasons("<main><dialog><p>Texto</p></dialog></main>")
        assert "component_contracts" in reasons

    def test_plain_page_without_component_evidence_does_not_pay_for_the_specialist(self):
        reasons = _conditional_agent_reasons("<main><p>Texto</p><button>Salvar</button></main>")
        assert "component_contracts" not in reasons

    def test_popover_tooltip_reaches_the_component_specialists(self):
        reasons = _conditional_agent_reasons(ASTRO_TOOLTIP_HTML)
        assert "component_contracts" in reasons
        assert "widgets_a11y" in reasons

    def test_disclosure_navigation_is_not_forced_into_role_menu(self):
        """Achado lendo o Navigation do my-accessible-site: botão aria-haspopup=true + lista de links."""
        assert "padrão de navegação por divulgação" in COMPONENT_LIBRARY_METHOD
        assert "não exija role=\"menu\"" in COMPONENT_LIBRARY_METHOD
        assert "aria-haspopup=\"true\" num botão cujo submenu só tem links" in COMPONENT_LIBRARY_METHOD
        prompt = _prompt("widgets_a11y")
        assert "disclosure\n    navigation pattern" in prompt
        assert "a recommendation only, never\n    a confirmed failure on its own" in prompt

    def test_site_dropdown_navigation_reaches_the_widget_and_component_specialists(self):
        html = (
            '<nav aria-label="Main navigation desktop"><ul><li class="has-dropdown">'
            '<button aria-haspopup="true" aria-expanded="false">Features</button>'
            '<ul><li><a href="/a">A</a></li></ul></li></ul></nav>'
        )
        reasons = _conditional_agent_reasons(html)
        assert "widgets_a11y" in reasons
        assert "component_contracts" in reasons

    def test_catalog_states_what_is_not_a_failure_for_each_astro_shape(self):
        assert "details e summary são o padrão nativo" in COMPONENT_LIBRARY_FULL
        assert "toggletip" in COMPONENT_LIBRARY_FULL
        assert "Exigir aria-current=\"page\" aqui não se aplica" in COMPONENT_LIBRARY_FULL


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("html", "fragment"),
    [
        (ASTRO_ACCORDION_HTML, "details e summary"),
        (ASTRO_TOOLTIP_HTML, "toggletip"),
        (ASTRO_PAGINATION_HTML, "Page X of Y"),
    ],
)
async def test_component_specialist_sends_html_and_catalog_to_the_model(html, fragment):
    from backend.src.agents.component_contracts import component_contracts

    model = AsyncMock(return_value=[])
    with patch.object(component_contracts, "call_llm_structured", model):
        result = await component_contracts.run_component_contracts(html)
    assert result.success
    assert html in model.call_args.kwargs["user_prompt"]
    assert fragment in model.call_args.kwargs["system_prompt"]
