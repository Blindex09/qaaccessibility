import json
from unittest.mock import AsyncMock, patch

import pytest

from backend.src.agents.link_checker.link_checker import run_link_checker

from .conftest_agents import HTML_CLEAN, assert_agent_contract, assert_issues_valid, make_issue

HTML_WITH_LINK_ISSUES = """
<html>
  <body>
    <a href="/product/1">Read more</a>
    <a href="/product/2">Read more</a>
    <a href="/report.pdf" target="_blank">Download</a>
  </body>
</html>
""".strip()

LINK_ISSUE = make_issue(
    {
        "id": "links-1",
        "guideline": "WCAG 2.2",
        "criterion": "2.4.4 Link Purpose (In Context)",
        "severity": "high",
        "element": "a[href='/product/1']",
        "description": "duplicate 'Read more' link text with different destinations",
        "suggestion": "Add unique aria-label per link",
    }
)


@pytest.mark.asyncio
class TestLinkCheckerAgent:
    async def test_contract_on_success(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value=json.dumps([LINK_ISSUE])),
        ):
            result = await run_link_checker(HTML_WITH_LINK_ISSUES)
        assert_agent_contract(result, "link_checker")
        assert_issues_valid(result.data["issues"])

    async def test_link_issue_has_links_id_prefix(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value=json.dumps([LINK_ISSUE])),
        ):
            result = await run_link_checker(HTML_WITH_LINK_ISSUES)
        for issue in result.data.get("issues", []):
            assert issue["id"].startswith("links-"), f"ID deve começar com links-: {issue['id']}"

    async def test_empty_html_returns_success(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value="[]"),
        ):
            result = await run_link_checker("")
        assert result.success is True
        assert result.data["issues"] == []

    async def test_clean_html_no_issues(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value="[]"),
        ):
            result = await run_link_checker(HTML_CLEAN)
        assert result.success is True
        assert len(result.data["issues"]) == 0

    async def test_failure_on_invalid_json(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value="not json"),
        ):
            result = await run_link_checker(HTML_WITH_LINK_ISSUES)
        assert result.success is False
        assert result.error is not None

    async def test_failure_on_llm_exception(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(side_effect=Exception("LLM timeout")),
        ):
            result = await run_link_checker(HTML_WITH_LINK_ISSUES)
        assert result.success is False
        assert "LLM timeout" in result.error
