import pytest
from pydantic import ValidationError

from backend.src.shared.models import (
    AccessibilityIssue,
    AgentResult,
    AnalyzeUrlRequest,
    Guideline,
    ReportOutput,
    Severity,
)


class TestAccessibilityIssue:
    def test_create_valid_issue(self, sample_issue):
        assert sample_issue.id == "issue-001"
        assert sample_issue.severity == Severity.CRITICAL
        assert sample_issue.guideline == Guideline.WCAG_2_2

    def test_normalizes_uppercase_severity(self):
        issue = AccessibilityIssue(
            id="issue-uppercase",
            guideline="WCAG 2.2",
            criterion="1.1.1 Non-text Content",
            severity="CRITICAL",
            element="img",
            description="Image missing alt attribute",
            suggestion="Add a descriptive alt attribute",
        )

        assert issue.severity == Severity.CRITICAL

    def test_issue_missing_required_field(self):
        with pytest.raises(ValidationError):
            AccessibilityIssue(
                id="x",
                guideline=Guideline.WCAG_2_2,
                # criterion ausente
                severity=Severity.HIGH,
                element="div",
                description="desc",
                suggestion="fix",
            )


class TestReportOutput:
    def test_score_boundaries(self, sample_issue, sample_checklist_item):
        report = ReportOutput(
            report_id="r-001",
            summary="Test",
            score=85,
            issues=[sample_issue],
            checklist=[sample_checklist_item],
        )
        assert 0 <= report.score <= 100

    def test_score_below_zero_raises(self, sample_issue, sample_checklist_item):
        with pytest.raises(ValidationError):
            ReportOutput(
                report_id="r-002",
                summary="Test",
                score=-1,
                issues=[],
                checklist=[],
            )

    def test_score_above_100_raises(self):
        with pytest.raises(ValidationError):
            ReportOutput(
                report_id="r-003",
                summary="Test",
                score=101,
                issues=[],
                checklist=[],
            )


class TestAgentResult:
    def test_success_result(self):
        result = AgentResult(agent="analyzer", success=True, data={"issues": []})
        assert result.success is True
        assert result.error is None

    def test_failure_result(self):
        result = AgentResult(
            agent="analyzer",
            success=False,
            data={},
            error="Timeout",
        )
        assert result.success is False
        assert result.error == "Timeout"


class TestAnalyzeUrlRequest:
    def test_valid_url(self):
        req = AnalyzeUrlRequest(url="https://example.com")
        assert req.url == "https://example.com"
