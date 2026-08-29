"""Testes do canal de progresso/clarify/cancelamento do chat."""

import pytest

from backend.src.services import chat_progress


class TestProgressSink:
    def test_emit_without_sink_is_noop(self):
        # Fora do chat (sem sink registrado) emit não deve levantar nada.
        chat_progress.emit({"type": "agent", "agent": "x"})

    def test_sink_receives_events_then_reset(self):
        seen: list[dict] = []
        token = chat_progress.set_sink(lambda ev: seen.append(ev))
        try:
            chat_progress.emit({"type": "phase", "text": "oi"})
            chat_progress.emit({"type": "agent", "agent": "perceiver"})
        finally:
            chat_progress.reset_sink(token)
        assert seen == [
            {"type": "phase", "text": "oi"},
            {"type": "agent", "agent": "perceiver"},
        ]
        # Apos reset, volta a ser no-op.
        chat_progress.emit({"type": "phase", "text": "ignorado"})
        assert len(seen) == 2

    def test_sink_error_never_propagates(self):
        def boom(_ev):
            raise RuntimeError("falha no sink")

        token = chat_progress.set_sink(boom)
        try:
            chat_progress.emit({"type": "phase", "text": "x"})  # não deve levantar
        finally:
            chat_progress.reset_sink(token)

    def test_emit_tool_progress_forwards_event(self):
        seen: list[dict] = []
        token = chat_progress.set_sink(lambda ev: seen.append(ev))
        try:
            chat_progress.emit_tool_progress("tid_1", "analyze_page", "Obtendo conteúdo...")
        finally:
            chat_progress.reset_sink(token)
        assert seen == [
            {"type": "tool_progress", "tool_call_id": "tid_1", "name": "analyze_page", "message": "Obtendo conteúdo..."},
        ]

    def test_emit_tool_progress_without_sink_is_noop(self):
        # Fora do chat (sem sink) não deve levantar.
        chat_progress.emit_tool_progress(None, "analyze_page", "x")


class TestClarifyRegistry:
    def test_answer_then_wait_returns_value(self):
        rid, ev = chat_progress.new_clarify()
        assert chat_progress.answer_clarify(rid, "https://exemplo.com") is True
        assert chat_progress.wait_clarify(rid, ev, timeout=1.0) == "https://exemplo.com"

    def test_answer_unknown_id_returns_false(self):
        assert chat_progress.answer_clarify("naoexiste", "x") is False

    def test_wait_timeout_returns_empty(self):
        rid, ev = chat_progress.new_clarify()
        assert chat_progress.wait_clarify(rid, ev, timeout=0.05) == ""


class TestCancelRegistry:
    def test_new_token_starts_not_cancelled(self):
        token = chat_progress.new_cancel_token()
        try:
            ev = chat_progress.cancel_event(token)
            assert ev is not None
            assert ev.is_set() is False
        finally:
            chat_progress.clear_cancel_token(token)

    def test_request_cancel_sets_the_event(self):
        token = chat_progress.new_cancel_token()
        try:
            assert chat_progress.request_cancel(token) is True
            ev = chat_progress.cancel_event(token)
            assert ev is not None
            assert ev.is_set() is True
        finally:
            chat_progress.clear_cancel_token(token)

    def test_request_cancel_unknown_token_returns_false(self):
        assert chat_progress.request_cancel("naoexiste") is False

    def test_clear_cancel_token_removes_the_event(self):
        token = chat_progress.new_cancel_token()
        chat_progress.clear_cancel_token(token)
        assert chat_progress.cancel_event(token) is None
        # Cancelar depois de limpo -- turno já terminou, não existe mais.
        assert chat_progress.request_cancel(token) is False


@pytest.mark.asyncio
async def test_cancel_event_is_awaitable_asyncio_event():
    """Precisa ser asyncio.Event (não threading.Event) -- é aguardado junto com
    asyncio.Queue.get() via asyncio.wait() no mesmo loop, sem thread cruzada."""
    token = chat_progress.new_cancel_token()
    try:
        ev = chat_progress.cancel_event(token)
        assert ev is not None
        chat_progress.request_cancel(token)
        await ev.wait()  # não deve bloquear -- já está setado
    finally:
        chat_progress.clear_cancel_token(token)
