"""Os papéis da squad são irmãos: reaproveitam uma decisão de rota em vez de pagar uma consulta cada."""

import contextlib
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


@pytest.mark.asyncio
async def test_expert_reviewer_batches_share_one_route_decision():
    """8 lotes pagavam 8 consultas ao roteador (cerca de 3,7 mil tokens cada)."""
    from backend.src.agents.a11y_expert_reviewer import a11y_expert_reviewer as reviewer
    from backend.src.shared.models import AccessibilityIssue

    seen = []

    async def fake_call_llm(**kwargs):
        seen.append(kwargs.get("route_family"))
        return "[]"

    issue = AccessibilityIssue(
        id="i-1", criterion="1.1.1", guideline="WCAG 2.2", severity="high", element="img", description="sem alt", suggestion="adicione alt",
    )
    with patch.object(reviewer, "call_llm", new=fake_call_llm):
        await reviewer._review_single_batch([issue])
    assert seen == ["expert_review"]


@pytest.mark.asyncio
async def test_specialists_of_one_audit_share_a_route_decision_without_each_asking_the_router():
    """Regressão (e2e real 2026-10-08): 9 especialistas pagavam 9 consultas ao roteador (cerca de 3,7 mil tokens cada)."""
    from backend.src.agents.orchestrator import orchestrator
    from backend.src.services import execution_scope
    from backend.src.shared.models import AgentResult

    seen = []

    async def specialist():
        seen.append(execution_scope.default_route_family())
        return AgentResult(agent="s", success=True, data={"issues": []})

    with execution_scope.execution_scope(10):
        await orchestrator._timed("s", specialist)
    assert seen == ["specialist"]
    assert execution_scope.default_route_family() is None  # fora da auditoria nada vaza


@pytest.mark.asyncio
async def test_a_call_without_its_own_family_inherits_the_one_of_the_context(monkeypatch):
    from backend.src.services import execution_scope, llm_client

    captured = {}

    async def fake_advise(*_a, **kwargs):
        captured.update(kwargs)
        raise RuntimeError("para aqui: só queremos ver o que foi pedido ao roteador")

    monkeypatch.setattr("backend.src.services.route_advisor.advise_route", fake_advise)
    from backend.src.config.settings import get_settings

    monkeypatch.setattr(get_settings(), "llm_provider", "ollama-cloud", raising=False)
    monkeypatch.setattr(get_settings(), "llm_model", "alto", raising=False)
    with (
        execution_scope.execution_scope(10),
        execution_scope.route_family_scope("specialist"),
        contextlib.suppress(Exception),
    ):
        await llm_client.call_llm("sys", "user", agent_label="perceiver")
    assert captured, "o caminho do roteador contextual deveria ter sido tomado"
    assert captured["step_type"] == "specialist" and captured["reuse_decision"] is True


def test_reviewer_packs_more_issues_per_batch_so_the_source_is_not_resent_eleven_times():
    from backend.src.agents.a11y_expert_reviewer.a11y_expert_reviewer import _REVIEW_BATCH_SIZE

    assert _REVIEW_BATCH_SIZE >= 12
    issues = list(range(61))
    batches = [issues[i:i + _REVIEW_BATCH_SIZE] for i in range(0, len(issues), _REVIEW_BATCH_SIZE)]
    assert len(batches) <= 5  # eram 11 lotes de 6
