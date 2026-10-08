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


def test_a_slow_provider_call_that_keeps_delivering_data_is_not_a_stall():
    """Regressão (teste ao vivo 2026-10-07): uma chamada longa ao provedor passa mais do que a janela.
    Enquanto dado chega, é espera legítima; a janela só recomeça quando ela termina."""
    with execution_scope(10) as budget:
        _tight_window(budget, 0.2)
        budget.begin_call()
        for _ in range(3):
            time.sleep(0.1)
            budget.note_chunk()  # dado chegando dentro da janela
        assert budget.effective_deadline() > time.monotonic()
        budget.end_call()
        assert budget.effective_deadline() > time.monotonic()  # janela nova a partir do fim da chamada


def test_a_provider_call_that_delivers_nothing_for_the_whole_window_is_a_stall():
    """Regressão (e2e real 2026-10-08): um especialista ficou 29 minutos numa chamada sem erro e sem fim, e a
    presença da chamada em andamento segurava o turno para sempre. Sem dado por toda a janela, é travamento."""
    with execution_scope(10) as budget:
        _tight_window(budget, 0.1)
        budget.begin_call()
        time.sleep(0.3)  # bem mais que a janela, sem nenhum dado
        assert budget.effective_deadline() <= time.monotonic()


def test_without_a_call_in_flight_silence_is_still_a_stall():
    with execution_scope(10) as budget:
        _tight_window(budget, 0.1)
        time.sleep(0.2)
        assert budget.effective_deadline() <= time.monotonic()


def test_agent_iteration_marks_the_provider_call_while_it_runs():
    from run_agent import AIAgent

    agent = AIAgent(enabled_toolsets=[], max_iterations=1)
    with execution_scope(10) as budget:
        iterator = agent._iterations()
        assert next(iterator) == 0
        assert budget.inflight == 1
        assert list(iterator) == []  # a única iteração terminou
        assert budget.inflight == 0


@pytest.mark.asyncio
async def test_slow_call_that_keeps_delivering_wrapped_by_run_until_stalled_is_not_cut():
    async def slow_call():
        budget = current_budget()
        budget.begin_call()
        try:
            for _ in range(5):
                await asyncio.sleep(0.1)
                budget.note_chunk()
        finally:
            budget.end_call()
        return "pronto"

    from backend.src.services.execution_scope import current_budget

    with execution_scope(10) as budget:
        _tight_window(budget, 0.25)
        assert await run_until_stalled(slow_call()) == "pronto"


@pytest.mark.asyncio
async def test_silent_call_wrapped_by_run_until_stalled_is_given_up():
    async def silent_call():
        budget = current_budget()
        budget.begin_call()
        try:
            await asyncio.sleep(5)
        finally:
            budget.end_call()

    from backend.src.services.execution_scope import current_budget

    with execution_scope(10) as budget:
        _tight_window(budget, 0.2)
        with pytest.raises(TimeoutError):
            await run_until_stalled(silent_call())


def test_dropping_stuck_specialists_gives_the_rest_of_the_pipeline_a_fresh_window():
    """Depois do autosubmit parcial, os passos seguintes (revisão, relatório) não podem
    herdar a janela esgotada, senão a análise inteira falha em vez de entregar parcial."""
    from backend.src.services.adaptive_budget import create_analysis_budget

    with execution_scope(10) as budget:
        phase = create_analysis_budget(selected_agents=6, parallelism=3, per_agent_timeout=10, tradeoff=3)
        budget.deadline = time.monotonic() - 1  # a fase esgotou
        assert phase.expired
        phase.note_progress()  # o que o orquestrador faz ao largar os parados
        assert not phase.expired
