from unittest.mock import AsyncMock, patch

import pytest

from backend.src.agents.gap_research.gap_research import (
    MAX_GAP_RESEARCH_ISSUES,
    run_gap_research_check,
)
from backend.src.shared.models import AccessibilityIssue, Confidence, Severity


def make_issue(id: str, confidence: Confidence = Confidence.LOW) -> AccessibilityIssue:
    return AccessibilityIssue(
        id=id,
        guideline="WCAG 2.2",
        criterion="1.1.1 Non-text Content",
        severity=Severity.MEDIUM,
        element="<img>",
        description="desc",
        suggestion="fix",
        confidence=confidence,
    )


@pytest.mark.asyncio
class TestGapResearchCheck:
    async def test_empty_issues_short_circuits_without_research_call(self):
        with patch(
            "backend.src.agents.deep_research.deep_research.run_deep_research",
            new=AsyncMock(side_effect=AssertionError("nao deveria pesquisar")),
        ):
            result = await run_gap_research_check([])
        assert result.success is True
        assert result.data["answer"] == ""

    async def test_research_answer_returned_with_covered_issue_ids(self):
        issue = make_issue("p-1")
        with patch(
            "backend.src.agents.deep_research.deep_research.run_deep_research",
            new=AsyncMock(return_value={
                "answer": "WCAG 1.1.1 confirms this is a genuine violation.",
                "question": "...", "status": "ok",
            }),
        ):
            result = await run_gap_research_check([issue])
        assert result.success is True
        assert "1.1.1" in result.data["answer"]
        assert result.data["issue_ids"] == ["p-1"]

    async def test_caps_at_max_gap_research_issues(self):
        issues = [make_issue(f"p-{i}") for i in range(6)]
        with patch(
            "backend.src.agents.deep_research.deep_research.run_deep_research",
            new=AsyncMock(return_value={"answer": "ok", "question": "...", "status": "ok"}),
        ):
            result = await run_gap_research_check(issues)
        assert len(result.data["issue_ids"]) == MAX_GAP_RESEARCH_ISSUES

    async def test_research_failure_degrades_gracefully(self):
        with patch(
            "backend.src.agents.deep_research.deep_research.run_deep_research",
            new=AsyncMock(return_value={"answer": "", "question": "...", "status": "error", "error": "sem chave de API"}),
        ):
            result = await run_gap_research_check([make_issue("p-1")])
        assert result.success is False
        assert result.data["answer"] == ""

    async def test_research_exception_degrades_gracefully(self):
        with patch(
            "backend.src.agents.deep_research.deep_research.run_deep_research",
            new=AsyncMock(side_effect=Exception("timeout")),
        ):
            result = await run_gap_research_check([make_issue("p-1")])
        assert result.success is False
        assert "timeout" in result.error
