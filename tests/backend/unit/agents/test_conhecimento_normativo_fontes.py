"""Afirmações normativas dos prompts conferidas contra a documentação oficial (2026-10-17).

Cada teste trava uma correção. Fontes consultadas:
- WCAG 2.2, novidades: https://www.w3.org/WAI/standards-guidelines/wcag/new-in-22/ (4.1.1 Parsing foi removido).
- WCAG 2.2, 1.4.12: https://www.w3.org/WAI/WCAG22/Understanding/text-spacing.html (testa a sobreposição pelo usuário).
- WCAG 2.2, 2.4.13: https://www.w3.org/WAI/WCAG22/Understanding/focus-appearance.html (nível AAA).
- WCAG 2.2, 2.5.3: https://www.w3.org/WAI/WCAG22/Understanding/label-in-name.html (nível A).
- WCAG 2.2, 1.4.3: https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html (só a razão do WCAG 2).
- WAI-ARIA 1.2, papéis sem nome do autor: https://www.w3.org/TR/wai-aria-1.2/#namefromprohibited
- MDN aria-checked, aria-expanded e aria-selected (papéis que suportam cada propriedade).
- MDN, regiões vivas: https://developer.mozilla.org/en-US/docs/Web/Accessibility/ARIA/Guides/Live_regions
- WAI-ARIA APG, alerta: https://www.w3.org/WAI/ARIA/apg/patterns/alert/ (alerta não toma o foco).
- HTML, popover: https://html.spec.whatwg.org/multipage/popover.html (não exige papel explícito).
"""

import importlib
from pathlib import Path

import pytest

_AGENTS = Path(__file__).resolve().parents[4] / "backend" / "src" / "agents"
_RESOURCES = Path(__file__).resolve().parents[4] / "backend" / "src" / "resources"


def _prompt(agent: str) -> str:
    return str(importlib.import_module(f"backend.src.agents.{agent}.{agent}").SYSTEM_PROMPT)


class TestWcagCriteria:
    @pytest.mark.parametrize("agent", ["react_framework", "screen_reader", "svelte_framework"])
    def test_removed_parsing_criterion_is_never_cited_as_active(self, agent):
        prompt = _prompt(agent)
        assert "4.1.1" in prompt  # só para dizer que foi removido
        assert "WCAG 4.1.1," not in prompt
        assert "/ 4.1.1)" not in prompt
        assert "removed" in prompt.lower()

    def test_line_height_and_justified_text_are_not_1412_failures_by_themselves(self):
        prompt = _prompt("css_analyzer")
        assert "line-height below 1.2 (violates WCAG 1.4.12" not in prompt
        assert "NOT a 1.4.12 failure by itself" in prompt
        assert "fails WCAG 1.4.12" not in prompt
        assert "not a 1.4.12 failure" in prompt

    def test_label_in_name_is_level_a(self):
        assert "Level A, new in 2.1" in _prompt("compliance_audit")

    def test_chat_reference_does_not_present_focus_appearance_as_aa_or_apca_as_conformance(self):
        text = (_RESOURCES / "a11y_reference.md").read_text(encoding="utf-8")
        assert "2.4.13 (Aparência do Foco) é AAA" in text
        assert "Não faz parte do WCAG 2.2" in text
        assert "(Lc 60 para texto do corpo" not in text


class TestAriaSupport:
    def test_aria_checked_is_supported_on_option_and_aria_expanded_on_checkbox(self):
        prompt = _prompt("aria_specialist")
        assert "aria-checked is supported on: checkbox, menuitemcheckbox, menuitemradio, option" in prompt
        assert "aria-expanded is supported on: application, button, checkbox" in prompt
        assert "PROHIBITED on option, button, link, tab, combobox" not in prompt
        assert "listitem, checkbox, radio" not in prompt

    def test_time_and_blockquote_can_be_named_so_they_are_not_flagged(self):
        prompt = _prompt("aria_specialist")
        assert "<time> and <blockquote> CAN be named" in prompt
        assert "<sub>, <sup>, <del>, <ins>, <time>, <blockquote>)" not in prompt

    def test_popover_does_not_demand_a_particular_explicit_role(self):
        prompt = _prompt("wcag_semantics")
        assert "Popover containers MUST have an explicit semantic role" not in prompt
        assert "<dialog popover>" in prompt


class TestLiveRegionsAndToasts:
    def test_actionable_toast_reason_matches_what_live_regions_really_do(self):
        prompt = _prompt("fixer")
        assert "live regions strip interactive semantics" not in prompt
        assert "cannot be operated by screen reader users" not in prompt
        assert "announced as plain text" in prompt
        assert "must not take keyboard focus" in prompt
