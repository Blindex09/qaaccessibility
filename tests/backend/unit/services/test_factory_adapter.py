"""Factory provider regressions: wire contracts and executed MCP handlers."""
import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from backend.src.services.factory_adapter import _plain, run_factory
from run_agent import AIAgent
from tools.registry import registry


@pytest.fixture
def sdk_run():
    response = SimpleNamespace(success=True, text="ok", structured_output=None,
                               usage=SimpleNamespace(input_tokens=37, output_tokens=11))
    with patch("droid_sdk.run", new=AsyncMock(return_value=response)) as mock:
        yield mock


def test_context_schema_system_and_permission_boundary(sdk_run):
    schema = {"type": "object", "properties": {"issues": {"type": "array"}}, "required": ["issues"]}
    agent = AIAgent(provider="factory", model="auto", fallback_model={},
                    ephemeral_system_prompt="System policy", response_schema=schema,
                    prefill_messages=[{"role": "user", "content": "history-canary"}])
    response = agent.run_conversation("current question")
    args = sdk_run.call_args
    assert not response["failed"]
    assert "history-canary" in args.args[0]
    assert args.kwargs["config"].system_prompt == "System policy"
    assert _plain(args.kwargs["output"].schema) == schema
    assert args.kwargs["config"].restrict_tools == frozenset({"qa___no_tools_allowed"})
    assert args.kwargs["interactions"].on_permission is not None
    assert args.kwargs["timeout"] > 0
    assert response["usage"]["total_tokens"] == 48


def test_unknown_usage_is_not_zero(sdk_run):
    sdk_run.return_value.usage = None
    assert "usage" not in run_factory("hello", None, "auto", "dummy")


def test_permissions_deny_native_and_unknown_tools(sdk_run):
    import droid_sdk as sdk

    run_factory("hello", None, "auto", "dummy", tools=[{"function": {
        "name": "probe", "parameters": {"type": "object"}}}])
    permission = sdk_run.call_args.kwargs["interactions"].on_permission
    for action, expected in [
        (sdk.McpToolAction(tool_use=None, tool_name="qa___probe", impact_level="low"), sdk.ToolConfirmationOutcome.PROCEED_ONCE),
        (sdk.McpToolAction(tool_use=None, tool_name="other___probe", impact_level="low"), sdk.ToolConfirmationOutcome.CANCEL),
        (SimpleNamespace(tool_name="Execute"), sdk.ToolConfirmationOutcome.CANCEL),
    ]:
        request = SimpleNamespace(actions=[action], respond=lambda outcome: outcome)
        assert permission(request) == expected


def test_inline_image_is_forwarded_as_sdk_image(sdk_run):
    run_factory([{"type": "image_url", "image_url": {"url": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aZ1kAAAAASUVORK5CYII="}}], None, "auto", "dummy")
    assert len(sdk_run.call_args.kwargs["images"]) == 1


def test_sdk_structured_result_is_returned_not_commentary(sdk_run):
    sdk_run.return_value.structured_output = {"issues": []}
    assert json.loads(run_factory("hello", None, "auto", "dummy")["final_response"]) == {"issues": []}


def test_real_qa_handler_and_callbacks_are_used(sdk_run, monkeypatch):
    handler = Mock(return_value='{"evidence": "tool-ran"}')
    monkeypatch.setitem(registry.tools, "audit_probe", {"schema": {"parameters": {"type": "object"}}, "handler": handler})
    monkeypatch.setitem(registry.toolsets, "audit_probe_set", ["audit_probe"])
    start, complete = Mock(), Mock()
    response = sdk_run.return_value

    async def invoke(prompt, **kwargs):
        config = kwargs["config"]
        assert config.restrict_tools == frozenset({"qa___audit_probe"})
        result = await config.mcp_servers[0].tools[0].handler({"value": 42})
        assert json.loads(result)["evidence"] == "tool-ran"
        return response

    sdk_run.side_effect = invoke
    result = AIAgent(provider="factory", fallback_model={}, enabled_toolsets=["audit_probe_set"],
                     tool_start_callback=start, tool_complete_callback=complete).run_conversation("use tool")
    assert not result["failed"]
    handler.assert_called_once_with({"value": 42})
    start.assert_called_once()
    complete.assert_called_once()


def test_tool_limit_blocks_additional_executions(sdk_run):
    execute = Mock(side_effect=lambda calls: {calls[0][0]: "ok"})
    response = sdk_run.return_value

    async def invoke(prompt, **kwargs):
        handler = kwargs["config"].mcp_servers[0].tools[0].handler
        assert await handler({}) == "ok"
        assert "error" in json.loads(await handler({}))
        return response

    sdk_run.side_effect = invoke
    run_factory("hello", None, "auto", None, max_tool_calls=1, execute_tools=execute,
                tools=[{"function": {"name": "probe", "parameters": {"type": "object"}}}])
    execute.assert_called_once()


def test_cancelled_turn_does_not_start_or_fallback(sdk_run):
    with pytest.raises(asyncio.CancelledError):
        AIAgent(provider="factory", cancel_check=lambda: True).run_conversation("hello")
    sdk_run.assert_not_awaited()


def test_missing_runtime_fails_explicitly():
    with (patch("shutil.which", return_value=None), patch("pathlib.Path.is_file", return_value=False),
          pytest.raises(RuntimeError, match="Droid CLI")):
        run_factory("hello", None, "auto", None)


def test_inflight_cancellation_closes_sdk_task(sdk_run):
    closed = Mock()

    async def pending(*args, **kwargs):
        try:
            await asyncio.sleep(30)
        finally:
            closed()

    sdk_run.side_effect = pending
    checks = iter([False, True])
    with pytest.raises(asyncio.CancelledError):
        run_factory("hello", None, "auto", None, cancel_check=lambda: next(checks, True))
    closed.assert_called_once()


def test_fallback_preserves_cancellation(sdk_run):
    check = Mock(return_value=False)
    agent = AIAgent(provider="factory", cancel_check=check,
                    fallback_model={"provider": "factory", "model": "auto"})
    sdk_run.side_effect = RuntimeError("primary failed")
    with patch("run_agent.AIAgent") as secondary:
        secondary.return_value.run_conversation.return_value = {"failed": False, "final_response": "ok"}
        assert agent.run_conversation("hello")["failed"] is False
    assert secondary.call_args.kwargs["cancel_check"] is check


def test_error_redacts_key(sdk_run):
    sdk_run.return_value.success = False
    sdk_run.return_value.error = "bad secret-canary"
    with pytest.raises(RuntimeError) as error:
        run_factory("hello", None, "auto", "secret-canary")
    assert "secret-canary" not in str(error.value)


def test_remote_image_is_rejected_not_stringified(sdk_run):
    with pytest.raises(ValueError, match="URL remota"):
        run_factory([{"type": "image_url", "image_url": {"url": "https://example.test/image.png"}}], None, "auto", None)
    sdk_run.assert_not_awaited()
