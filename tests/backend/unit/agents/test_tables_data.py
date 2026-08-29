import json
from unittest.mock import AsyncMock, patch

import pytest

from backend.src.agents.tables_data.tables_data import run_tables_data

from .conftest_agents import HTML_CLEAN, assert_agent_contract, assert_issues_valid, make_issue

HTML_WITH_TABLE_ISSUES = """
<html>
  <body>
    <table>
      <tr><td>Jan</td><td>120</td></tr>
      <tr><td>Fev</td><td>98</td></tr>
    </table>
  </body>
</html>
""".strip()

TABLE_ISSUE = make_issue(
    {
        "id": "tables-1",
        "guideline": "WCAG 2.2",
        "criterion": "1.3.1 Info and Relationships",
        "severity": "high",
        "element": "table",
        "description": "table has no headers",
        "suggestion": "Add <th> and <caption>",
    }
)


@pytest.mark.asyncio
class TestTablesDataAgent:
    async def test_contract_on_success(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value=json.dumps([TABLE_ISSUE])),
        ):
            result = await run_tables_data(HTML_WITH_TABLE_ISSUES)
        assert_agent_contract(result, "tables_data")
        assert_issues_valid(result.data["issues"])

    async def test_table_issue_has_tables_id_prefix(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value=json.dumps([TABLE_ISSUE])),
        ):
            result = await run_tables_data(HTML_WITH_TABLE_ISSUES)
        for issue in result.data.get("issues", []):
            assert issue["id"].startswith("tables-"), f"ID deve começar com tables-: {issue['id']}"

    async def test_empty_html_returns_success(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value="[]"),
        ):
            result = await run_tables_data("")
        assert result.success is True
        assert result.data["issues"] == []

    async def test_clean_html_no_issues(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value="[]"),
        ):
            result = await run_tables_data(HTML_CLEAN)
        assert result.success is True
        assert len(result.data["issues"]) == 0

    async def test_failure_on_invalid_json(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value="not json"),
        ):
            result = await run_tables_data(HTML_WITH_TABLE_ISSUES)
        assert result.success is False
        assert result.error is not None

    async def test_failure_on_llm_exception(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(side_effect=Exception("LLM timeout")),
        ):
            result = await run_tables_data(HTML_WITH_TABLE_ISSUES)
        assert result.success is False
        assert "LLM timeout" in result.error
