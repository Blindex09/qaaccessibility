import json
from unittest.mock import AsyncMock, patch

import pytest

from backend.src.agents.css_analyzer.css_analyzer import run_css_analyzer

from .conftest_agents import (
    HTML_CLEAN,
    assert_agent_contract,
    assert_issues_valid,
    make_issue,
)

HTML_WITH_CSS_ISSUES = """
<html>
  <head>
    <style>
      button:focus { outline: none; }
      .text { color: #aaa; background: #fff; }
      .animate { transition: all 0.3s; }
    </style>
  </head>
  <body>
    <button style="outline:0">OK</button>
    <p style="color:#ccc; background-color:#fff">Texto</p>
  </body>
</html>
""".strip()

CSS_ISSUE = make_issue(
    {
        "id": "css-1",
        "guideline": "WCAG 2.2",
        "criterion": "2.4.7 Focus Visible",
        "severity": "critical",
        "element": "button:focus",
        "description": "outline:none removes focus indicator",
        "suggestion": "Add :focus-visible with visible ring style",
    }
)


@pytest.mark.asyncio
class TestCSSAnalyzerAgent:
    async def test_contract_on_success(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value=json.dumps([CSS_ISSUE])),
        ):
            result = await run_css_analyzer(HTML_WITH_CSS_ISSUES)
        assert_agent_contract(result, "css_analyzer")
        assert_issues_valid(result.data["issues"])

    async def test_css_issue_has_css_id_prefix(self):
        """Issues do css_analyzer devem ter id prefixado com css-."""
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value=json.dumps([CSS_ISSUE])),
        ):
            result = await run_css_analyzer(HTML_WITH_CSS_ISSUES)
        for issue in result.data.get("issues", []):
            assert issue["id"].startswith("css-"), f"ID deve começar com css-: {issue['id']}"

    async def test_empty_html_returns_success(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value="[]"),
        ):
            result = await run_css_analyzer("")
        assert result.success is True
        assert result.data["issues"] == []

    async def test_clean_html_no_issues(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value="[]"),
        ):
            result = await run_css_analyzer(HTML_CLEAN)
        assert result.success is True
        assert len(result.data["issues"]) == 0

    async def test_failure_on_invalid_json(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value="not json"),
        ):
            result = await run_css_analyzer(HTML_WITH_CSS_ISSUES)
        assert result.success is False
        assert result.error is not None

    async def test_failure_on_llm_exception(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(side_effect=Exception("timeout")),
        ):
            result = await run_css_analyzer(HTML_WITH_CSS_ISSUES)
        assert result.success is False
        assert "timeout" in result.error
