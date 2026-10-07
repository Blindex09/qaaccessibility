"""Regra 8: nenhum relógio fixo encerra trabalho que continua avançando.

O orçamento do turno é uma janela de silêncio: progresso real desliza o prazo
para frente; só a falta de progresso por toda a janela encerra a execução.
"""

import asyncio
import threading
import time

import pytest

from backend.src.services import chat_progress
from backend.src.services.execution_scope import (
    execution_scope,
    note_progress,
    pause_for_user_gate,
    run_until_stalled,
)


def _tight_window(budget, seconds):
    budget.patience = seconds
    budget.deadline = time.monotonic() + seconds


@pytest.mark.asyncio
async def test_work_that_keeps_progressing_outlives_the_initial_window():
    with execution_scope(10) as budget:
        _tight_window(budget, 0.2)

        async def long_task():
            for _ in range(12):  # ~0.6s no total, muito mais que a janela de 0.2s
                await asyncio.sleep(0.05)
                note_progress()
            return "concluido"

        assert await run_until_stalled(long_task()) == "concluido"


@pytest.mark.asyncio
async def test_silent_work_is_ended_only_by_the_absence_of_progress():
    with execution_scope(10) as budget:
        _tight_window(budget, 0.15)

        async def stuck():
            await asyncio.sleep(5)

        started = time.monotonic()
        with pytest.raises(TimeoutError):
            await run_until_stalled(stuck())
        assert time.monotonic() - started < 2


def test_published_events_count_as_progress():
    with execution_scope(10) as budget:
        _tight_window(budget, 0.3)
        time.sleep(0.15)
        before = budget.deadline
        chat_progress.emit({"type": "phase", "text": "avançando"})  # sem sink: ainda é progresso
        assert budget.deadline > before


def test_user_gate_wait_is_not_machine_progress_and_does_not_slide_the_window():
    with execution_scope(10) as budget:
        _tight_window(budget, 0.3)
        with pause_for_user_gate():
            before = budget.deadline
            note_progress()
            assert budget.deadline == before


def test_progress_never_shortens_the_window():
    with execution_scope(10) as budget:
        budget.adapt("high")
        reserved = budget.deadline
        note_progress()
        assert budget.deadline >= reserved


@pytest.mark.asyncio
async def test_cancel_still_stops_work_that_is_progressing():
    token = chat_progress.set_cancel_check(lambda: True)
    try:
        with execution_scope(10):
            async def busy():
                await asyncio.sleep(5)

            with pytest.raises(InterruptedError):
                await run_until_stalled(busy())
    finally:
        chat_progress.reset_cancel_check(token)


def test_waiting_for_the_person_has_no_fixed_clock():
    """O cartão de aprovação espera a resposta ou o cancelamento, nunca um relógio."""
    import inspect

    assert "timeout" not in inspect.signature(chat_progress.wait_clarify).parameters
    rid, ev = chat_progress.new_clarify()
    threading.Timer(0.4, lambda: chat_progress.answer_clarify(rid, "sim")).start()
    with execution_scope(10):
        started = time.monotonic()
        answer = chat_progress.wait_clarify(rid, ev)
    assert answer == "sim"
    assert time.monotonic() - started >= 0.35


def test_stream_callbacks_are_progress_signals():
    from run_agent import AIAgent

    seen = []
    with execution_scope(10) as budget:
        _tight_window(budget, 0.3)
        agent = AIAgent(stream_delta_callback=seen.append)
        time.sleep(0.15)
        before = budget.deadline
        agent.stream_delta_callback("texto")
        assert seen == ["texto"]
        assert budget.deadline > before


def test_persistent_repetition_ends_the_tool_loop_instead_of_spinning():
    from run_agent import AIAgent

    with execution_scope(10):
        agent = AIAgent(enabled_toolsets=["probe"], max_iterations=1)
        notes = [agent._check_context_drift("probe", {"a": 1}, "mesmo resultado") for _ in range(8)]
        assert any(n for n in notes), "a reflexão única deve aparecer"
        assert agent._drift_stalled
        assert list(agent._iterations()) == []
        assert "repetiu a mesma chamada" in agent._loop_exit_error("havia pendências")
