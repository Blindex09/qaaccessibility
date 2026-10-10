"""O contrato de comportamento confere repetição (fato) e delega tom e qualidade dos achados a um juiz separado, com veredito validado."""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "behavior_judge.py"
spec = importlib.util.spec_from_file_location("behavior_judge", SCRIPT)
bj = importlib.util.module_from_spec(spec)
sys.modules["behavior_judge"] = bj
spec.loader.exec_module(bj)

EXPECTED = {"lang": "idioma", "title": "titulo"}


def verdict(**over) -> str:
    base = {"user_register": "direct", "answer_register": "direct", "tone_matches": True, "tone_why": "ok", "covered": ["lang", "title"], "missing": [], "invented": []}
    base.update(over)
    return json.dumps(base)


class TestRepeatedPassages:
    def test_same_sentence_twice_is_reported(self):
        text = "Vou analisar o projeto agora mesmo com os especialistas. Achei três problemas. Vou analisar o projeto agora mesmo com os especialistas!"
        assert len(bj.repeated_passages(text)) == 1

    def test_short_phrases_and_distinct_text_are_not(self):
        assert bj.repeated_passages("Certo. Certo. Esta é uma frase longa o bastante para contar. Esta é outra frase bem diferente da primeira aqui.") == []


class TestVerdictContract:
    def test_valid_verdict_passes(self):
        assert bj.parse_verdict(verdict(), EXPECTED).tone_matches is True

    def test_non_json_is_rejected(self):
        with pytest.raises(ValueError):
            bj.parse_verdict("não sei", EXPECTED)

    def test_defect_must_be_classified_exactly_once(self):
        with pytest.raises(ValueError):
            bj.parse_verdict(verdict(covered=["lang"], missing=[]), EXPECTED)
        with pytest.raises(ValueError):
            bj.parse_verdict(verdict(covered=["lang", "title"], missing=["title"]), EXPECTED)

    def test_unknown_defect_is_rejected(self):
        with pytest.raises(ValueError):
            bj.parse_verdict(verdict(covered=["lang", "title", "x"]), EXPECTED)

    def test_judge_retries_once_on_bad_format_then_gives_up(self):
        calls = []

        def ask(system, prompt):
            calls.append(prompt)
            return "lixo" if len(calls) == 1 else verdict()

        assert bj.judge(ask, "oi", "resposta", EXPECTED).covered == ["lang", "title"]
        assert len(calls) == 2
        with pytest.raises(ValueError):
            bj.judge(lambda s, p: "lixo", "oi", "resposta", EXPECTED)


class TestProblems:
    def test_tone_missing_and_invented_become_problems(self):
        parsed = bj.parse_verdict(verdict(tone_matches=False, tone_why="gíria com pessoa formal", covered=["lang"], missing=["title"], invented=["contraste 9:1"]), EXPECTED)
        problems = bj.problems_from(parsed, EXPECTED, min_covered=2)
        assert any("tom" in p for p in problems) and any("title" in p for p in problems) and any("9:1" in p for p in problems)

    def test_missing_defects_only_fail_against_a_measured_reference(self):
        parsed = bj.parse_verdict(verdict(covered=["lang"], missing=["title"]), EXPECTED)
        assert bj.problems_from(parsed, EXPECTED) == []
        assert bj.problems_from(parsed, EXPECTED, min_covered=1) == []
        assert bj.problems_from(parsed, EXPECTED, min_covered=2) != []

    def test_clean_verdict_has_no_problems(self):
        assert bj.problems_from(bj.parse_verdict(verdict(), EXPECTED), EXPECTED) == []

    def test_findings_are_not_required_without_ground_truth(self):
        parsed = bj.parse_verdict(verdict(covered=[], missing=[]), None)
        assert bj.problems_from(parsed, None) == []


def test_known_defects_match_the_test_project():
    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
    spec2 = importlib.util.spec_from_file_location("verify_live", Path(__file__).resolve().parents[3] / "scripts" / "verify_live_modules_1_to_3.py")
    assert spec2 is not None
    source = Path(spec2.origin).read_text(encoding="utf-8")
    for needle in ("logo.png", "<h4>", 'placeholder="Seu e-mail"', 'class="btn" onclick', "clique aqui", "<td>Ano</td>", "outline: none", "#aaaaaa"):
        assert needle in source
