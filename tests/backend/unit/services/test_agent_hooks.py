"""Testes do sistema de hooks plugáveis do harness (agent_hooks.py).

Cobre o contrato central: N hooks por evento, registro/remoção em runtime,
isolamento de falha (um hook quebrado nunca derruba o loop do agente).
"""
import pytest

from backend.src.services import agent_hooks


@pytest.fixture(autouse=True)
def _clear_hooks():
    agent_hooks.clear_all_hooks()
    yield
    agent_hooks.clear_all_hooks()


class TestRegisterAndFire:
    def test_registered_hook_receives_fired_args(self):
        received = []
        agent_hooks.register_hook(agent_hooks.PRE_TOOL_CALL, lambda *a: received.append(a))
        agent_hooks.fire(agent_hooks.PRE_TOOL_CALL, "tool-1", "compute_contrast", {"a": 1})
        assert received == [("tool-1", "compute_contrast", {"a": 1})]

    def test_multiple_hooks_all_fire_in_order(self):
        order = []
        agent_hooks.register_hook(agent_hooks.POST_LLM_CALL, lambda *a: order.append("first"))
        agent_hooks.register_hook(agent_hooks.POST_LLM_CALL, lambda *a: order.append("second"))
        agent_hooks.fire(agent_hooks.POST_LLM_CALL, "openai", "gpt-5", "task-1", "perceiver", True, 500.0)
        assert order == ["first", "second"]

    def test_fire_with_no_hooks_registered_is_noop(self):
        agent_hooks.fire(agent_hooks.ON_ERROR, "openai", "gpt-5", "task-1", "perceiver", "boom")

    def test_unknown_event_registration_raises(self):
        with pytest.raises(ValueError):
            agent_hooks.register_hook("not_a_real_event", lambda: None)


class TestUnregister:
    def test_unregister_stops_future_fires(self):
        calls = []
        token = agent_hooks.register_hook(agent_hooks.PRE_TOOL_CALL, lambda *a: calls.append(a))
        agent_hooks.unregister_hook(agent_hooks.PRE_TOOL_CALL, token)
        agent_hooks.fire(agent_hooks.PRE_TOOL_CALL, "tool-1", "x", {})
        assert calls == []

    def test_unregister_unknown_token_is_noop(self):
        agent_hooks.unregister_hook(agent_hooks.PRE_TOOL_CALL, "does-not-exist")

    def test_registered_count_reflects_registrations(self):
        assert agent_hooks.registered_count(agent_hooks.PRE_LLM_CALL) == 0
        agent_hooks.register_hook(agent_hooks.PRE_LLM_CALL, lambda *a: None)
        agent_hooks.register_hook(agent_hooks.PRE_LLM_CALL, lambda *a: None)
        assert agent_hooks.registered_count(agent_hooks.PRE_LLM_CALL) == 2


class TestFailureIsolation:
    def test_broken_hook_does_not_raise_to_caller(self):
        def bad_hook(*a):
            raise RuntimeError("hook de terceiro quebrado")

        agent_hooks.register_hook(agent_hooks.PRE_TOOL_CALL, bad_hook)
        agent_hooks.fire(agent_hooks.PRE_TOOL_CALL, "tool-1", "x", {})  # não deve levantar

    def test_broken_hook_does_not_block_subsequent_hooks(self):
        calls = []

        def bad_hook(*a):
            raise RuntimeError("boom")

        agent_hooks.register_hook(agent_hooks.PRE_TOOL_CALL, bad_hook)
        agent_hooks.register_hook(agent_hooks.PRE_TOOL_CALL, lambda *a: calls.append("ran"))
        agent_hooks.fire(agent_hooks.PRE_TOOL_CALL, "tool-1", "x", {})
        assert calls == ["ran"]


class TestClearAllHooks:
    def test_clears_every_event(self):
        agent_hooks.register_hook(agent_hooks.PRE_TOOL_CALL, lambda *a: None)
        agent_hooks.register_hook(agent_hooks.POST_LLM_CALL, lambda *a: None)
        agent_hooks.clear_all_hooks()
        assert agent_hooks.registered_count(agent_hooks.PRE_TOOL_CALL) == 0
        assert agent_hooks.registered_count(agent_hooks.POST_LLM_CALL) == 0
