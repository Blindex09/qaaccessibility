import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.src.services.route_advisor import (
    RouteAdvice,
    RouteCandidate,
    clear_advisor_cache,
    eligible_candidates,
    rank_candidates,
    route_credentials,
)


@pytest.fixture(autouse=True)
def clean_cache():
    clear_advisor_cache()
    yield
    clear_advisor_cache()


def candidates():
    return [RouteCandidate("ollama-cloud", m, 64000, ("tools",), 1, 2, .75, .75, 0)
            for m in ("a", "b", "c")]


def answer(**extra):
    return json.dumps(dict(ranking=["ollama-cloud::b", "ollama-cloud::a", "ollama-cloud::c"],
                           complexity="low", preference="cost", compare_models=[], judge="",
                           reason="a tarefa pede economia", **extra))


@pytest.mark.asyncio
async def test_model_decides_ranking_and_single_response_instead_of_quality_threshold():
    ask = AsyncMock(return_value=answer())
    advice = await rank_candidates(candidates(), task="contexto real", step_type="audit", ask=ask)
    assert advice.ranking[0] == "ollama-cloud::b"
    assert advice.source == "ia"
    assert advice.compare_models == []
    assert "contexto real" in ask.call_args.args[1]


@pytest.mark.asyncio
@pytest.mark.parametrize("raw", [
    '{"ranking":["malicious::outside"],"reason":"x"}',
    '{"ranking":["ollama-cloud::b","ollama-cloud::b"],"reason":"x"}',
    '{"ranking":["ollama-cloud::b"],"judge":"outside","reason":"x"}',
    'not json',
])
async def test_invalid_advice_falls_back_without_inventing_model_or_comparison(raw):
    advice = await rank_candidates(candidates(), task="x", step_type="audit",
                                   ask=AsyncMock(return_value=raw))
    assert advice.source == "fallback"
    assert advice.ranking[0] == "ollama-cloud::a"
    assert advice.compare_models == []


@pytest.mark.asyncio
async def test_cache_hits_same_context_but_new_task_or_catalog_is_reclassified():
    ask = AsyncMock(return_value=answer())
    for task in ["first", "first", "second"]:
        await rank_candidates(candidates(), task=task, step_type="audit", ask=ask)
    assert ask.await_count == 2
    changed = candidates()[:2]
    ask.return_value = '{"ranking":["ollama-cloud::b","ollama-cloud::a"],"reason":"x"}'
    await rank_candidates(changed, task="second", step_type="audit", ask=ask)
    assert ask.await_count == 3


@pytest.mark.asyncio
async def test_stalled_router_preserves_only_objective_fallback():
    """Sem prazo legado: quem encerra uma consulta que não avança é a falta de progresso."""
    import asyncio
    import time

    from backend.src.services.execution_scope import execution_scope

    async def slow(*_args):
        await asyncio.sleep(5)
        return answer()

    with execution_scope(10) as budget:
        budget.patience = 0.1
        budget.deadline = time.monotonic() + 0.1
        advice = await rank_candidates(candidates(), task="x", step_type="audit", ask=slow)
    assert advice.source == "fallback"


@pytest.mark.asyncio
async def test_router_without_a_budget_has_no_clock_at_all():
    """Não existe prazo escondido: sem orçamento a consulta apenas espera a resposta."""
    import asyncio
    import inspect

    from backend.src.services.execution_scope import run_until_stalled
    from backend.src.services.route_advisor import advise_route

    async def eventually():
        await asyncio.sleep(0.2)
        return "resposta"

    assert await run_until_stalled(eventually()) == "resposta"
    assert "fallback_timeout" not in inspect.signature(run_until_stalled).parameters
    assert "timeout" not in inspect.signature(rank_candidates).parameters
    assert "timeout" not in inspect.signature(advise_route).parameters


def test_eligibility_never_relaxes_vision_or_context():
    from backend.src.services.ollama_cloud_adapter import OllamaCloudModelDescriptor

    descriptors = [OllamaCloudModelDescriptor(id="text", has_vision=False, context_window=64000),
                   OllamaCloudModelDescriptor(id="small-vision", has_vision=True, context_window=100)]
    with patch("backend.src.services.ollama_cloud_adapter.discover_ollama_cloud_descriptors",
               return_value=descriptors):
        assert eligible_candidates("ollama-cloud", input_tokens=1000, output_tokens=1000,
                                   needs_tools=True, needs_vision=True) == []


def test_credentials_are_not_forwarded_to_another_provider(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "other-key")
    monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)
    assert route_credentials("anthropic", "openai", "primary-key", "primary-url") == ("other-key", None)
    assert route_credentials("openai", "openai", "primary-key", "primary-url") == ("primary-key", "primary-url")


@pytest.mark.asyncio
async def test_full_context_not_silently_truncated_and_schema_excludes_harness_source():
    ask = AsyncMock(return_value=answer())
    task = "x" * 15001 + "continuação relevante"
    await rank_candidates(candidates(), task=task, step_type="chat", ask=ask)
    assert json.loads(ask.call_args.args[1])["task"] == task
    assert "source" not in ask.call_args.args[2]["properties"]


@pytest.mark.asyncio
async def test_auto_compares_only_providers_with_credentials():
    from backend.src.services.route_advisor import advise_route

    async def rank(items, **_kwargs):
        assert {item.provider for item in items} == {"openai", "anthropic"}
        return RouteAdvice(
            ranking=[items[1].key, items[0].key], reason="contexto", source="ia",
        )

    with (
        patch("backend.src.services.model_router._available_auto_providers", return_value=["openai", "anthropic"]),
        patch("backend.src.services.route_advisor.eligible_candidates",
              side_effect=lambda p, **_k: [RouteCandidate(p, "model", 64000, ("tools",), 1, 2, .75, .75, 0)]),
        patch("backend.src.services.route_advisor.rank_candidates", side_effect=rank),
    ):
        advice = await advise_route("auto", "alto", task="contexto", step_type="chat", api_key=None,
                                    base_url=None, output_tokens=1000)
    assert advice.ranking[0] == "anthropic::model"


def test_model_name_heuristics_cannot_grant_tools_or_vision():
    from backend.src.services.ollama_cloud_adapter import OllamaCloudModelDescriptor

    descriptor = OllamaCloudModelDescriptor(
        id="qwen-vision-reasoner", has_tools=True, has_vision=True, capabilities=[],
    )
    with patch("backend.src.services.ollama_cloud_adapter.discover_ollama_cloud_descriptors",
               return_value=[descriptor]):
        assert eligible_candidates("ollama-cloud", input_tokens=100, output_tokens=100,
                                   needs_tools=True, needs_vision=True) == []


@pytest.mark.asyncio
async def test_invalid_contract_gets_one_bounded_repair_not_a_semantic_override():
    ask = AsyncMock(side_effect=['{"ranking":["invented"],"reason":"x"}', answer()])
    advice = await rank_candidates(candidates(), task="contexto", step_type="chat", ask=ask)
    assert advice.source == "ia"
    assert advice.ranking[0] == "ollama-cloud::b"
    assert ask.await_count == 2


def test_bootstrap_uses_fresh_observed_contract_results_not_model_name():
    from backend.src.services.route_advisor import _bootstrap_candidate

    items = candidates()
    with (
        patch("backend.src.services.model_reliability.get_reliability_score", side_effect=lambda p, m: .9 if m == "b" else .4),
        patch("backend.src.services.model_reliability.get_latency_score", return_value=.5),
    ):
        assert _bootstrap_candidate(items).model == "b"
    with (
        patch("backend.src.services.model_reliability.get_reliability_score", side_effect=lambda p, m: .9 if m == "a" else .4),
        patch("backend.src.services.model_reliability.get_latency_score", return_value=.5),
    ):
        assert _bootstrap_candidate(items).model == "a"


@pytest.mark.asyncio
async def test_invalid_bootstrap_output_is_recorded_and_repair_can_use_another_model():
    from backend.src.services.route_advisor import advise_route

    reliability = {"a": .8, "b": .75, "c": .7}
    used = []
    outcomes = []

    def construct(**kwargs):
        assert kwargs["stream_delta_callback"] is None
        used.append(kwargs["model"])
        agent = MagicMock()
        agent.run_conversation.return_value = {"final_response": "" if len(used) == 1 else answer()}
        return agent

    def record(provider, model, success, duration_ms):
        outcomes.append(success)
        reliability[model] = .4 if not success else .9

    with (
        patch("backend.src.services.route_advisor.eligible_candidates", return_value=candidates()),
        patch("backend.src.services.model_reliability.get_reliability_score", side_effect=lambda p, m: reliability[m]),
        patch("backend.src.services.model_reliability.get_latency_score", return_value=.5),
        patch("backend.src.services.model_reliability.record_call_outcome", side_effect=record),
        patch("run_agent.AIAgent", side_effect=construct),
    ):
        advice = await advise_route("ollama-cloud", "alto", task="contexto", step_type="triage",
                                    api_key="dummy", base_url=None, output_tokens=500)
    assert used == ["a", "b"]
    assert outcomes == [False, True]
    assert advice.source == "ia"
