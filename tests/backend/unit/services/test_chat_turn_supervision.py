import asyncio

import pytest

from backend.src.services import chat_progress, chat_runtime
from backend.src.services.execution_scope import current_budget


@pytest.mark.asyncio
async def test_cancel_is_effective_before_routing_or_planning_finishes(monkeypatch):
    entered = asyncio.Event()
    cleaned = asyncio.Event()

    async def blocked(*args):
        entered.set()
        try:
            await asyncio.Event().wait()
            yield {"type": "done", "final": "should not happen"}
        finally:
            cleaned.set()

    monkeypatch.setattr(chat_runtime, "_stream_chat_impl", blocked)
    monkeypatch.setattr(chat_runtime.chat_history_store, "append_message", lambda *a, **kw: None)
    stream = chat_runtime.stream_chat("audit a site")
    first = await anext(stream)
    next_event = asyncio.create_task(anext(stream))
    await entered.wait()
    assert chat_progress.request_cancel(first["id"])
    assert (await next_event)["type"] == "token"
    assert (await anext(stream))["type"] == "cancelled"
    await stream.aclose()
    assert cleaned.is_set()
    assert chat_progress.cancel_event(first["id"]) is None


@pytest.mark.asyncio
async def test_progress_from_early_stage_is_delivered_without_waiting_for_final(monkeypatch):
    release = asyncio.Event()

    async def staged(*args):
        assert current_budget() is not None
        chat_progress.emit({"type": "phase", "text": "Vou conferir os controles desta página."})
        await release.wait()
        yield {"type": "done", "final": "concluído"}

    monkeypatch.setattr(chat_runtime, "_stream_chat_impl", staged)
    stream = chat_runtime.stream_chat("audit")
    assert (await anext(stream))["type"] == "stream_id"
    assert (await anext(stream))["text"] == "Vou conferir os controles desta página."
    release.set()
    assert (await anext(stream))["type"] == "done"
    await stream.aclose()


@pytest.mark.asyncio
async def test_timeout_preserves_partial_instead_of_claiming_completion(monkeypatch):
    stored = []

    async def partial(*args):
        yield {"type": "token", "text": "Encontrei um controle sem nome. "}
        current_budget().deadline = 0
        await asyncio.Event().wait()

    monkeypatch.setattr(chat_runtime, "_stream_chat_impl", partial)
    monkeypatch.setattr(chat_runtime.chat_history_store, "append_message", lambda *a, **kw: stored.append(a[1]))
    events = [event async for event in chat_runtime.stream_chat("audit")]
    assert events[-1]["type"] == "done"
    assert "parciais" in events[-1]["final"]
    assert "controle sem nome" in stored[0]


@pytest.mark.asyncio
async def test_disconnect_preserves_visible_progress(monkeypatch):
    stored = []

    async def partial(*args):
        yield {"type": "token", "text": "Já examinei o nome do controle."}
        await asyncio.Event().wait()

    monkeypatch.setattr(chat_runtime, "_stream_chat_impl", partial)
    monkeypatch.setattr(chat_runtime.chat_history_store, "append_message", lambda *a, **kw: stored.append(a[1]))
    stream = chat_runtime.stream_chat("audit")
    assert (await anext(stream))["type"] == "stream_id"
    assert (await anext(stream))["type"] == "token"
    await stream.aclose()
    assert "nome do controle" in stored[0]
    assert "parciais" in stored[0]
