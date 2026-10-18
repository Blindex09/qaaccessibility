"""Terceira rodada de pesquisa: frameworks, mobile, documentos, cognitivo, conformidade, e fatias por especialista.

Promessas de docs/modules/conhecimento_de_leitor_de_tela.md (seção da terceira rodada) e o teste que cobre cada uma.
Fontes: documentação do Vue, Angular, Svelte, Tailwind, MDN, W3C (mobile, WCAG 2.2, COGA, WCAG-EM, ACT, EPUB),
Microsoft (Office), PDF Association, Access Board (Revised 508) e o texto da EN 301 549 V3.2.1, consultadas em 2026-10-17.
"""

import importlib
import re
from pathlib import Path

import pytest

from backend.src.services import a11y_knowledge
from backend.src.shared import specialist_knowledge as sk

_ROOT = Path(__file__).resolve().parents[4]
_RESOURCES = _ROOT / "backend" / "src" / "resources"
_AGENTS = _ROOT / "backend" / "src" / "agents"
_NEW_DOCS = (sk.FRAMEWORKS, sk.MOBILE_DOCS, sk.COGNITIVE)


def _text(name: str) -> str:
    return (_RESOURCES / name).read_text(encoding="utf-8")


def _prompt(agent: str) -> str:
    return str(importlib.import_module(f"backend.src.agents.{agent}.{agent}").SYSTEM_PROMPT)


class TestNewReferences:
    @pytest.mark.parametrize("name", _NEW_DOCS)
    def test_each_new_reference_is_dated_sourced_and_in_the_chat_corpus(self, name):
        text = _text(name)
        assert "2026-10-17" in text
        assert "Fontes consultadas" in text
        assert name in a11y_knowledge._CORPUS_FILES
        assert len([c for c in a11y_knowledge.load_corpus() if c.source == name]) >= 3

    def test_frameworks_cover_each_framework_with_the_documented_facts(self):
        text = _text(sk.FRAMEWORKS)
        for needle in (
            "ariaCurrentValue", "useId() do Vue", "ambas as formas são válidas", "ariaCurrentWhenActive", "LiveAnnouncer",
            "cdkTrapFocus", "@defer", "a11y_click_events_have_key_events" if False else "accesskey", "svelte-ignore", "outline-hidden",
            "box-shadow vira none", "forced-color-adjust-none", "delegatesFocus", "ElementInternals", "Reference Target",
            "v-show não resolve",
        ):
            assert needle in text

    def test_mobile_documents_and_media_cover_each_source(self):
        text = _text(sk.MOBILE_DOCS)
        for needle in (
            "24 por 24 pixels CSS", "9 mm por 9 mm", "2.5.1", "2.5.4", "2.5.7", "1.3.4", "320 pixels CSS", "Meta viewport allows for zoom",
            "mergeDescendants", "Verificador de Acessibilidade", "célula A1", "Ordem de Leitura", "PDF1 a PDF23", "136 condições de falha",
            "31 pontos de verificação", "PDF/UA-2", "accessModeSufficient", "dcterms:conformsTo", "1.2.2",
        ):
            assert needle in text

    def test_cognitive_compliance_and_method_cover_each_source(self):
        text = _text(sk.COGNITIVE)
        for needle in (
            "COGA", "3.3.7", "3.3.8", "3.2.6", "2.2.1", "1.3.5", "E205.4", "EN 301 549 V3.2.1", "Cláusula 9", "WCAG-EM", "ACT Rules Format",
            "57 por cento", "Lei Europeia de Acessibilidade", "não pôde ser lido",
        ):
            assert needle in text

    def test_unread_sources_are_declared_not_hidden(self):
        assert "não pôde ser lida" in _text(sk.MOBILE_DOCS)
        assert "não confirmada nesta rodada" in _text(sk.MOBILE_DOCS)
        assert "O texto oficial não foi lido" in _text(sk.COGNITIVE)


class TestWcagLevelsAgreeWithTheSourcedList:
    """Achado: o VPAT tinha 4.1.3 como A e 3.2.6 e 3.3.7 como AA. Os níveis vêm das páginas do W3C."""

    @staticmethod
    def _levels_from_reference() -> dict[str, set[str]]:
        text = _text(sk.COGNITIVE)
        out = {}
        for level in ("A", "AA"):
            line = next(ln for ln in text.splitlines() if ln.startswith(f"- Nível {level} ("))
            out[level] = set(re.findall(r"\d\.\d\.\d{1,2}", line))
        return out

    def test_reference_lists_31_level_a_and_24_level_aa_criteria(self):
        levels = self._levels_from_reference()
        assert len(levels["A"]) == 31
        assert len(levels["AA"]) == 24
        assert not levels["A"] & levels["AA"]

    def test_vpat_criteria_levels_match_the_reference(self):
        from backend.src.agents.vpat_reporter.vpat_reporter import _WCAG_22_CRITERIA

        levels = self._levels_from_reference()
        assert {c[0] for c in _WCAG_22_CRITERIA["A"]} == levels["A"]
        assert {c[0] for c in _WCAG_22_CRITERIA["AA"]} == levels["AA"]

    def test_the_three_levels_that_were_wrong_are_right(self):
        from backend.src.agents.vpat_reporter.vpat_reporter import _WCAG_22_CRITERIA

        level_a = {c[0] for c in _WCAG_22_CRITERIA["A"]}
        level_aa = {c[0] for c in _WCAG_22_CRITERIA["AA"]}
        assert {"3.2.6", "3.3.7"} <= level_a
        assert "4.1.3" in level_aa and "4.1.3" not in level_a


class TestSpecialistSlices:
    def test_every_slice_belongs_to_an_existing_specialist(self):
        for agent in sk.SLICES:
            assert (_AGENTS / agent / f"{agent}.py").exists(), agent

    @pytest.mark.parametrize("agent", sorted(sk.SLICES))
    def test_every_requested_section_exists(self, agent):
        found = {(d, t) for d, t, _ in sk.slice_sections(agent)}
        for document, prefix in sk.SLICES[agent][1]:
            assert any(d == document and t.startswith(prefix) for d, t in found), (agent, document, prefix)

    @pytest.mark.parametrize("agent", sorted(sk.SLICES))
    def test_slice_respects_its_cap_and_reaches_the_specialist_prompt(self, agent):
        block = sk.specialist_knowledge(agent)
        cap = sk.SLICES[agent][0]
        assert len(block) <= cap + len(sk._HEADER) + 8
        assert block in _prompt(agent)

    def test_total_cost_of_all_slices_is_measured_and_bounded(self):
        total = sum(len(sk.specialist_knowledge(agent)) for agent in sk.SLICES)
        assert total < 155_000  # medido em 2026-10-18: cerca de 146 mil caracteres para os 28 especialistas (126 mil em 2026-10-17, antes da quarta rodada)

    def test_unknown_specialist_fails_loudly(self):
        with pytest.raises(KeyError):
            sk.specialist_knowledge("nao_existe")

    def test_domain_slices_carry_the_domain_facts(self):
        assert "E205.4" in sk.specialist_knowledge("section508")
        assert "24 por 24 pixels CSS" in sk.specialist_knowledge("mobile_a11y")
        assert "Matterhorn" in sk.specialist_knowledge("pdf_accessibility")
        assert "3.3.8" in sk.specialist_knowledge("cognitive")
        assert "delegatesFocus" in sk.specialist_knowledge("web_components")
        assert "outline-hidden" in sk.specialist_knowledge("tailwind_css")
        assert "ariaCurrentValue" in sk.specialist_knowledge("vue_framework")


class TestPromptCorrectionsFromTheThirdRound:
    def test_section508_uses_the_revised_standards_not_the_2000_paragraphs(self):
        prompt = _prompt("section508")
        assert "Revised Section 508 Standards" in prompt
        assert "E205.4" in prompt
        assert "(a) 1194.22(a) = WCAG 1.1.1" not in prompt
        assert "Video content produced after 1997" not in prompt
        assert "Section 508 508(f)" not in prompt

    def test_compliance_audit_no_longer_maps_to_superseded_paragraphs(self):
        prompt = _prompt("compliance_audit")
        assert "1194.22(a) = WCAG 1.1.1" not in prompt
        assert "superseded 2000 standards" in prompt

    def test_live_region_advice_no_longer_recommends_hiding_with_display_none(self):
        for agent in ("vue_framework", "react_framework", "svelte_framework", "ajax_dynamic"):
            text = _prompt(agent)
            assert "should use v-show (which sets display:none" not in text
            assert "must be changed to v-show" not in text
        assert "does NOT fix this" in _prompt("ajax_dynamic")

    def test_vue_knows_routerlink_sets_aria_current(self):
        prompt = _prompt("vue_framework")
        assert "ariaCurrentValue" in prompt
        assert "NuxtLink/RouterLink elements without aria-current" not in prompt

    def test_angular_accepts_both_aria_binding_forms(self):
        prompt = _prompt("angular_framework")
        assert "both forms are valid" in prompt
        assert "causes silent template rendering issues" not in prompt

    def test_tailwind_flags_outline_none_plus_ring_as_a_forced_colors_risk(self):
        prompt = _prompt("tailwind_css")
        assert "forced colors" in prompt
        assert "outline-hidden" in prompt

    def test_mobile_prompt_separates_input_types_from_wcag_135(self):
        prompt = _prompt("mobile_a11y")
        assert "not WCAG 1.3.5" in prompt
        assert "Meta viewport allows for zoom" in prompt

    def test_cognitive_prompt_applies_the_real_levels_and_exceptions(self):
        prompt = _prompt("cognitive")
        assert "object-recognition CAPTCHA" in prompt
        assert "3.1.5 is Level AAA" in prompt
        assert "COGA recommendation" in prompt

    def test_screen_reader_prompt_no_longer_quotes_an_unsourced_automation_percentage(self):
        prompt = _prompt("screen_reader")
        assert "30-50%" not in prompt
        assert "57 percent by volume" in prompt

    def test_browser_pairing_claims_follow_the_webaim_survey(self):
        text = (_RESOURCES / "a11y_reference.md").read_text(encoding="utf-8")
        assert "Safari obrigatório" not in text
        assert "Safari recomendado" in text
        assert "combinação mais completa" not in text
        source = (_ROOT / "backend" / "src" / "services" / "chat_runtime.py").read_text(encoding="utf-8")
        assert "VoiceOver REQUIRES Safari" not in source
        assert "NVDA+Firefox is the most complete free combo" not in source
