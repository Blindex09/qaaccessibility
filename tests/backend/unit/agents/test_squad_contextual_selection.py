"""Role selection is model judgment; the harness validates only contracts."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from backend.src.agents.clarifier.clarifier import _construir_classificacao, run_clarifier
from backend.src.agents.squad.contracts import RoleDecision
from backend.src.agents.squad.coordinator import SquadCoordinator
from backend.src.agents.squad.roles import SquadRole
from backend.src.services.chat_tools import consult_squad


@pytest.mark.parametrize("roles", [["tech_lead"], ["qa_lead", "product_owner"], [], ["scrum_master"]])
async def test_classifier_preserves_model_selection_for_same_input(roles):
    async def structured(*_args, build, **_kwargs):
        return build(json.dumps({"intent": "analyze_url", "squad_roles": roles}))

    with patch("backend.src.agents.clarifier.clarifier.call_llm_structured", side_effect=structured):
        result = await run_clarifier("Mesmo contexto; a escolha é do modelo.")
    assert result.success
    assert result.data["squad_roles"] == roles


@pytest.mark.parametrize("roles", [["unknown"], ["qa_lead", "qa_lead"], "tech_lead", [False]])
def test_invalid_role_contract_is_rejected(roles):
    with pytest.raises(ValueError):
        _construir_classificacao(json.dumps({"intent": "analyze_url", "squad_roles": roles}))


async def test_chosen_order_is_not_replaced_by_management_chain():
    squad = SquadCoordinator("Auditoria inicial")
    tech = AsyncMock(return_value=RoleDecision(role=SquadRole.TECH_LEAD, decisions=["Inspecionar títulos"], handoff={"scope": "headings"}))
    po = AsyncMock(return_value=RoleDecision(role=SquadRole.PRODUCT_OWNER, decisions=["Preservar escopo"]))
    with patch("backend.src.agents.squad.coordinator.run_tech_lead", tech), patch("backend.src.agents.squad.coordinator.run_product_owner", po), patch("backend.src.agents.squad.coordinator.run_engineering_manager", new=AsyncMock()) as em:
        events = [event async for event in squad.run_selected_roles(["tech_lead", "product_owner"], {"message": "Escopo inicial"})]
    assert [event["role"] for event in events if event["type"] == "squad_decision"] == ["tech_lead", "product_owner"]
    assert po.call_args.args[0]["handoffs"]["tech_lead"] == {"scope": "headings"}
    assert tech.call_args.args[0]["current_request"]["message"] == "Escopo inicial"
    em.assert_not_called()
    assert squad.plan.task("cycle-planning").status.value == "backlog"
    assert squad.plan.task("a11y-analysis").depends_on == []
    assert squad.plan.task("tech-approach").metadata["work_kind"] == "role_consultation_not_executed_verification"


async def test_new_scope_can_reconsult_completed_role():
    squad = SquadCoordinator("Auditoria")
    runner = AsyncMock(return_value=RoleDecision(role=SquadRole.TECH_LEAD, decisions=["Abordagem revista"]))
    with patch("backend.src.agents.squad.coordinator.run_tech_lead", runner):
        for context in ({"message": "Primeiro pedido"}, {"message": "Escopo mudou"}):
            _ = [event async for event in squad.run_selected_roles(["tech_lead"], context)]
    assert runner.await_count == 2
    assert runner.call_args.args[0]["current_request"]["message"] == "Escopo mudou"


def test_registered_tool_runs_roles_and_passes_real_session_evidence():
    from tools.registry import registry

    snapshot = SquadCoordinator("Auditoria").plan.to_dict()
    runner = AsyncMock(return_value=RoleDecision(role=SquadRole.QA_LEAD, decisions=["Exige teste manual"]))
    with patch("backend.src.services.squad_plan_store.load_squad_plan", return_value=snapshot), patch("backend.src.services.squad_plan_store.save_squad_plan") as save, patch("backend.src.services.last_analysis_store.get_last_analysis", return_value=([{"criterion": "3.1.1"}], "https://example.com")), patch("backend.src.agents.squad.coordinator.run_qa_lead", runner):
        result = json.loads(registry.tools["consult_squad"]["handler"]({"roles": ["qa_lead"], "context": "Reveja os achados"}))
    assert result["decisions"][0]["role"] == "qa_lead"
    evidence = runner.call_args.args[0]["current_request"]["observed_analysis"]
    assert evidence["issues"] == [{"criterion": "3.1.1"}]
    assert evidence["target"] == "https://example.com"
    save.assert_called_once()
    assert registry.tools["consult_squad"]["is_async"] is False


def test_invalid_tool_selection_cannot_execute_any_role():
    with patch("backend.src.agents.squad.coordinator.run_tech_lead", new=AsyncMock()) as runner, pytest.raises(ValueError):
        consult_squad({"roles": ["tech_lead", "unknown"], "context": "x"})
    runner.assert_not_called()


async def test_scrum_master_selection_survives_restore_without_timer_policy():
    squad = SquadCoordinator("Replanejar")
    runner = AsyncMock(return_value=RoleDecision(role=SquadRole.SCRUM_MASTER, decisions=["Rever a dependência"]))
    with patch("backend.src.agents.squad.coordinator.run_scrum_master", runner):
        _ = [event async for event in squad.run_selected_roles(["scrum_master"], {"message": "Novo contexto"})]
    restored = SquadCoordinator.restore(squad.plan.to_dict())
    assert restored.plan.task("flow-health").status.value == "done"
    assert restored.plan.decisions[0].role is SquadRole.SCRUM_MASTER
