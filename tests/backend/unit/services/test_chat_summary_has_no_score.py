"""O assistente não conta ao usuário uma nota numérica inventada (regra 11).

A nota antiga era 100 menos pontos por severidade: sem relação com conformidade
WCAG nem com o tamanho da página, e um "100" soava como "está conforme". O
resumo que o modelo narra traz só a contagem por severidade e os principais achados.
"""

from backend.src.services.chat_tools import _ANALYZE_PAGE_SCHEMA, _summarize_issues


def _issue(severity: str) -> dict:
    return {"severity": severity, "criterion": "1.1.1", "element": "img", "description": "x"}


def test_summary_counts_by_severity_without_any_numeric_score():
    summary = _summarize_issues([_issue("high")] + [_issue("medium")] * 5)
    assert summary["counts_by_severity"] == {"critical": 0, "high": 1, "medium": 5, "low": 0}
    assert summary["total_issues"] == 6
    assert "score" not in summary


def test_no_findings_is_not_presented_as_a_perfect_score():
    summary = _summarize_issues([])
    assert summary["total_issues"] == 0
    assert "score" not in summary


def test_tool_description_tells_the_model_not_to_invent_a_score():
    description = _ANALYZE_PAGE_SCHEMA["description"]
    assert "(0-100)" not in description
    assert "no numeric score" in description
