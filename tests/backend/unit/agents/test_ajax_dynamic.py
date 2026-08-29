import json
from unittest.mock import AsyncMock, patch

import pytest

from backend.src.agents.ajax_dynamic.ajax_dynamic import run_ajax_dynamic

from .conftest_agents import (
    HTML_CLEAN,
    assert_agent_contract,
    assert_issues_valid,
    make_issue,
)

HTML_WITH_DYNAMIC_ISSUES = """
<html>
  <body>
    <div id="results"></div>
    <div class="modal" role="dialog">
      <button onclick="closeModal()">Fechar</button>
    </div>
    <script>
      fetch('/api/data').then(r => r.json()).then(data => {
        document.getElementById('results').innerHTML = data.html;
      });
      function closeModal() {
        document.querySelector('.modal').style.display = 'none';
      }
    </script>
  </body>
</html>
""".strip()

DYNAMIC_ISSUE = make_issue(
    {
        "id": "dynamic-1",
        "guideline": "WCAG 2.2",
        "criterion": "4.1.3 Status Messages",
        "severity": "high",
        "element": "#results",
        "description": "Container updated via fetch without aria-live region",
        "suggestion": "Add aria-live='polite' to #results container",
    }
)


@pytest.mark.asyncio
class TestAJAXDynamicAgent:
    async def test_contract_on_success(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value=json.dumps([DYNAMIC_ISSUE])),
        ):
            result = await run_ajax_dynamic(HTML_WITH_DYNAMIC_ISSUES)
        assert_agent_contract(result, "ajax_dynamic")
        assert_issues_valid(result.data["issues"])

    async def test_dynamic_issue_has_dynamic_id_prefix(self):
        """Issues do ajax_dynamic devem ter id prefixado com dynamic-."""
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value=json.dumps([DYNAMIC_ISSUE])),
        ):
            result = await run_ajax_dynamic(HTML_WITH_DYNAMIC_ISSUES)
        for issue in result.data.get("issues", []):
            assert issue["id"].startswith("dynamic-"), f"ID deve começar com dynamic-: {issue['id']}"

    async def test_empty_html_returns_success(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value="[]"),
        ):
            result = await run_ajax_dynamic("")
        assert result.success is True
        assert result.data["issues"] == []

    async def test_clean_html_no_issues(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value="[]"),
        ):
            result = await run_ajax_dynamic(HTML_CLEAN)
        assert result.success is True
        assert len(result.data["issues"]) == 0

    async def test_failure_on_invalid_json(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value="not json"),
        ):
            result = await run_ajax_dynamic(HTML_WITH_DYNAMIC_ISSUES)
        assert result.success is False
        assert result.error is not None

    async def test_failure_on_llm_exception(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(side_effect=Exception("connection error")),
        ):
            result = await run_ajax_dynamic(HTML_WITH_DYNAMIC_ISSUES)
        assert result.success is False
        assert "connection error" in result.error
