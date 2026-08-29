import json
from unittest.mock import AsyncMock, patch

import pytest

from backend.src.agents.section508.section508 import run_section508

from .conftest_agents import (
    HTML_WITH_ISSUES,
    assert_agent_contract,
    assert_issues_valid,
    make_issue,
)

S508_ISSUE = make_issue(
    {
        "id": "s508-1",
        "guideline": "ADA/Section 508",
        "criterion": "1194.22(a) Text Equivalent",
        "severity": "critical",
        "element": "img",
        "description": "Image element missing text equivalent as required by Section 508 1194.22(a)",
        "suggestion": "Provide alt attribute with descriptive text",
    }
)


@pytest.mark.asyncio
class TestSection508Agent:
    async def test_contract_on_success(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value=json.dumps([S508_ISSUE])),
        ):
            result = await run_section508(HTML_WITH_ISSUES)
        assert_agent_contract(result, "section508")
        assert_issues_valid(result.data["issues"])

    async def test_guideline_is_ada_508(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value=json.dumps([S508_ISSUE])),
        ):
            result = await run_section508(HTML_WITH_ISSUES)
        for issue in result.data.get("issues", []):
            assert (
                issue["guideline"] == "ADA/Section 508"
            ), f"Section508 retornou guideline errada: {issue['guideline']}"

    async def test_failure_on_llm_exception(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(side_effect=Exception("err")),
        ):
            result = await run_section508(HTML_WITH_ISSUES)
        assert result.success is False
        assert result.error is not None

    async def test_1194_22_web_criteria_accepted(self):
        """Criterios 1194.22 (n) devem ser aceitos pelo section508."""
        criteria_22 = [
            make_issue(
                {
                    "id": f"s508-{i+2}",
                    "guideline": "ADA/Section 508",
                    "criterion": crit,
                    "severity": "high",
                    "element": "input",
                }
            )
            for i, crit in enumerate(
                [
                    "1194.22(a) Text Equivalent",
                    "1194.22(c) Color Not Used Alone",
                    "1194.22(d) Style Sheets Readable",
                    "1194.22(n) Electronic Forms",
                ]
            )
        ]
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value=json.dumps(criteria_22)),
        ):
            result = await run_section508(HTML_WITH_ISSUES)
        assert result.success is True
        assert len(result.data["issues"]) == 4
        for issue in result.data["issues"]:
            assert issue["guideline"] == "ADA/Section 508"

    async def test_1194_21_software_criteria_accepted(self):
        """Criterios 1194.21 (software) devem ser aceitos com guideline correta."""
        issue_21 = make_issue(
            {
                "id": "s508-10",
                "guideline": "ADA/Section 508",
                "criterion": "1194.21(d) Sufficient Info to AT",
                "severity": "critical",
                "element": "custom-widget",
                "description": "Custom widget exposes no name/role/value to AT via accessibility API",
                "suggestion": "Use ARIA attributes or native elements to expose widget state",
            }
        )
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value=json.dumps([issue_21])),
        ):
            result = await run_section508(HTML_WITH_ISSUES)
        assert result.success is True
        assert result.data["issues"][0]["guideline"] == "ADA/Section 508"
