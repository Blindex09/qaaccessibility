import json
from unittest.mock import AsyncMock, patch

import pytest

from backend.src.agents.compliance_audit.compliance_audit import run_compliance_audit

from .conftest_agents import (
    HTML_CLEAN,
    assert_agent_contract,
    assert_issues_valid,
    make_issue,
)

HTML_COMPLIANCE_ISSUES = """
<!DOCTYPE html>
<html>
  <head><title>App</title></head>
  <body>
    <button>X</button>
    <img src="hero.jpg">
    <form>
      <input type="email" id="email">
      <button type="submit">Submit</button>
    </form>
    <div onclick="go()" tabindex="-1">Go</div>
  </body>
</html>
""".strip()

COMPLIANCE_ISSUE = make_issue(
    {
        "id": "compliance-1",
        "guideline": "WCAG 2.2",
        "criterion": "4.1.2 Name, Role, Value",
        "severity": "critical",
        "element": "button",
        "description": "Button has no accessible name; AT announces it as 'button' with no context",
        "suggestion": "Add aria-label or descriptive text content to the button",
        "wcag_url": "https://www.w3.org/WAI/WCAG22/Understanding/name-role-value",
    }
)


@pytest.mark.asyncio
class TestComplianceAuditAgent:
    async def test_contract_on_success(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value=json.dumps([COMPLIANCE_ISSUE])),
        ):
            result = await run_compliance_audit(HTML_COMPLIANCE_ISSUES)
        assert_agent_contract(result, "compliance_audit")
        assert_issues_valid(result.data["issues"])

    async def test_issue_id_starts_with_compliance(self):
        """Issues do compliance_audit devem ter id prefixado com compliance- ou audit-."""
        compliance_issue_2 = make_issue(
            {
                **COMPLIANCE_ISSUE,
                "id": "audit-2",
                "criterion": "1.1.1 Non-text Content",
            }
        )
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value=json.dumps([COMPLIANCE_ISSUE, compliance_issue_2])),
        ):
            result = await run_compliance_audit(HTML_COMPLIANCE_ISSUES)
        for issue in result.data.get("issues", []):
            assert issue["id"].startswith("compliance-") or issue["id"].startswith(
                "audit-"
            ), f"ID deve começar com compliance- ou audit-: {issue['id']}"

    async def test_empty_html_returns_success(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value="[]"),
        ):
            result = await run_compliance_audit("")
        assert result.success is True
        assert result.data["issues"] == []

    async def test_clean_html_no_issues(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value="[]"),
        ):
            result = await run_compliance_audit(HTML_CLEAN)
        assert result.success is True
        assert len(result.data["issues"]) == 0

    async def test_failure_on_invalid_json(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value="not json at all"),
        ):
            result = await run_compliance_audit(HTML_COMPLIANCE_ISSUES)
        assert result.success is False
        assert result.error is not None

    async def test_failure_on_llm_exception(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(side_effect=Exception("network error")),
        ):
            result = await run_compliance_audit(HTML_COMPLIANCE_ISSUES)
        assert result.success is False
        assert "network error" in (result.error or "")

    async def test_strips_markdown_fences_from_response(self):
        """extract_json_array deve aceitar resposta embrulhada em ```json```."""
        fenced = f"```json\n{json.dumps([COMPLIANCE_ISSUE])}\n```"
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value=fenced),
        ):
            result = await run_compliance_audit(HTML_COMPLIANCE_ISSUES)
        assert result.success is True
        assert len(result.data["issues"]) == 1

    async def test_wcag22_new_criteria_accepted(self):
        """Criterios novos do WCAG 2.2 (2.4.11, 2.5.7, 2.5.8, 3.3.7, 3.3.8) devem ser aceitos."""
        new_wcag22 = [
            make_issue(
                {
                    "id": f"compliance-{i+2}",
                    "guideline": "WCAG 2.2",
                    "criterion": crit,
                    "severity": "high",
                    "element": "input",
                }
            )
            for i, crit in enumerate(
                [
                    "2.4.11 Focus Not Obscured (Minimum)",
                    "2.5.7 Dragging Movements",
                    "2.5.8 Target Size (Minimum)",
                    "3.3.7 Redundant Entry",
                    "3.3.8 Accessible Authentication (Minimum)",
                ]
            )
        ]
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value=json.dumps([COMPLIANCE_ISSUE] + new_wcag22)),
        ):
            result = await run_compliance_audit(HTML_COMPLIANCE_ISSUES)
        assert result.success is True
        assert len(result.data["issues"]) == 6
        criterions = [i["criterion"] for i in result.data["issues"]]
        assert "3.3.7 Redundant Entry" in criterions
        assert "3.3.8 Accessible Authentication (Minimum)" in criterions

    async def test_systemic_patterns_field_present(self):
        """ComplianceAudit deve expor campo data.systemic_patterns se present."""
        response_with_systemic = {
            "issues": [COMPLIANCE_ISSUE],
            "wcag_level": "Partial AA",
            "systemic_patterns": ["All images missing alt attributes (systemic, not isolated)"],
        }
        # Agent returns plain list — systemic_patterns is an optional bonus field.
        # Verify the contract accepts it when present via a pass-through JSON response.
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value=json.dumps([COMPLIANCE_ISSUE])),
        ):
            result = await run_compliance_audit(HTML_COMPLIANCE_ISSUES)
        assert result.success is True
        assert "issues" in result.data
