"""Conhecimento sobre o que o leitor de tela fala e faz em cada elemento e comportamento.

Promessas de docs/modules/conhecimento_de_leitor_de_tela.md e o teste que cobre cada uma. O conteúdo vem
de pesquisa em documentação oficial (W3C, MDN, React, Astro, Next.js, NVDA, WebAIM) e nos testes públicos de
suporte de HTML da TetraLogical, feita em 2026-10-17.
"""

import importlib
from pathlib import Path

import pytest

from backend.src.services import a11y_knowledge
from backend.src.shared.screen_reader_calibration import SCREEN_READER_EXPECTATIONS

_RESOURCES = Path(__file__).resolve().parents[4] / "backend" / "src" / "resources"
_DOCS = (
    "leitor_de_tela_elementos_html.md",
    "leitor_de_tela_aria_e_padroes.md",
    "leitor_de_tela_dinamico_js_react.md",
    "leitor_de_tela_css_e_modos.md",
)


def _text(name: str) -> str:
    return (_RESOURCES / name).read_text(encoding="utf-8")


def _prompt(agent: str) -> str:
    return str(importlib.import_module(f"backend.src.agents.{agent}.{agent}").SYSTEM_PROMPT)


class TestSourcesAndCorpus:
    @pytest.mark.parametrize("name", _DOCS)
    def test_every_reference_declares_dated_official_sources(self, name):
        text = _text(name)
        assert "Consultadas em 2026-10-17" in text or "2026-10-17" in text
        assert any(host in text for host in ("w3.org", "MDN", "TetraLogical", "WebAIM", "NVDA"))

    @pytest.mark.parametrize("name", _DOCS)
    def test_every_reference_is_in_the_chat_retrieval_corpus_in_bounded_chunks(self, name):
        assert name in a11y_knowledge._CORPUS_FILES
        chunks = [c for c in a11y_knowledge.load_corpus() if c.source == name]
        assert len(chunks) >= 3
        assert all(c.text.strip() for c in chunks)
        assert max(len(c.text) for c in chunks) < 9000  # um trecho recuperado não pode estourar o contexto do turno


class TestRetrievalBudget:
    """Achado ao ligar estas referências: a busca devolvia seções inteiras e o bloco de referência do turno
    passou de 16 mil caracteres, estourando o teste de economia do índice. Seções longas agora são repartidas."""

    def test_long_sections_are_split_on_whole_lines(self):
        lines = [f"Linha {n} " + "x" * 300 for n in range(20)]
        parts = a11y_knowledge._split_by_size("\n".join(lines))
        assert len(parts) > 1
        assert "\n".join(parts).split("\n") == lines  # nada perdido nem cortado no meio
        assert all(len(part) <= a11y_knowledge._MAX_CHUNK_CHARS for part in parts)

    def test_short_sections_stay_whole(self):
        assert a11y_knowledge._split_by_size("curto") == ["curto"]

    def test_split_titles_say_which_part_they_are(self):
        content = "## Tema\n" + "\n".join(f"Linha {n} " + "y" * 400 for n in range(15))
        chunks = a11y_knowledge.chunk_markdown(content, "x.md")
        assert len(chunks) > 1
        assert chunks[0].title.startswith("Tema (parte 1 de ")

    def test_no_corpus_chunk_exceeds_the_budget_unless_one_line_does(self):
        for chunk in a11y_knowledge.load_corpus():
            longest_line = max(len(line) for line in chunk.text.splitlines())
            assert len(chunk.text) <= max(a11y_knowledge._MAX_CHUNK_CHARS, longest_line + 1)


class TestHtmlElementsCoverage:
    @pytest.mark.parametrize(
        "needle",
        [
            "Cabeçalhos h1 a h6", "Listas ul e ol", "a sem href", "button e input", "Campos de texto", "password",
            "number", "range", "date, time e color", "textarea", "checkbox", "radio", "select", "optgroup",
            "datalist", "fieldset e legend", "table é falada", "img com alt", "alt vazio", "svg", "canvas",
            "figure", "header e footer", "main, nav e aside", "form e section", "article", "details e summary",
            "dialog aberto com showModal", "progress", "meter", "abbr", "mark", "del e ins", "audio", "video",
            "iframe", "embed e object", "noscript", "title",
        ],
    )
    def test_each_html_element_family_has_an_entry(self, needle):
        assert needle in _text("leitor_de_tela_elementos_html.md")

    def test_readers_and_versions_are_named_with_the_caveat_that_speech_varies(self):
        text = _text("leitor_de_tela_elementos_html.md")
        for fragment in ("NVDA 2024 com Chrome 129", "JAWS 2026 com Chrome 148", "Sequoia 15.5", "iOS 18.6.2", "TalkBack de 2025", "Narrator de 2025"):
            assert fragment in text
        assert "A frase exata falada" in text
        assert "nunca como prova de conformidade" in text or "não para provar conformidade" in text


class TestAriaPatternsCoverage:
    @pytest.mark.parametrize(
        "needle",
        [
            "Diálogo (dialog) e diálogo de alerta", "Abas (tabs)", "Acordeão e divulgação", "Navegação por divulgação",
            "Menu de aplicativo", "Combobox, listbox e select", "Dicas, balões e avisos", "Casos de estado de formulário",
            "Controles básicos", "Toolbar, carrossel, breadcrumb, landmarks", "Tabela e grade", "árvore (tree)",
            "aria-hidden", "role=\"presentation\"", "role=\"application\"", "aria-activedescendant", "aria-errormessage",
        ],
    )
    def test_each_pattern_and_attribute_has_an_entry(self, needle):
        assert needle in _text("leitor_de_tela_aria_e_padroes.md")

    def test_site_navigation_is_a_disclosure_and_not_a_role_menu(self):
        text = _text("leitor_de_tela_aria_e_padroes.md")
        assert "sem o papel menu" in text
        assert "Só para comandos de aplicativo" in text

    def test_native_dialog_guidance_matches_the_sources_on_tabindex_and_focus_return(self):
        text = _text("leitor_de_tela_aria_e_padroes.md")
        assert "não pôr tabindex no próprio dialog" in text
        assert "O MDN não documenta o retorno do foco" in text


class TestDynamicAndFrameworkCoverage:
    @pytest.mark.parametrize(
        "needle",
        [
            "Região viva", "aria-busy", "WCAG 4.1.3", "Foco: a ferramenta mais importante", "tabindex", "inert",
            "Popover API", "3.2.2", "2.2.2", "Formulários e validação", "## React", "useId", "htmlFor", "Fragment",
            "ClientRouter", "astro:page-load", "transition:persist", "Next.js",
        ],
    )
    def test_each_dynamic_and_framework_topic_has_an_entry(self, needle):
        assert needle in _text("leitor_de_tela_dinamico_js_react.md")

    def test_live_region_rules_match_mdn_and_the_apg(self):
        text = _text("leitor_de_tela_dinamico_js_react.md")
        assert "incluí-la na marcação inicial, vazia" in text
        assert "texto simples" in text
        assert "O APG diz que um alert não deve tomar o foco" in text

    def test_unconfirmed_claims_are_labelled_as_such(self):
        assert "não foi confirmado nas fontes lidas" in _text("leitor_de_tela_css_e_modos.md")
        assert "Orientação consagrada, não está na página de acessibilidade do React" in _text("leitor_de_tela_dinamico_js_react.md")


class TestCssAndReaderModes:
    @pytest.mark.parametrize(
        "needle",
        [
            "display none", "sr-only", "opacity 0", "Conteúdo gerado", "forced-colors", "box-shadow", "prefers-reduced-motion",
            "1.4.12", "APCA não faz parte do WCAG 2.2", "NVDA (Windows, gratuito)", "JAWS (Windows)", "VoiceOver no macOS",
            "VoiceOver no iOS", "TalkBack no Android", "Narrator", "40,5%", "37,7%", "Limites desta referência",
        ],
    )
    def test_each_css_effect_and_reader_has_an_entry(self, needle):
        assert needle in _text("leitor_de_tela_css_e_modos.md")


class TestCompactBlockAndWiring:
    def test_block_states_defined_versus_observed_and_the_silent_spots(self):
        assert "never assert an" in SCREEN_READER_EXPECTATIONS.replace("\n", " ") or "Never assert an" in SCREEN_READER_EXPECTATIONS.replace("\n", " ")
        for fragment in ("plain text", "alt=\"\"", "aria-hidden removes content", "disclosure pattern", "ClientRouter"):
            assert fragment in SCREEN_READER_EXPECTATIONS

    def test_block_facts_exist_in_the_sourced_references(self):
        everything = "".join(_text(name) for name in _DOCS)
        for fragment in ("alt vazio", "aria-hidden", "Navegação por divulgação", "ClientRouter", "texto simples"):
            assert fragment in everything

    @pytest.mark.parametrize("agent", ["screen_reader", "aria_specialist", "forms_a11y", "ajax_dynamic", "a11y_expert_reviewer"])
    def test_specialists_receive_the_block(self, agent):
        assert SCREEN_READER_EXPECTATIONS in _prompt(agent)

    def test_reviewer_keeps_the_normative_contract_last(self):
        from backend.src.shared.normative_calibration import NORMATIVE_CALIBRATION

        assert _prompt("a11y_expert_reviewer").endswith(NORMATIVE_CALIBRATION)

    def test_chat_prompt_builder_includes_the_block(self):
        source = (Path(__file__).resolve().parents[4] / "backend" / "src" / "services" / "chat_runtime.py").read_text(encoding="utf-8")
        assert "SCREEN_READER_EXPECTATIONS" in source


class TestCorrectionsFoundByTheResearch:
    def test_screen_reader_agent_no_longer_says_live_regions_strip_semantics_or_forces_one_route_technique(self):
        prompt = _prompt("screen_reader")
        assert "STRIP all semantics" not in prompt
        assert "NEVER rely on aria-live" not in prompt
        assert "Judge by outcome, not by one technique" in prompt
        assert "do not require both" in prompt

    def test_missing_h1_and_skipped_levels_are_recommendations_not_failures(self):
        prompt = _prompt("screen_reader")
        assert "no h1 = no entry point" not in prompt
        assert "NOT a\n    standalone WCAG failure" in prompt
        assert 'element": "<body> (no <h1> present)"' not in prompt

    def test_missing_alt_is_described_per_reader_and_empty_alt_stays_valid(self):
        prompt = _prompt("screen_reader")
        assert "SR announces filename" not in prompt
        assert "VoiceOver reads the file name" in prompt
        assert 'alt="" is valid' in prompt

    def test_ajax_specialist_does_not_present_a_fixed_delay_as_a_rule(self):
        prompt = _prompt("ajax_dynamic")
        assert "delay 100–500ms after AJAX" not in prompt
        assert "no fixed number applies" in prompt
