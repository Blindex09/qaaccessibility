import json
from unittest.mock import AsyncMock, patch

import pytest

from backend.src.agents.svelte_framework.svelte_framework import run_svelte_framework

from .conftest_agents import (
    HTML_CLEAN,
    assert_agent_contract,
    assert_issues_valid,
    make_issue,
)

HTML_WITH_SVELTE_ISSUES = """
<html>
  <body class="svelte-a1b2c3" data-svelte-h="1">
    <div onclick="handleClick()" class="tab">Perfil</div>
    <!-- {#if showStatus} -->
    <span role="status">Salvo</span>
  </body>
</html>
""".strip()

SVELTE_ISSUE = make_issue(
    {
        "id": "svelte-1",
        "guideline": "WCAG 2.2",
        "criterion": "2.1.1 Keyboard",
        "severity": "critical",
        "element": "div[onclick].tab",
        "description": "div with onclick is not keyboard accessible in Svelte 5 runes mode",
        "suggestion": "Use <button> or add role='button', tabindex='0' and onkeydown handler",
    }
)


@pytest.mark.asyncio
class TestSvelteFrameworkAgent:
    async def test_contract_on_success(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value=json.dumps([SVELTE_ISSUE])),
        ):
            result = await run_svelte_framework(HTML_WITH_SVELTE_ISSUES)
        assert_agent_contract(result, "svelte_framework")
        assert_issues_valid(result.data["issues"])

    async def test_svelte_issue_has_svelte_id_prefix(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value=json.dumps([SVELTE_ISSUE])),
        ):
            result = await run_svelte_framework(HTML_WITH_SVELTE_ISSUES)
        for issue in result.data.get("issues", []):
            assert issue["id"].startswith("svelte-"), f"ID deve começar com svelte-: {issue['id']}"

    async def test_pre_filter_skips_llm_without_svelte_indicators(self):
        """Sem indicadores Svelte no HTML, o agente pula a chamada de LLM
        inteiramente (mesmo padrao de custo de vue_framework.py)."""
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(side_effect=AssertionError("call_llm nao deveria ser chamado sem indicadores Svelte")),
        ):
            result = await run_svelte_framework(HTML_CLEAN)
        assert result.success is True
        assert result.data["issues"] == []

    async def test_empty_html_returns_success(self):
        result = await run_svelte_framework("")
        assert result.success is True
        assert result.data["issues"] == []

    async def test_failure_on_invalid_json(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value="not json"),
        ):
            result = await run_svelte_framework(HTML_WITH_SVELTE_ISSUES)
        assert result.success is False
        assert result.error is not None

    async def test_failure_on_llm_exception(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(side_effect=Exception("timeout")),
        ):
            result = await run_svelte_framework(HTML_WITH_SVELTE_ISSUES)
        assert result.success is False
        assert "timeout" in result.error
