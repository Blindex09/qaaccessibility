"""Regressões do ciclo agentico interativo do orquestrador."""

import asyncio

import pytest

from backend.src.agents.orchestrator import orchestrator
from backend.src.shared.models import AgentResult


@pytest.mark.asyncio
async def test_timeout_does_not_repeat_specialist_call(monkeypatch):
    calls = 0

    async def slow_agent():
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.05)
        return AgentResult(agent="specialist", success=True, data={"issues": []})

    monkeypatch.setattr(orchestrator, "_get_agent_timeout", lambda: 0.001)
    result, _ = await orchestrator._timed("specialist", slow_agent)

    assert calls == 1
    assert result.success is False
    assert "Timeout" in (result.error or "")


@pytest.mark.asyncio
async def test_cancelled_turn_skips_queued_specialist(monkeypatch):
    calls = 0

    async def agent():
        nonlocal calls
        calls += 1
        return AgentResult(agent="specialist", success=True, data={"issues": []})

    monkeypatch.setattr(orchestrator.chat_progress, "is_cancelled", lambda: True)
    result, _ = await orchestrator._timed("specialist", agent)

    assert calls == 0
    assert result.success is False
    assert result.error == "Cancelado pelo usuário"
