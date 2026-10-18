"""O texto que o modelo recebe traz as regras de comportamento do CLAUDE.md e nao se contradiz.

Fatos objetivos conferidos (numeracao e referencias entre regras) e a presenca das regras de narracao e de autonomia
(regras 3 e 5 do CLAUDE.md), que ficaram sem texto quando a numeracao do prompt mudou. Quem aplica o conteudo e o modelo.
"""

import re

from backend.src.services.chat_runtime import SYSTEM_PROMPT


def _defined() -> list[str]:
    return re.findall(r"(?m)^(\d+[a-c]?)\. ", SYSTEM_PROMPT)


def test_every_rule_number_in_the_prompt_is_unique():
    defined = _defined()
    assert len(defined) == len(set(defined)), sorted(n for n in set(defined) if defined.count(n) > 1)


def test_no_rule_refers_to_a_rule_that_does_not_exist():
    defined = {re.match(r"\d+", n).group() for n in _defined()}
    referred = set(re.findall(r"\brules? (\d+)", SYSTEM_PROMPT)) | set(re.findall(r"rules \d+/(\d+)", SYSTEM_PROMPT))
    assert referred <= defined, sorted(referred - defined)


def test_rule_that_the_spoken_explanation_points_to_is_the_narration_rule():
    number = re.search(r"rule (\d+)'s spoken explanation", SYSTEM_PROMPT).group(1)
    assert re.search(rf"(?m)^{number}\. NARRATION WHILE YOU WORK", SYSTEM_PROMPT)


def test_narration_rule_carries_the_conversation_behaviour():
    text = SYSTEM_PROMPT[SYSTEM_PROMPT.index("NARRATION WHILE YOU WORK"):]
    for needle in ("text, tool call, text", "match what you do", "adds something new", "technical name", "interrupt"):
        assert needle in text


def test_autonomy_rule_carries_the_autonomy_and_honest_delivery_behaviour():
    text = SYSTEM_PROMPT[SYSTEM_PROMPT.index("AUTONOMY AND HONEST DELIVERY"):]
    for needle in ("not installed or not running", "another route", "needlessly", "what was verified"):
        assert needle in text
