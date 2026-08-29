import json
from unittest.mock import AsyncMock, patch

import pytest

from backend.src.agents.operability.operability import run_operability

from .conftest_agents import (
    HTML_WITH_ISSUES,
    assert_agent_contract,
    assert_issues_valid,
    make_issue,
)

OPERABILITY_ISSUE = make_issue(
    {
        "id": "operability-1",
        "criterion": "2.1.1 Keyboard",
        "severity": "critical",
        "element": "div[onclick]",
        "description": "Interactive div not keyboard accessible",
        "suggestion": "Replace div with button element",
    }
)


@pytest.mark.asyncio
class TestOperabilityAgent:
    async def test_contract_on_success(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value=json.dumps([OPERABILITY_ISSUE])),
        ):
            result = await run_operability(HTML_WITH_ISSUES)
        assert_agent_contract(result, "operability")
        assert_issues_valid(result.data["issues"])

    async def test_only_wcag2x_criterion(self):
        """Operability deve retornar apenas criterios 2.x."""
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value=json.dumps([OPERABILITY_ISSUE])),
        ):
            result = await run_operability(HTML_WITH_ISSUES)
        for issue in result.data.get("issues", []):
            crit = issue["criterion"]
            assert crit.startswith("2."), f"Operability retornou criterio não-2.x: {crit}"

    async def test_empty_html_no_crash(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value="[]"),
        ):
            result = await run_operability("")
        assert result.success is True

    async def test_failure_on_llm_exception(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(side_effect=RuntimeError("err")),
        ):
            result = await run_operability(HTML_WITH_ISSUES)
        assert result.success is False
        assert result.error is not None

    async def test_multiple_ways_criterion_accepted(self):
        """2.4.5 Multiple Ways deve ser aceito como criterio valido do operability."""
        issue_245 = make_issue(
            {
                "id": "operability-2",
                "criterion": "2.4.5 Multiple Ways",
                "severity": "medium",
                "level": "AA",
                "element": "body",
                "description": "Page has no search form, breadcrumb or sitemap link",
                "suggestion": "Add at least a second way to locate this page (search or breadcrumb)",
            }
        )
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value=json.dumps([issue_245])),
        ):
            result = await run_operability(HTML_WITH_ISSUES)
        assert result.success is True
        issues = result.data["issues"]
        assert any(i["criterion"] == "2.4.5 Multiple Ways" for i in issues)

    async def test_new_wcag22_criteria_accepted(self):
        """Criterios novos do WCAG 2.2 (2.4.11, 2.5.7, 2.5.8) devem ser aceitos."""
        new_criteria = [
            make_issue(
                {
                    "id": f"operability-{n}",
                    "criterion": crit,
                    "severity": "medium",
                    "element": "button",
                }
            )
            for n, crit in enumerate(
                [
                    "2.4.11 Focus Not Obscured (Minimum)",
                    "2.5.7 Dragging Movements",
                    "2.5.8 Target Size (Minimum)",
                ]
            )
        ]
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value=json.dumps(new_criteria)),
        ):
            result = await run_operability(HTML_WITH_ISSUES)
        assert result.success is True
        for issue in result.data["issues"]:
            assert issue["criterion"].startswith("2."), f"Operability emitiu criterio fora de 2.x: {issue['criterion']}"
