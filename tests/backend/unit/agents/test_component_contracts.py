import json
from unittest.mock import AsyncMock, patch

import pytest

from backend.src.agents.component_contracts.component_contracts import (
    SYSTEM_PROMPT,
    run_component_contracts,
)

from .conftest_agents import HTML_CLEAN, assert_agent_contract, assert_issues_valid, make_issue

COMPONENT_HTML = """
<main>
  <button aria-expanded="false" aria-controls="details">Mais detalhes</button>
  <div id="details" hidden>Detalhes</div>
  <div role="status" aria-live="polite"></div>
</main>
""".strip()

ISSUE = make_issue(
    {
        "id": "component-1",
        "criterion": "4.1.2 Name, Role, Value",
        "element": "button[aria-expanded]",
        "description": "The disclosure state is not kept synchronized with the revealed panel.",
        "suggestion": "Update aria-expanded and panel visibility in the same runtime state transition.",
    }
)


@pytest.mark.asyncio
class TestComponentContractsAgent:
    async def test_contract_on_success(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value=json.dumps([ISSUE])),
        ):
            result = await run_component_contracts(COMPONENT_HTML)
        assert_agent_contract(result, "component_contracts")
        assert_issues_valid(result.data["issues"])

    async def test_empty_result_is_success(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value="[]"),
        ):
            result = await run_component_contracts(HTML_CLEAN)
        assert result.success is True
        assert result.data["issues"] == []

    async def test_failure_is_explicit(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(side_effect=TimeoutError("component timeout")),
        ):
            result = await run_component_contracts(COMPONENT_HTML)
        assert result.success is False
        assert "component timeout" in result.error

    async def test_prompt_requires_evidence_and_runtime_distinction(self):
        assert "not proof" in SYSTEM_PROMPT
        assert "markup-only" in SYSTEM_PROMPT
        assert "runtime-needed" in SYSTEM_PROMPT
