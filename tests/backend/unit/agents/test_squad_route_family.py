"""Os papéis da squad são irmãos: reaproveitam uma decisão de rota em vez de pagar uma consulta cada."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from backend.src.agents.squad.role_agents._runner import run_role
from backend.src.agents.squad.roles import SquadRole
from backend.src.services.route_advisor import RouteCandidate, rank_candidates


@pytest.mark.asyncio
async def test_every_squad_role_shares_one_route_family():
    seen = []

    async def fake_structured(**kwargs):
        seen.append(kwargs["route_family"])
        return {"decisions": [], "blockers": [], "handoff": ""}

    with patch("backend.src.agents.squad.role_agents._runner.call_llm_structured", new=fake_structured):
        for role in (SquadRole.TECH_LEAD, SquadRole.QA_LEAD):
            await run_role(role=role, system_prompt="papel", context={"objetivo": "x"})
    assert seen == ["squad", "squad"]


@pytest.mark.asyncio
async def test_sibling_roles_with_different_contracts_pay_one_router_consultation():
    cands = [RouteCandidate("ollama-cloud", m, 64000, ("tools",), 1, 2, .75, .75, 0) for m in ("a", "b", "c")]
    ask = AsyncMock(return_value=json.dumps({
        "ranking": ["ollama-cloud::b", "ollama-cloud::a", "ollama-cloud::c"], "complexity": "low",
        "preference": "cost", "compare_models": [], "judge": "", "reason": "economia"}))
    for contract in ("contrato do tech lead", "contrato do qa lead muito diferente"):
        await rank_candidates(cands, task=contract, step_type="squad-teste-familia", ask=ask, cache_by_step=True)
    assert ask.await_count == 1
