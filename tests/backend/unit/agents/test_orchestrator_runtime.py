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
        await asyncio.sleep(5)  # sem nenhum progresso: a janela de silêncio esgota
        return AgentResult(agent="specialist", success=True, data={"issues": []})

    import time

    from backend.src.services.execution_scope import execution_scope

    with execution_scope(10) as budget:
        budget.patience = 0.1
        budget.deadline = time.monotonic() + 0.1
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


@pytest.mark.asyncio
async def test_findings_are_delivered_before_whole_analysis_finishes(monkeypatch):
    events = []
    monkeypatch.setattr(orchestrator.chat_progress, "emit", events.append)

    async def agent():
        return AgentResult(agent="specialist", success=True, data={"issues": [{
            "id": "probe-1", "guideline": "WCAG 2.2", "criterion": "4.1.2", "severity": "high",
            "element": "button", "description": "O botão está sem nome acessível.",
            "suggestion": "Fornecer um nome acessível.",
        }]})

    result, _ = await orchestrator._timed("specialist", agent)
    assert result.success
    progress = [event for event in events if event["type"] == "phase"]
    assert "botão está sem nome" in progress[0]["text"]
    assert "preliminar" in progress[0]["text"]
