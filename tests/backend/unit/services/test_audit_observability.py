import json

from backend.src.services import agent_hooks
from backend.src.services.audit_observability import audit_scope, audited_orchestrator


def test_audit_scope_records_tool_llm_and_approval_events():
    with audit_scope() as audit:
        audit.add(
            "tool_call",
            phase="requested",
            tool_id="tool-1",
            tool="fix_and_zip_files",
            arguments={"html_content": "secret"},
            requires_approval=True,
        )
        agent_hooks.fire(
            agent_hooks.POST_TOOL_CALL,
            "tool-1",
            "fix_and_zip_files",
            {"html_content": "secret"},
            json.dumps({"error": "Ação cancelada pelo usuário."}),
        )
        agent_hooks.fire(agent_hooks.POST_LLM_CALL, "ollama-cloud", "model-x", "task-1", "perceiver", True, 12.5)

    snapshot = audit.snapshot()
    assert snapshot["counters"]["tool_calls"] == 1
    assert snapshot["counters"]["llm_calls"] == 1
    assert snapshot["counters"]["approval_requests"] == 1
    assert snapshot["counters"]["approval_cancellations"] == 1
    assert all(event.get("arguments", {}).get("html_content") != "secret" for event in snapshot["events"])


def test_audit_hooks_are_scoped_to_the_current_run():
    with audit_scope() as first:
        agent_hooks.fire(agent_hooks.POST_LLM_CALL, "ollama", "model", "task", "agent", True, 1)
    with audit_scope() as second:
        pass

    assert first.snapshot()["counters"]["llm_calls"] == 1
    assert second.snapshot()["counters"]["llm_calls"] == 0


def test_audited_orchestrator_attaches_audit_to_result_data():
    class Result:
        def __init__(self):
            self.data = {}

    @audited_orchestrator
    async def fake_orchestrator():
        agent_hooks.fire(agent_hooks.POST_LLM_CALL, "ollama", "model", "task", "agent", True, 1)
        return Result()

    import asyncio

    result = asyncio.run(fake_orchestrator())
    assert result.data["audit"]["counters"]["llm_calls"] == 1
    assert result.data["audit"]["run_id"].startswith("qa-")
