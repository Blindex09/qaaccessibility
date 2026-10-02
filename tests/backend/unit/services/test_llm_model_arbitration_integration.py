from types import SimpleNamespace
from unittest.mock import patch

import pytest

from backend.src.services.llm_client import call_llm
from backend.src.services.response_cache import clear_cache
from backend.src.services.route_advisor import RouteAdvice


@pytest.mark.asyncio
@pytest.mark.parametrize("cache_enabled", [False, True])
async def test_alto_runs_candidate_and_judge_calls_when_quality_is_prioritized(cache_enabled):
    clear_cache()
    calls: list[tuple[str, str]] = []

    class FakeAgent:
        def __init__(self, *, model: str, **_kwargs):
            self.model = model

        def run_conversation(self, *, user_message: str, task_id: str) -> dict:
            calls.append((self.model, user_message))
            if "Respostas candidatas para comparar" in user_message:
                return {"final_response": "resposta julgada"}
            return {"final_response": f"resposta de {self.model}"}

    settings = SimpleNamespace(
        llm_provider="ollama-cloud",
        llm_model="alto",
        llm_api_key="secret",
        llm_base_url=None,
        a11y_response_cache_enabled=cache_enabled,
        a11y_response_cache_ttl_seconds=300.0,
        a11y_model_arbitration_enabled=True,
        a11y_route_advisor_enabled=True,
        agent_timeout_seconds=90,
        a11y_model_arbitration_max_candidates=2,
        build_fallback_model=lambda: None,
    )

    with (
        patch("backend.src.services.llm_client.get_settings", return_value=settings),
        patch("backend.src.services.llm_client.AIAgent", FakeAgent),
        patch(
            "backend.src.services.model_router.resolve_model_and_provider",
            return_value=("ollama-cloud", "modelo-a"),
        ) as legacy_router,
        patch(
            "backend.src.services.route_advisor.advise_route",
            return_value=RouteAdvice(
                ranking=["ollama-cloud::modelo-a", "ollama-cloud::modelo-b"],
                compare_models=["ollama-cloud::modelo-a", "ollama-cloud::modelo-b"],
                judge="ollama-cloud::modelo-b", reason="revisão independente necessária",
            ),
        ),
        patch("backend.src.services.complexity_router.get_current_tradeoff", return_value=2),
    ):
        result = await call_llm(
            system_prompt="Analise acessibilidade.",
            user_prompt="Avalie este componente.",
            agent_label="wcag_semantics",
        )
        if cache_enabled:
            assert await call_llm(
                system_prompt="Analise acessibilidade.", user_prompt="Avalie este componente.",
                agent_label="wcag_semantics",
            ) == "resposta julgada"

    assert result == "resposta julgada"
    assert [model for model, _prompt in calls] == ["modelo-a", "modelo-b", "modelo-b"]
    legacy_router.assert_not_called()
    clear_cache()
