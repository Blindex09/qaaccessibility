"""Orçamento de tokens configurado pela pessoa (regra 8).

É o único teto de trabalho que existe, e é escolha dela: padrão 0 = sem limite, o código
nunca impõe um número por conta própria. Atingir o limite não é falha nem travamento: o
trabalho pára no próximo limite de chamada e o que já foi apurado é entregue como parcial.
"""

import json

import pytest

from backend.src.config.settings import Settings
from backend.src.services import chat_runtime, execution_scope
from backend.src.services.execution_scope import (
    TokenBudgetReachedError,
    add_tokens,
    check_execution,
)
from run_agent import _accumulate_usage, run_local_tool


@pytest.fixture(autouse=True)
def _no_configured_limit(monkeypatch):
    """Hermético: nunca depende do limite que a pessoa tenha gravado no .env dela."""
    monkeypatch.setattr(execution_scope, "_configured_token_limit", lambda: None)


def test_no_limit_by_default_and_the_code_never_imposes_one(monkeypatch):
    monkeypatch.delenv("TURN_TOKEN_BUDGET", raising=False)
    monkeypatch.setenv("SECRET_KEY", "test-secret-key")
    # Hermético: nunca lê o .env real da pessoa, que pode ter um limite escolhido por ela.
    assert Settings(_env_file=None).turn_token_budget == 0
    with execution_scope.execution_scope(10) as budget:
        add_tokens(10_000_000)
        assert budget.token_limit is None
        check_execution()  # nenhum limite: nada é barrado


def test_usage_of_every_provider_call_feeds_the_budget():
    totals = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    with execution_scope.execution_scope(10, token_limit=1000) as budget:
        _accumulate_usage(totals, {"input_tokens": 100, "output_tokens": 50})
        _accumulate_usage(totals, {"prompt_tokens": 30, "completion_tokens": 20})  # outro provider
        assert budget.tokens_used == 200
    assert totals["total_tokens"] == 200


def test_reaching_the_limit_stops_at_the_next_call_boundary_with_an_honest_message():
    with execution_scope.execution_scope(10, token_limit=500):
        add_tokens(499)
        check_execution()  # ainda dentro do limite
        add_tokens(1)
        with pytest.raises(TokenBudgetReachedError) as caught:
            check_execution()
    assert caught.value.used == 500 and caught.value.limit == 500
    assert "500" in str(caught.value) and "atingido" in str(caught.value)


def test_a_nested_scope_inherits_the_limit_of_the_turn():
    with execution_scope.execution_scope(10, token_limit=100) as outer, execution_scope.execution_scope(
        1000, token_limit=999_999
    ) as inner:
        assert inner is outer and inner.token_limit == 100


def test_tools_are_not_run_once_the_limit_is_reached():
    from tools.registry import registry

    called = []
    registry.tools["budget_probe"] = {
        "schema": {"parameters": {"type": "object", "properties": {}}},
        "handler": lambda args: called.append(args) or "ok",
    }
    try:
        with execution_scope.execution_scope(10, token_limit=10):
            add_tokens(10)
            result = json.loads(run_local_tool("budget_probe", {}))
    finally:
        registry.tools.pop("budget_probe", None)
    assert "encerrada" in result["error"]
    assert called == []


@pytest.mark.asyncio
async def test_chat_turn_ends_with_an_explanation_and_keeps_what_was_already_said(monkeypatch):
    saved = []

    async def fake_impl(*_args):
        yield {"type": "token", "text": "Resultado parcial já apurado."}
        raise TokenBudgetReachedError(900, 800)

    monkeypatch.setattr(chat_runtime, "_stream_chat_impl", fake_impl)
    monkeypatch.setattr(
        chat_runtime.chat_history_store, "append_message",
        lambda role, text, session_id=None: saved.append((role, text)),
    )
    events = [e async for e in chat_runtime.stream_chat("Analise", conversation_id="token-limit")]
    assert not any(e["type"] == "error" for e in events)
    text = "".join(e.get("text", "") for e in events if e["type"] == "token")
    assert "Resultado parcial já apurado." in text
    assert "800" in text and "Configurações" in text  # diz o que aconteceu e como continuar
    assert "continua valendo" in text  # havia algo apurado: a mensagem não promete o que não existe
    assert events[-1]["type"] == "done"
    assert saved and "Resultado parcial já apurado." in saved[-1][1] and "800" in saved[-1][1]


@pytest.mark.asyncio
async def test_chat_scope_gets_the_limit_from_the_persons_settings(monkeypatch):
    seen = {}

    async def fake_impl(*_args):
        seen["limit"] = execution_scope.current_budget().token_limit
        yield {"type": "done", "final": "ok"}

    class FakeSettings:
        agent_timeout_seconds = 90.0
        turn_token_budget = 1234

    monkeypatch.setattr(chat_runtime, "_stream_chat_impl", fake_impl)
    monkeypatch.setattr(chat_runtime, "get_settings", lambda: FakeSettings())
    _ = [e async for e in chat_runtime.stream_chat("oi", conversation_id="token-limit-2")]
    assert seen["limit"] == 1234


@pytest.mark.asyncio
async def test_when_nothing_was_produced_yet_the_message_does_not_pretend_otherwise(monkeypatch):
    async def fake_impl(*_args):
        raise TokenBudgetReachedError(5399, 3000)
        yield  # pragma: no cover

    monkeypatch.setattr(chat_runtime, "_stream_chat_impl", fake_impl)
    monkeypatch.setattr(chat_runtime.chat_history_store, "append_message", lambda *a, **k: None)
    events = [e async for e in chat_runtime.stream_chat("Analise", conversation_id="token-limit-3")]
    text = "".join(e.get("text", "") for e in events if e["type"] == "token")
    assert "Não houve como apurar nada" in text
    assert "já apareceu acima" not in text


# ----------------------------------------------------------------- registro de custo por tipo de chamada
def test_cost_summary_groups_tokens_by_call_type_and_by_model():
    with execution_scope.execution_scope(10) as budget:
        execution_scope.record_call("a11y:classificador", "ollama-cloud", "m1", {"input_tokens": 100, "output_tokens": 20, "total_tokens": 120})
        execution_scope.record_call("a11y:perceiver", "ollama-cloud", "m2", {"total_tokens": 900})
        execution_scope.record_call("a11y:perceiver", "ollama-cloud", "m2", {"total_tokens": 100})
        summary = budget.cost_summary()
    assert summary["total_tokens"] == 1120 and summary["calls"] == 3
    assert summary["by_label"]["a11y:perceiver"] == {"calls": 2, "total": 1000, "input": 0, "output": 0}
    assert list(summary["by_label"])[0] == "a11y:perceiver"  # o mais caro primeiro
    assert summary["by_model"]["ollama-cloud::m2"]["total"] == 1000


def test_every_agent_conversation_records_what_it_cost():
    from unittest.mock import patch

    from run_agent import AIAgent

    agent = AIAgent(provider="openai", model="m", api_key="k", log_prefix="[a11y:roteador]")
    fake = {"final_response": "ok", "usage": {"input_tokens": 7, "output_tokens": 3, "total_tokens": 10}}
    with execution_scope.execution_scope(10) as budget, patch.object(agent, "_run_conversation_inner", return_value=fake):
        agent.run_conversation("oi")
        assert budget.cost_summary()["by_label"] == {"a11y:roteador": {"calls": 1, "total": 10, "input": 7, "output": 3}}


def test_call_without_usage_is_recorded_as_zero_not_invented():
    with execution_scope.execution_scope(10) as budget:
        execution_scope.record_call("a11y:x", "p", "m", None)
        assert budget.cost_summary()["total_tokens"] == 0 and budget.cost_summary()["calls"] == 1
