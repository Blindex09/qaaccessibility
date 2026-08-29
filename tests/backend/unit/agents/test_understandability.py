import json
from unittest.mock import AsyncMock, patch

import pytest

from backend.src.agents.understandability.understandability import run_understandability

from .conftest_agents import (
    HTML_WITH_ISSUES,
    assert_agent_contract,
    assert_issues_valid,
    make_issue,
)

UNDERSTAND_ISSUE = make_issue(
    {
        "id": "understandability-1",
        "criterion": "3.1.1 Language of Page",
        "severity": "high",
        "element": "html",
        "description": "HTML element missing lang attribute",
        "suggestion": "Add lang='pt-BR' to html element",
    }
)


@pytest.mark.asyncio
class TestUnderstandabilityAgent:
    async def test_contract_on_success(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value=json.dumps([UNDERSTAND_ISSUE])),
        ):
            result = await run_understandability(HTML_WITH_ISSUES)
        assert_agent_contract(result, "understandability")
        assert_issues_valid(result.data["issues"])

    async def test_only_wcag3x_criterion(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value=json.dumps([UNDERSTAND_ISSUE])),
        ):
            result = await run_understandability(HTML_WITH_ISSUES)
        for issue in result.data.get("issues", []):
            assert issue["criterion"].startswith(
                "3."
            ), f"Understandability retornou criterio não-3.x: {issue['criterion']}"

    async def test_failure_on_invalid_json(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value="bad response"),
        ):
            result = await run_understandability(HTML_WITH_ISSUES)
        assert result.success is False
