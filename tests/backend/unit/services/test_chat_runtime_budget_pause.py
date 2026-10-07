"""A supervisão SSE não pode expirar por um timeout anterior à pausa humana."""

import asyncio
import time
from contextlib import contextmanager

import pytest

from backend.src.services import chat_runtime, execution_scope


@pytest.mark.asyncio
async def test_stream_rechecks_deadline_after_user_gate_pause(monkeypatch):
    real_scope = execution_scope.execution_scope

    @contextmanager
    def short_scope(_seconds):
        with real_scope(10) as budget:
            budget.deadline = time.monotonic() + 0.12
            yield budget

    async def fake_impl(*_args):
        yield {"type": "phase", "text": "Aguardando aprovação."}
        with execution_scope.pause_for_user_gate():
            await asyncio.sleep(0.25)
        yield {"type": "done", "final": "Aprovação recebida; entrega concluída."}

    monkeypatch.setattr(execution_scope, "execution_scope", short_scope)
    monkeypatch.setattr(chat_runtime, "_stream_chat_impl", fake_impl)
    events = [event async for event in chat_runtime.stream_chat("Teste", conversation_id="gate-regression")]
    assert events[-1] == {"type": "done", "final": "Aprovação recebida; entrega concluída."}
    assert not any(event["type"] in {"error", "cancelled", "token"} for event in events)
