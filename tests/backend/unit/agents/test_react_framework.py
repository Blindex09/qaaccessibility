import json
from unittest.mock import AsyncMock, patch

import pytest

from backend.src.agents.react_framework.react_framework import run_react_framework

from .conftest_agents import (
    HTML_CLEAN,
    assert_agent_contract,
    assert_issues_valid,
    make_issue,
)

HTML_WITH_REACT_ISSUES = """
<html>
  <body data-reactroot>
    <div onclick="handleClick()" class="btn">Clique aqui</div>
    <a href="/page" target="_blank">Leia mais</a>
    <button class="close outline-none">X</button>
    <span class="text-gray-300 bg-white">Texto claro</span>
    <a href="#">aqui</a>
  </body>
</html>
""".strip()

REACT_ISSUE = make_issue(
    {
        "id": "react-1",
        "guideline": "WCAG 2.2",
        "criterion": "2.1.1 Keyboard",
        "severity": "critical",
        "element": "div[onclick]",
        "description": "div with onClick is not keyboard accessible — no role, tabIndex or onKeyDown",
        "suggestion": "Replace with <button> or add role='button', tabIndex='0', onKeyDown handler",
    }
)


@pytest.mark.asyncio
class TestReactFrameworkAgent:
    async def test_contract_on_success(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value=json.dumps([REACT_ISSUE])),
        ):
            result = await run_react_framework(HTML_WITH_REACT_ISSUES)
        assert_agent_contract(result, "react_framework")
        assert_issues_valid(result.data["issues"])

    async def test_react_issue_has_react_id_prefix(self):
        """Issues do react_framework devem ter id prefixado com react-."""
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value=json.dumps([REACT_ISSUE])),
        ):
            result = await run_react_framework(HTML_WITH_REACT_ISSUES)
        for issue in result.data.get("issues", []):
            assert issue["id"].startswith("react-"), f"ID deve começar com react-: {issue['id']}"

    async def test_empty_html_returns_success(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value="[]"),
        ):
            result = await run_react_framework("")
        assert result.success is True
        assert result.data["issues"] == []

    async def test_clean_html_no_issues(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value="[]"),
        ):
            result = await run_react_framework(HTML_CLEAN)
        assert result.success is True
        assert len(result.data["issues"]) == 0

    async def test_failure_on_invalid_json(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value="not json"),
        ):
            result = await run_react_framework(HTML_WITH_REACT_ISSUES)
        assert result.success is False
        assert result.error is not None

    async def test_failure_on_llm_exception(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(side_effect=Exception("timeout")),
        ):
            result = await run_react_framework(HTML_WITH_REACT_ISSUES)
        assert result.success is False
        assert "timeout" in result.error
