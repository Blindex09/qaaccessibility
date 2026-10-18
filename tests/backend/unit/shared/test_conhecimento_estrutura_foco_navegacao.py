"""Quarta rodada de pesquisa: ordem de foco, titulos, listas, tabelas, grade e navegacao por leitor de tela.

Fontes: W3C (WCAG 2.2, tutoriais de tabelas e titulos, padrao de grade), MDN (tabindex, flex order, reading-flow, roles
table/list), guia do usuario do NVDA, Apple e Freedom Scientific (por resumo), Angular e WebKit, consultadas em 2026-10-18.
"""

from pathlib import Path

import pytest

from backend.src.services import a11y_knowledge
from backend.src.shared import specialist_knowledge as sk

_RESOURCES = Path(__file__).resolve().parents[4] / "backend" / "src" / "resources"


def _text() -> str:
    return (_RESOURCES / sk.STRUCTURE).read_text(encoding="utf-8")


def test_reference_is_dated_sourced_and_in_the_chat_corpus():
    text = _text()
    assert "2026-10-18" in text and "Fontes consultadas" in text
    assert sk.STRUCTURE in a11y_knowledge._CORPUS_FILES
    assert len([c for c in a11y_knowledge.load_corpus() if c.source == sk.STRUCTURE]) >= 4
    assert "*" not in text


@pytest.mark.parametrize(
    "needle",
    [
        "2.4.3", "F44", "F85", "SCR26", "tabindex", "reading-flow", "ignorados dentro de um contêiner", "2.4.11", "2.4.10",
        "aria-level igual ao número da tag", "pular níveis", "list-style none", "role list", "dezembro de 2025",
        "listitem só pode estar dentro", "presentation", "scope", "headers", "colgroup", "aria-rowcount", "-1 se o total",
        "Ctrl+Alt+Home", "NVDA+F7", "shift+vírgula", "VO-R-R", "Alt+Ctrl+seta direita", "Ctrl+Home", "Enter ou F2",
    ],
)
def test_reference_carries_each_sourced_fact(needle):
    assert needle in _text()


def test_unverified_items_are_declared_not_hidden():
    text = _text()
    assert "Não pôde ser lido" in text
    assert "não pôde ser lida" in text
    assert "não foi confirmado" in text.lower() or "não foi confirmado" in text


@pytest.mark.parametrize("agent", ["screen_reader", "tables_data", "wcag_semantics", "operability", "css_analyzer", "interaction_pattern"])
def test_specialist_slice_includes_the_structure_sections(agent):
    found = {(d, t) for d, t, _ in sk.slice_sections(agent)}
    wanted = [prefix for doc, prefix in sk.SLICES[agent][1] if doc == sk.STRUCTURE]
    assert wanted
    for prefix in wanted:
        assert any(d == sk.STRUCTURE and t.startswith(prefix) for d, t in found), (agent, prefix)
