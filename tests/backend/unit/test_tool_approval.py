import json
from types import SimpleNamespace

from run_agent import run_local_tool
from tools.registry import Registry


def test_registry_defaults_to_no_approval():
    local = Registry()
    local.register("read_only", "test", {"parameters": {}}, lambda args: args)
    assert local.tools["read_only"]["requires_approval"] is False


def test_side_effect_tool_is_blocked_without_approval(monkeypatch):
    from tools.registry import registry

    called = False

    def handler(_args):
        nonlocal called
        called = True
        return "executed"

    monkeypatch.setitem(
        registry.tools,
        "dangerous_test_tool",
        {
            "schema": {"parameters": {}},
            "handler": handler,
            "is_async": False,
            "emoji": "",
            "requires_approval": True,
        },
    )
    result = json.loads(run_local_tool("dangerous_test_tool", {}))
    assert "aprovação explícita" in result["error"]
    assert called is False


def test_side_effect_tool_still_requires_approval_when_setting_is_off(monkeypatch):
    from tools.registry import registry

    calls: list[dict] = []
    monkeypatch.setattr("backend.src.config.settings.get_settings", lambda: SimpleNamespace(approval_enabled=False))
    monkeypatch.setitem(
        registry.tools,
        "approval_off_test_tool",
        {
            "schema": {"parameters": {}},
            "handler": lambda args: calls.append(args) or "executed",
            "is_async": False,
            "emoji": "",
            "requires_approval": True,
        },
    )
    result = json.loads(run_local_tool("approval_off_test_tool", {"target": "artifact"}))
    assert "aprovação explícita" in result["error"]
    assert calls == []


def test_side_effect_tool_runs_only_after_explicit_approval(monkeypatch):
    from tools.registry import registry

    calls: list[dict] = []
    monkeypatch.setitem(
        registry.tools,
        "approved_test_tool",
        {
            "schema": {"parameters": {}},
            "handler": lambda args: calls.append(args) or "executed",
            "is_async": False,
            "emoji": "",
            "requires_approval": True,
        },
    )
    denied = run_local_tool(
        "approved_test_tool", {"value": 1}, lambda _question, _choices: "Cancelar"
    )
    assert "cancelada" in json.loads(denied)["error"]
    assert calls == []

    approved = run_local_tool(
        "approved_test_tool",
        {"value": 1, "optional": None},
        lambda _question, _choices: "Aprovar",
    )
    assert approved == "executed"
    assert calls == [{"value": 1}]


def test_approval_prompt_binds_exact_arguments_and_redacts_secrets(monkeypatch):
    from tools.registry import registry

    monkeypatch.setitem(
        registry.tools,
        "bound_test_tool",
        {
            "schema": {"parameters": {}},
            "handler": lambda args: "executed",
            "is_async": False,
            "emoji": "",
            "requires_approval": True,
        },
    )
    prompts: list[str] = []

    result = run_local_tool(
        "bound_test_tool",
        {"target": "issue-42", "api_key": "never-show-this"},
        lambda question, _choices: prompts.append(question) or "Aprovar",
    )

    assert result == "executed"
    assert '"target": "issue-42"' in prompts[0]
    assert "never-show-this" not in prompts[0]
    assert "[redigido]" in prompts[0]
    assert "Identificador da ação:" in prompts[0]


def test_approved_arguments_cannot_change_while_waiting_for_confirmation(monkeypatch):
    from tools.registry import registry

    executed: list[dict] = []
    monkeypatch.setitem(
        registry.tools,
        "bound_mutation_test_tool",
        {"handler": lambda args: executed.append(args) or "executed", "requires_approval": True},
    )
    original = {"target": {"path": "original.txt"}}

    def approve_after_mutation(question, _choices):
        assert "original.txt" in question
        original["target"]["path"] = "different.txt"
        return "Aprovar"

    assert run_local_tool("bound_mutation_test_tool", original, approve_after_mutation) == "executed"
    assert executed == [{"target": {"path": "original.txt"}}]


def test_approval_prompt_redacts_nested_secrets(monkeypatch):
    from tools.registry import registry

    monkeypatch.setitem(
        registry.tools,
        "nested_secret_test_tool",
        {"handler": lambda _args: "executed", "requires_approval": True},
    )
    prompts: list[str] = []
    result = run_local_tool(
        "nested_secret_test_tool",
        {"target": "issue-42", "metadata": {"credentials": [{"api_key": "nested-private-key"}]}},
        lambda question, _choices: prompts.append(question) or "Cancelar",
    )

    assert "cancelada" in json.loads(result)["error"]
    assert '"target": "issue-42"' in prompts[0]
    assert "nested-private-key" not in prompts[0]
