"""Regressao: portao do usuario pausa o orcamento (2026-10-02).

O teto do turno expirava enquanto o cartao de aprovacao/clarify esperava o
usuario clicar -- o tempo de leitura/click era cobrado como trabalho. Agora
`wait_clarify` abre `pause_for_user_gate`: o deadline efetivo desconta a pausa
(0 pausa = 0 shift; X s esperado = deadline desliza X s a frente).
"""

import threading
import time

import pytest

from backend.src.services import chat_progress
from backend.src.services.execution_scope import (
    ExecutionBudget,
    current_budget,
    execution_scope,
    pause_for_user_gate,
    remaining_seconds,
)


def test_pause_without_budget_is_noop():
    # Rotas non-chat nao tem orcamento: a pausa nao pode quebrar.
    assert current_budget() is None
    with pause_for_user_gate():
        pass


def test_pausa_desloca_o_deadline_efetivo():
    with execution_scope(10) as budget:
        antes = budget.effective_deadline() - budget.deadline
        with pause_for_user_gate():
            time.sleep(0.15)  # simula o usuario lendo o cartao
        depois = budget.effective_deadline() - budget.deadline
        # A pausa empurrou o fim efetivo para frente pelo tempo esperado.
        assert depois > antes + 0.10
        # O deadline teorico (comeco + allowance) nao mudou.
        assert budget.deadline == budget.started_at + budget.unit_seconds * 2


def test_tempo_restante_nao_e_consumido_durante_a_pausa():
    with execution_scope(2) as budget:
        time.sleep(0.2)  # gasta 0.2s de verdade
        restante_antes = remaining_seconds()
        with pause_for_user_gate():
            time.sleep(0.3)  # esperaria expirar (0.2 + 0.3 > 1.0*2? nao) -- usa teto maior
        restante_depois = remaining_seconds()
        # Sem a pausa, teria restado ~0.5s menos; com a pausa, o restante
        # desconta apenas o trabalho real (não menor que antes - 0.05).
        assert restante_depois >= restante_antes - 0.02


def test_pausa_aberta_antes_do_teto_evita_expiracao():
    """Cenário real do teto curto: cartao abriu antes do deadline; o tempo do
    humano não consome, o trabalho real antes/depois da pausa sim.

    Nota: `execution_scope(seconds)` cria deadline = started + seconds*2 (folga
    historica x2), então este teste seta um ExecutionBudget direto para
    controlar o fim com precisao, sem dormir ~20s. As janelas de timing sao
    folgadas porque sob a suíte completa a máquina roda mais lenta: o ponto do
    teste é a SEMANTICA (tempo de humano não consome), nao medir ms."""
    from backend.src.services.execution_scope import _budget, check_execution

    base = time.monotonic()
    budget = ExecutionBudget(started_at=base, deadline=base + 1.5, unit_seconds=10.0)
    token = _budget.set(budget)
    try:
        time.sleep(0.15)  # trabalho real: 0.15s
        budget.pause()
        time.sleep(2.0)  # humano demora: sem pausa expiraria (2.15 > 1.5)
        check_execution()  # não levanta: tempo em pausa não é consumo
        budget.resume()
        time.sleep(1.5)  # trabalho real de novo: 1.65s totais > 1.5 → expira
        with pytest.raises(TimeoutError):
            check_execution()
        assert budget.paused_total >= 1.9
    finally:
        _budget.reset(token)


def test_wait_clarify_abre_pausa_e_recebe_resposta():
    rid, ev = chat_progress.new_clarify()

    def responder():
        time.sleep(0.1)
        chat_progress.answer_clarify(rid, "ok")

    threading.Thread(target=responder, daemon=True).start()
    with execution_scope(10) as budget:
        resposta = chat_progress.wait_clarify(rid, ev, timeout=5.0)
    assert resposta == "ok"
    # A pausa foi fechada e contabilizada.
    assert budget.paused_since is None
    assert budget.paused_total > 0.0


def test_wait_clarify_cancelamento_continua_funcionando_durante_a_pausa():
    token_cancel = chat_progress.new_cancel_token()
    rid, ev = chat_progress.new_clarify()

    def cancelar():
        time.sleep(0.05)
        chat_progress.request_cancel(token_cancel)

    threading.Thread(target=cancelar, daemon=True).start()
    with execution_scope(10):
        resposta = chat_progress.wait_clarify(rid, ev, timeout=5.0)
    chat_progress.clear_cancel_token(token_cancel)
    # Cancelado: resposta vazia e sem pendurar a espera ate o timeout.
    assert resposta == ""
