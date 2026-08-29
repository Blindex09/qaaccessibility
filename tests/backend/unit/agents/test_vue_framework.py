import json
from unittest.mock import AsyncMock, patch

import pytest

from backend.src.agents.vue_framework.vue_framework import run_vue_framework

from .conftest_agents import HTML_CLEAN, assert_agent_contract, assert_issues_valid, make_issue

HTML_WITH_VUE_ISSUES = """
<html>
  <body>
    <div v-if="show" @click="toggle()">Clique aqui</div>
    <router-link to="/page">aqui</router-link>
  </body>
</html>
""".strip()

VUE_ISSUE = make_issue(
    {
        "id": "vue-1",
        "guideline": "WCAG 2.2",
        "criterion": "2.1.1 Keyboard",
        "severity": "critical",
        "element": "div[v-if][@click]",
        "description": "div with @click is not keyboard accessible",
        "suggestion": "Replace with <button> or add role='button' and keyboard handler",
    }
)


@pytest.mark.asyncio
class TestVueFrameworkAgent:
    async def test_contract_on_success(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value=json.dumps([VUE_ISSUE])),
        ):
            result = await run_vue_framework(HTML_WITH_VUE_ISSUES)
        assert_agent_contract(result, "vue_framework")
        assert_issues_valid(result.data["issues"])

    async def test_no_vue_indicators_skips_llm_call(self):
        """Pre-filter: sem indicador Vue no HTML, o agente nem chama o LLM."""
        mock_llm = AsyncMock(return_value="[]")
        with patch("backend.src.services.llm_client.call_llm", new=mock_llm):
            result = await run_vue_framework(HTML_CLEAN)
        assert result.success is True
        assert result.data["issues"] == []
        mock_llm.assert_not_called()

    async def test_failure_on_invalid_json(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value="not json"),
        ):
            result = await run_vue_framework(HTML_WITH_VUE_ISSUES)
        assert result.success is False
        assert result.error is not None

    async def test_failure_on_llm_exception(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(side_effect=Exception("timeout")),
        ):
            result = await run_vue_framework(HTML_WITH_VUE_ISSUES)
        assert result.success is False
        assert "timeout" in result.error
