import json
from unittest.mock import AsyncMock, patch

import pytest

from backend.src.agents.robustness.robustness import run_robustness

from .conftest_agents import (
    HTML_WITH_ISSUES,
    assert_agent_contract,
    assert_issues_valid,
    make_issue,
)

ROBUST_ISSUE = make_issue(
    {
        "id": "robustness-1",
        "criterion": "4.1.2 Name, Role, Value",
        "severity": "critical",
        "element": "div[onclick]",
        "description": "Interactive element missing role and accessible name",
        "suggestion": "Add role='button' and aria-label or use native button element",
    }
)


@pytest.mark.asyncio
class TestRobustnessAgent:
    async def test_contract_on_success(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value=json.dumps([ROBUST_ISSUE])),
        ):
            result = await run_robustness(HTML_WITH_ISSUES)
        assert_agent_contract(result, "robustness")
        assert_issues_valid(result.data["issues"])

    async def test_only_wcag4x_criterion(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value=json.dumps([ROBUST_ISSUE])),
        ):
            result = await run_robustness(HTML_WITH_ISSUES)
        for issue in result.data.get("issues", []):
            assert issue["criterion"].startswith("4."), f"Robustness retornou criterio não-4.x: {issue['criterion']}"

    async def test_failure_on_llm_exception(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(side_effect=Exception("err")),
        ):
            result = await run_robustness(HTML_WITH_ISSUES)
        assert result.success is False

    async def test_prompt_excludes_4_1_1_parsing(self):
        """Prompt do robustness deve instruir explicitamente a NÃO reportar 4.1.1 Parsing."""
        from backend.src.agents.robustness.robustness import SYSTEM_PROMPT

        assert (
            "4.1.1" in SYSTEM_PROMPT and "REMOVED" in SYSTEM_PROMPT.upper()
        ), "SYSTEM_PROMPT deve mencionar que 4.1.1 Parsing foi removido no WCAG 2.2"

    async def test_status_messages_criterion_accepted(self):
        """4.1.3 Status Messages deve ser aceito como criterio valido."""
        issue_413 = make_issue(
            {
                "id": "robustness-2",
                "criterion": "4.1.3 Status Messages",
                "severity": "medium",
                "level": "AA",
                "element": "div.spinner",
                "description": "Loading spinner has no role=status or aria-live",
                "suggestion": "Add role='status' and aria-label to the loading spinner",
            }
        )
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value=json.dumps([issue_413])),
        ):
            result = await run_robustness(HTML_WITH_ISSUES)
        assert result.success is True
        issues = result.data["issues"]
        assert any(i["criterion"] == "4.1.3 Status Messages" for i in issues)
