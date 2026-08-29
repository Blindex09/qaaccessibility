import json
from unittest.mock import AsyncMock, patch

import pytest

from backend.src.agents.reporter.reporter import _calculate_score, run_reporter
from backend.src.shared.models import AccessibilityIssue, Guideline, Severity


def make_issue(severity: Severity) -> AccessibilityIssue:
    return AccessibilityIssue(
        id=f"issue-{severity}",
        guideline=Guideline.WCAG_2_2,
        criterion="1.1.1 Non-text Content",
        severity=severity,
        element="img",
        description="desc",
        suggestion="fix",
    )


class TestCalculateScore:
    def test_no_issues_returns_100(self):
        assert _calculate_score([]) == 100

    def test_one_critical_deducts_20(self):
        assert _calculate_score([make_issue(Severity.CRITICAL)]) == 80

    def test_one_high_deducts_10(self):
        assert _calculate_score([make_issue(Severity.HIGH)]) == 90

    def test_score_never_below_zero(self):
        issues = [make_issue(Severity.CRITICAL)] * 10
        assert _calculate_score(issues) == 0


MOCK_REPORT_RESPONSE = {
    "summary": "The page has 1 critical accessibility issue.",
    "score": 80,
}


@pytest.mark.asyncio
class TestReporterAgent:
    async def test_returns_report_on_success(self, sample_issue, sample_checklist_item):
        with patch(
            "backend.src.agents.reporter.reporter.call_llm",
            new=AsyncMock(return_value=json.dumps(MOCK_REPORT_RESPONSE)),
        ):
            result = await run_reporter([sample_issue], [sample_checklist_item])

        assert result.success is True
        assert result.agent == "reporter"
        assert result.data["score"] == 80
        assert "summary" in result.data

    async def test_failure_on_llm_exception(self, sample_issue, sample_checklist_item):
        with patch(
            "backend.src.agents.reporter.reporter.call_llm",
            new=AsyncMock(side_effect=Exception("err")),
        ):
            result = await run_reporter([sample_issue], [sample_checklist_item])

        assert result.success is False
