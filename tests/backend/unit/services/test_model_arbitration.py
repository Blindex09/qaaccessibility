import pytest

from backend.src.services.model_arbitration import arbitrate_model_responses


@pytest.mark.asyncio
async def test_arbitration_asks_judge_to_synthesize_without_exposing_process():
    calls: list[tuple[str, str]] = []

    async def fake_judge(system: str, user: str) -> str:
        calls.append((system, user))
        return "resposta final"

    result = await arbitrate_model_responses(
        run_model=fake_judge,
        original_system_prompt="Analise acessibilidade.",
        original_user_prompt="Avalie este componente.",
        responses=[("modelo-a", "achado A"), ("modelo-b", "achado B")],
        response_schema=None,
    )

    assert result == "resposta final"
    assert len(calls) == 1
    assert "modelo-a" not in calls[0][1]
    assert "achado A" in calls[0][1]
    assert "modelos" in calls[0][0]


@pytest.mark.asyncio
async def test_arbitration_rejects_single_candidate():
    async def fake_judge(_system: str, _user: str) -> str:
        return "unused"

    with pytest.raises(ValueError, match="dois candidatos"):
        await arbitrate_model_responses(
            run_model=fake_judge,
            original_system_prompt="s",
            original_user_prompt="u",
            responses=[("modelo-a", "resposta")],
            response_schema=None,
        )
