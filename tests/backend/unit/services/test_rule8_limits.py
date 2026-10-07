"""Regra 8: sem relógio fixo, sem teto fixo de tokens, sem máximo fixo de ações.

Cada teste cobre um dos limites que ainda existiam depois da janela de progresso:
o prazo por especialista, o teto de tokens por chamada, o máximo de chamadas de
ferramenta do factory e a janela fixa da consulta de roteamento.
"""

import asyncio
import inspect
import json
import time
from itertools import islice
from unittest.mock import MagicMock, patch

import pytest

from backend.src.agents.orchestrator import orchestrator
from backend.src.services.execution_scope import current_budget, execution_scope, note_progress
from backend.src.services.factory_adapter import run_factory
from backend.src.services.llm_client import call_llm_structured
from backend.src.services.route_advisor import RouteCandidate, rank_candidates
from backend.src.shared.models import AgentResult
from run_agent import AIAgent, _provider_output_limit


def _tight(budget, seconds):
    budget.patience = seconds
    budget.deadline = time.monotonic() + seconds


# ----------------------------------------------------------------- prazo por especialista
@pytest.mark.asyncio
async def test_specialist_that_keeps_progressing_is_not_cut_by_a_per_agent_clock(monkeypatch):
    monkeypatch.setattr(orchestrator, "_get_agent_timeout", lambda: 0.01)

    async def working_agent():
        for _ in range(8):
            await asyncio.sleep(0.05)
            note_progress()
        return AgentResult(agent="s", success=True, data={"issues": []})

    with execution_scope(10) as budget:
        _tight(budget, 0.2)
        result, _ = await orchestrator._timed("s", working_agent)
    assert result.success is True


@pytest.mark.asyncio
async def test_specialist_without_any_progress_returns_a_partial_result():
    async def hung_agent():
        await asyncio.sleep(5)

    with execution_scope(10) as budget:
        _tight(budget, 0.15)
        result, _ = await orchestrator._timed("s", hung_agent)
    assert result.success is False
    assert "Timeout" in (result.error or "")


# ----------------------------------------------------------------- tokens
def test_agent_has_no_output_cap_unless_one_was_requested():
    assert AIAgent(provider="openai", model="gpt-5.6", api_key="k").max_tokens is None
    assert AIAgent(provider="openai", model="gpt-5.6", api_key="k", max_tokens=512).max_tokens == 512


def test_responses_request_omits_the_output_cap_when_none_was_requested():
    agent = AIAgent(provider="openai", model="gpt-5.6", api_key="k")
    captured: dict = {}
    client = MagicMock()

    def _create(**kwargs):
        captured.update(kwargs)
        resp = MagicMock()
        resp.status = "completed"
        resp.output_text = "ok"
        resp.output = []
        resp.usage = MagicMock(input_tokens=1, output_tokens=1, total_tokens=2)
        return resp

    client.responses.create.side_effect = _create
    with patch("openai.OpenAI", return_value=client):
        agent._run_openai("hello")
    assert captured and "max_output_tokens" not in captured


def test_anthropic_uses_a_high_default_because_the_api_requires_a_number():
    agent = AIAgent(provider="anthropic", model="claude-sonnet-5-5", api_key="k")
    assert agent._anthropic_max_tokens() == 32000
    assert AIAgent(provider="anthropic", model="m", api_key="k", max_tokens=777)._anthropic_max_tokens() == 777


def test_provider_output_limit_is_read_from_the_providers_own_error():
    err = Exception("max_tokens: 64000 > 32000, which is the maximum allowed number of output tokens for model x")
    assert _provider_output_limit(err) == 32000
    assert _provider_output_limit(Exception("401 invalid api key")) is None


def test_anthropic_retries_once_with_the_limit_the_provider_reported():
    agent = AIAgent(provider="anthropic", model="m", api_key="k")
    sent = []

    def once(_client, **kwargs):
        sent.append(kwargs["max_tokens"])
        if len(sent) == 1:
            raise Exception("max_tokens: 64000 > 32000, which is the maximum allowed number of output tokens")
        return "ok"

    with patch.object(agent, "_anthropic_messages_create_once", side_effect=once):
        assert agent._anthropic_messages_create(object(), max_tokens=64000) == "ok"
    assert sent == [64000, 32000]


def test_anthropic_does_not_retry_on_unrelated_errors():
    agent = AIAgent(provider="anthropic", model="m", api_key="k")
    with patch.object(agent, "_anthropic_messages_create_once", side_effect=Exception("401 invalid api key")), \
            pytest.raises(Exception, match="401"):
        agent._anthropic_messages_create(object(), max_tokens=64000)


@pytest.mark.asyncio
async def test_structured_escalation_has_no_fixed_ceiling():
    budgets: list[int] = []

    async def fake_call(*_a, **kwargs):
        budgets.append(kwargs["max_tokens"])
        # com mais espaço o modelo avança mais antes de ser cortado de novo
        partial = ['{"items": [1, 2', '{"items": [1, 2, 3, 4, 5']
        return partial[len(budgets) - 1] if len(budgets) < 3 else '{"ok": true}'

    with patch("backend.src.services.llm_client.call_llm", new=fake_call):
        result = await call_llm_structured("sys", "user", build=json.loads, max_tokens=20000)
    assert result == {"ok": True}
    assert budgets == [20000, 40000, 80000]  # antes parava em 32768


@pytest.mark.asyncio
async def test_structured_escalation_stops_when_the_same_output_comes_back():
    calls = 0

    async def clamped(*_a, **_kw):
        nonlocal calls
        calls += 1
        return '{"items": [1, 2'  # o provider cortou no mesmo ponto, mesmo com mais espaço

    with patch("backend.src.services.llm_client.call_llm", new=clamped), pytest.raises(json.JSONDecodeError):
        await call_llm_structured("sys", "user", build=json.loads, max_tokens=1000)
    assert calls == 2


# ----------------------------------------------------------------- ações
def test_factory_has_no_fixed_cap_on_tool_calls():
    assert "max_tool_calls" not in inspect.signature(run_factory).parameters


def test_tool_agent_loop_is_not_capped_by_max_iterations():
    agent = AIAgent(enabled_toolsets=["probe"], max_iterations=1)
    with execution_scope(10):
        assert len(list(islice(agent._iterations(), 6))) == 6


def test_single_shot_leaf_is_still_one_call_by_structure():
    agent = AIAgent(enabled_toolsets=[], max_iterations=1)
    with execution_scope(10):
        assert len(list(agent._iterations())) == 1


def test_every_conversation_runs_inside_a_progress_budget():
    seen = []
    agent = AIAgent(provider="openai", model="m", api_key="k")
    with patch.object(agent, "_run_conversation_inner", side_effect=lambda *a, **k: seen.append(current_budget()) or {}):
        agent.run_conversation("oi")
    assert seen and seen[0] is not None
    assert current_budget() is None


# ----------------------------------------------------------------- roteamento
@pytest.mark.asyncio
async def test_route_consultation_that_keeps_progressing_is_not_cut():
    cands = [RouteCandidate("ollama-cloud", m, 64000, ("tools",), 1, 2, .75, .75, 0) for m in ("a", "b", "c")]
    answer = json.dumps({"ranking": ["ollama-cloud::b", "ollama-cloud::a", "ollama-cloud::c"], "complexity": "low",
                         "preference": "cost", "compare_models": [], "judge": "", "reason": "economia", "updates": []})

    async def slow_but_alive(*_args):
        for _ in range(8):
            await asyncio.sleep(0.05)
            note_progress()
        return answer

    with execution_scope(10) as budget:
        _tight(budget, 0.2)
        advice = await rank_candidates(cands, task="t-rule8", step_type="audit", ask=slow_but_alive)
    assert advice.source == "ia"


# ----------------------------------------------------------------- clientes HTTP dos providers
def test_provider_http_clients_have_no_read_clock_and_keep_sdk_retries_inside_a_turn():
    """Regressão: dentro do turno os clientes saíam com max_retries=0 e um timeout de
    leitura fixo de 180s, o que matava uma chamada lenta e proibia o SDK de esperar e
    tentar de novo em 429/queda de conexão (as docstrings dos testes dizem que isso nunca
    pode ser desligado; eles só passavam porque rodam sem orçamento)."""
    import httpx

    from tests.backend.unit.test_run_agent import _mock_anthropic_client

    with execution_scope(10), patch("anthropic.Anthropic") as mock_cls:
        mock_cls.return_value = _mock_anthropic_client()
        AIAgent(model="claude-opus-5", provider="anthropic", api_key="k")._run_anthropic("hello")
    kwargs = mock_cls.call_args.kwargs
    assert "max_retries" not in kwargs
    timeout = kwargs["timeout"]
    assert isinstance(timeout, httpx.Timeout)
    assert timeout.read is not None and timeout.read >= 30  # só o SILÊNCIO encerra, nunca a duração
    assert timeout.connect is not None


def test_openai_and_ollama_clients_share_the_same_no_read_clock_policy():
    import httpx

    from run_agent import _provider_timeout

    timeout = _provider_timeout()
    assert isinstance(timeout, httpx.Timeout) and timeout.read is not None


def test_factory_runtime_has_no_fixed_timeout_parameter():
    assert "timeout" not in inspect.signature(run_factory).parameters


def test_the_silence_window_follows_the_turns_adaptive_patience():
    """Conexão muda por toda a janela encerra; a janela cresce com a complexidade que a IA declarou."""
    from run_agent import _provider_timeout

    with execution_scope(10) as budget:
        base = _provider_timeout().read
        budget.adapt("high")
        assert _provider_timeout().read > base
        assert _provider_timeout().read == budget.patience
    assert _provider_timeout().read == 180.0  # sem turno: o mesmo padrão da janela inicial
