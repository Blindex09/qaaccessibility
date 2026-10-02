import asyncio
import json

import pytest

from backend.src.services import chat_progress
from backend.src.services.execution_scope import check_execution, execution_scope, remaining_seconds
from run_agent import AIAgent
from tools.registry import registry


@pytest.mark.parametrize("parallel", [False, True])
def test_ungranted_tool_never_reaches_handler(monkeypatch, parallel):
    seen = []
    monkeypatch.setitem(registry.tools, "ungranted_probe", {
        "schema": {"parameters": {"type": "object", "properties": {}}},
        "handler": lambda args: seen.append(args) or "executed",
    })
    agent = AIAgent(provider="ollama-cloud", enabled_toolsets=[])
    calls = [("one", "ungranted_probe", {})]
    if parallel:
        calls.append(("two", "ungranted_probe", {}))
    results = agent._execute_tool_calls(calls)
    assert all("concedida" in json.loads(result)["error"] for result in results.values())
    assert seen == []


def test_ungranted_toolset_cannot_be_added_after_agent_creation(monkeypatch):
    monkeypatch.setitem(registry.toolsets, "probe", ["late_probe"])
    monkeypatch.setitem(registry.tools, "late_probe", {
        "schema": {"parameters": {}}, "handler": lambda args: "executed",
    })
    agent = AIAgent(enabled_toolsets=[])
    agent.enabled_toolsets.append("probe")
    assert agent._get_api_tools() == []
    assert "concedida" in json.loads(agent._execute_tool_calls([("one", "late_probe", {})])["one"])["error"]


def test_tool_contract_is_checked_before_handler(monkeypatch):
    seen = []
    monkeypatch.setitem(registry.tools, "granted_probe", {
        "schema": {"parameters": {"type": "object", "properties": {"url": {"type": "string"}},
                                  "required": ["url"], "additionalProperties": False}},
        "handler": lambda args: seen.append(args) or "executed",
    })
    monkeypatch.setitem(registry.toolsets, "probe", ["granted_probe"])
    agent = AIAgent(enabled_toolsets=["probe"])
    invalid = agent._execute_tool_calls([("one", "granted_probe", {"url": 42})])
    assert "error" in json.loads(invalid["one"])
    assert seen == []
    assert agent._execute_tool_calls([("two", "granted_probe", {"url": "https://example.com"})])["two"] == "executed"


def test_nested_budget_does_not_renew_deadline():
    with execution_scope(10) as outer, execution_scope(1000) as inner:
        assert inner is outer
        assert remaining_seconds() <= 20


@pytest.mark.asyncio
async def test_structured_repair_uses_the_same_budget(monkeypatch):
    from backend.src.services import llm_client

    observed = []

    async def fake_leaf(**kwargs):
        from backend.src.services.execution_scope import current_budget

        observed.append(current_budget())
        return "bad" if len(observed) == 1 else '{"ok":true}'

    monkeypatch.setattr(llm_client, "call_llm", fake_leaf)
    with execution_scope(10) as budget:
        result = await llm_client.call_llm_structured("system", "task", json.loads)
    assert result == {"ok": True}
    assert observed == [budget, budget]


def test_adaptation_uses_original_start_and_model_enum():
    with execution_scope(10) as budget:
        budget.adapt("high")
        assert budget.deadline == budget.started_at + 80
        budget.adapt("low")
        assert budget.deadline == budget.started_at + 20


def test_expired_budget_stops_tool_loop_not_an_arbitrary_round_count():
    with execution_scope(10) as budget:
        agent = AIAgent(enabled_toolsets=["probe"], max_iterations=1)
        iterator = agent._iterations()
        assert next(iterator) == 0
        assert next(iterator) == 1
        budget.deadline = 0
        with pytest.raises(TimeoutError):
            next(iterator)


@pytest.mark.asyncio
async def test_cancel_and_scope_propagate_into_worker():
    token = chat_progress.set_cancel_check(lambda: True)
    try:
        with execution_scope(10), pytest.raises(InterruptedError):
            await asyncio.to_thread(check_execution)
    finally:
        chat_progress.reset_cancel_check(token)
