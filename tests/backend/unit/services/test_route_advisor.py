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


def test_router_input_keeps_start_end_and_total_size_instead_of_the_whole_task():
    from backend.src.services.route_advisor import _TASK_HEAD_CHARS, _TASK_TAIL_CHARS, compact_task

    short = "pedido curto"
    assert compact_task(short) == short  # nada a cortar: nada muda
    long_task = "INICIO" + "x" * 20000 + "FIM-DO-PEDIDO"
    compact = compact_task(long_task)
    assert compact.startswith("INICIO") and compact.endswith("FIM-DO-PEDIDO")
    assert len(compact) < _TASK_HEAD_CHARS + _TASK_TAIL_CHARS + 200
    assert str(len(long_task)) in compact  # o roteador ainda sabe quão grande a tarefa é


@pytest.mark.asyncio
async def test_control_plane_step_does_not_ask_the_router_again_for_a_different_text():
    """Etapa interna (triagem, reranking): a decisão não muda com o texto de cada pedido."""
    ask = AsyncMock(return_value=answer())
    await rank_candidates(candidates(), task="primeiro pedido", step_type="kb-rerank", ask=ask, cache_by_step=True)
    await rank_candidates(candidates(), task="outro texto totalmente diferente", step_type="kb-rerank", ask=ask,
                          cache_by_step=True)
    assert ask.await_count == 1


@pytest.mark.asyncio
async def test_user_facing_step_still_asks_again_when_the_text_changes():
    ask = AsyncMock(return_value=answer())
    await rank_candidates(candidates(), task="primeiro pedido", step_type="chat", ask=ask)
    await rank_candidates(candidates(), task="outro pedido", step_type="chat", ask=ask)
    assert ask.await_count == 2


@pytest.mark.asyncio
async def test_different_steps_never_share_a_cached_decision():
    ask = AsyncMock(return_value=answer())
    await rank_candidates(candidates(), task="t", step_type="kb-rerank", ask=ask, cache_by_step=True)
    await rank_candidates(candidates(), task="t", step_type="clarifier", ask=ask, cache_by_step=True)
    assert ask.await_count == 2


@pytest.mark.asyncio
async def test_control_plane_cache_survives_the_live_telemetry_of_the_candidates_changing():
    """Regressão (e2e real 2026-10-07): a chave incluía confiabilidade/latência/tentativas, que mudam a
    cada chamada, então o cache de etapas internas nunca acertava e cada turno pagava 3 consultas."""
    ask = AsyncMock(return_value=answer())
    first = candidates()
    await rank_candidates(first, task="t1", step_type="kb-rerank-telemetria", ask=ask, cache_by_step=True)
    after_a_call = [RouteCandidate(c.provider, c.model, c.context_window, c.capabilities, c.cost_input,
                                   c.cost_output, c.reliability - .1, c.latency_score + .1, c.attempts + 7)
                    for c in first]
    await rank_candidates(after_a_call, task="t2", step_type="kb-rerank-telemetria", ask=ask, cache_by_step=True)
    assert ask.await_count == 1


@pytest.mark.asyncio
async def test_control_plane_cache_is_not_reused_when_the_set_of_models_changes():
    ask = AsyncMock(return_value=answer())
    await rank_candidates(candidates(), task="t", step_type="kb-rerank-conjunto", ask=ask, cache_by_step=True)
    fewer = candidates()[:2]
    ask_fewer = AsyncMock(return_value=json.dumps(dict(
        ranking=["ollama-cloud::b", "ollama-cloud::a"], complexity="low", preference="cost",
        compare_models=[], judge="", reason="dois modelos")))
    await rank_candidates(fewer, task="t", step_type="kb-rerank-conjunto", ask=ask_fewer, cache_by_step=True)
    assert ask.await_count == 1 and ask_fewer.await_count == 1  # conjunto diferente: nova consulta


@pytest.mark.asyncio
async def test_router_gets_compact_candidate_facts_without_repeating_provider_and_model_name():
    seen = {}

    async def ask(system, payload, schema):
        seen["payload"] = json.loads(payload)
        return answer()

    await rank_candidates(candidates(), task="t-fatos", step_type="chat-fatos", ask=ask)
    first = seen["payload"]["candidates"][0]
    assert first["id"] == "ollama-cloud::a"
    assert "provider" not in first and "model" not in first  # já estão no id
    assert set(first) >= {"capabilities", "context_window", "cost_input", "cost_output",
                          "reliability", "latency_score", "attempts"}
    assert first["reliability"] == round(first["reliability"], 2)


@pytest.mark.asyncio
async def test_router_may_rank_only_the_best_and_the_harness_completes_the_order():
    """Pedir todos os candidatos custa tokens de saída; o resto vem da confiabilidade observada."""
    from backend.src.services.route_advisor import _SYSTEM

    assert "no máximo 5" in _SYSTEM
    partial = json.dumps(dict(ranking=["ollama-cloud::c"], complexity="low", preference="cost",
                              compare_models=[], judge="", reason="só o melhor"))
    advice = await rank_candidates(candidates(), task="t-parcial", step_type="chat-parcial",
                                   ask=AsyncMock(return_value=partial))
    assert advice.ranking[0] == "ollama-cloud::c"
    assert set(advice.ranking) == {"ollama-cloud::a", "ollama-cloud::b", "ollama-cloud::c"}


@pytest.mark.asyncio
async def test_knowledge_rerank_is_a_cheap_control_step():
    from backend.src.services import a11y_knowledge

    seen = {}

    async def fake_call(**kwargs):
        seen.update(kwargs)
        return "[0, 1]"

    items = [a11y_knowledge.KnowledgeChunk(str(i), "fonte", f"titulo {i}", "texto") for i in range(2)]
    with patch("backend.src.services.llm_client.call_llm", new=fake_call):
        await a11y_knowledge.rerank_chunks("pergunta", items, top_k=2)
    assert seen["model_tier"] == "fast"


def test_router_is_told_that_reasoning_is_the_biggest_hidden_cost():
    """Regressão (e2e real 2026-10-07): o revisor pensou ~22 mil tokens para devolver 900. O roteador
    decide o esforço pela complexidade, então precisa saber o que cada nível custa."""
    from backend.src.services.route_advisor import _SYSTEM

    assert "maior custo escondido" in _SYSTEM
    assert "Use low para triagem" in _SYSTEM


def test_low_complexity_means_no_extra_reasoning_because_the_low_level_is_not_cheap():
    """Medido ao vivo: nos modelos de raciocínio o nível "low" gastou 6.372 tokens e pensar zero gastou 169."""
    from backend.src.services.llm_client import _EFFORT_FOR_COMPLEXITY

    assert _EFFORT_FOR_COMPLEXITY == {"low": "none", "medium": "medium", "high": "high"}
