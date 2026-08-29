import json
from unittest.mock import AsyncMock, patch

import pytest

from backend.src.agents.aria_specialist.aria_specialist import run_aria_specialist

from .conftest_agents import (
    HTML_WITH_ISSUES,
    assert_agent_contract,
    assert_issues_valid,
    make_issue,
)

ARIA_ISSUE = make_issue(
    {
        "id": "aria-1",
        "guideline": "WAI-ARIA",
        "criterion": "ARIA Rule 1",
        "severity": "high",
        "element": "div[onclick]",
        "description": "Native button element should be used instead of div with ARIA role",
        "suggestion": "Replace div with button; native semantics are preferred",
    }
)


@pytest.mark.asyncio
class TestARIASpecialistAgent:
    async def test_contract_on_success(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value=json.dumps([ARIA_ISSUE])),
        ):
            result = await run_aria_specialist(HTML_WITH_ISSUES)
        assert_agent_contract(result, "aria_specialist")
        assert_issues_valid(result.data["issues"])

    async def test_guideline_is_wai_aria(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value=json.dumps([ARIA_ISSUE])),
        ):
            result = await run_aria_specialist(HTML_WITH_ISSUES)
        for issue in result.data.get("issues", []):
            assert issue["guideline"] == "WAI-ARIA", f"ARIA specialist retornou guideline errada: {issue['guideline']}"

    async def test_empty_html_no_crash(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value="[]"),
        ):
            result = await run_aria_specialist("")
        assert result.success is True
        assert result.data["issues"] == []

    async def test_failure_on_llm_exception(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(side_effect=Exception("timeout")),
        ):
            result = await run_aria_specialist(HTML_WITH_ISSUES)
        assert result.success is False

    async def test_required_aria_properties_criterion_accepted(self):
        """Slider sem aria-valuenow/min/max deve gerar issue WAI-ARIA valida."""
        slider_issue = make_issue(
            {
                "id": "aria-2",
                "guideline": "WAI-ARIA",
                "criterion": "4.1.2 Name, Role, Value",
                "severity": "critical",
                "element": "div[role=slider]",
                "description": "role=slider missing required aria-valuenow, aria-valuemin, aria-valuemax",
                "suggestion": "Add aria-valuenow, aria-valuemin and aria-valuemax attributes",
            }
        )
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value=json.dumps([slider_issue])),
        ):
            result = await run_aria_specialist(HTML_WITH_ISSUES)
        assert result.success is True
        issues = result.data["issues"]
        assert any("slider" in i["element"].lower() for i in issues)

    async def test_aria_rule1_native_semantics(self):
        """ARIA Rule 1: evitar role em elementos nativos (button, a, input)."""
        rule1_issue = make_issue(
            {
                "id": "aria-3",
                "guideline": "WAI-ARIA",
                "criterion": "ARIA Rule 1",
                "severity": "high",
                "element": "input[role=textbox]",
                "description": "Redundant role=textbox on native input element",
                "suggestion": "Remove role=textbox; input already has implicit textbox role",
            }
        )
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value=json.dumps([rule1_issue])),
        ):
            result = await run_aria_specialist(HTML_WITH_ISSUES)
        assert result.success is True
        assert result.data["issues"][0]["guideline"] == "WAI-ARIA"
