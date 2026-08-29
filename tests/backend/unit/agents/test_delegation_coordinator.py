from unittest.mock import AsyncMock, patch

import pytest

from backend.src.agents.delegation_coordinator.delegation_coordinator import (
    MAX_DELEGATIONS,
    run_delegation_coordinator,
)


@pytest.mark.asyncio
class TestDelegationCoordinator:
    async def test_no_skipped_agents_short_circuits_without_llm_call(self):
        """Sem agentes pulados, nao ha o que delegar -- nem deve chamar o LLM."""
        with patch(
            "backend.src.agents.delegation_coordinator.delegation_coordinator.call_llm_structured",
            new=AsyncMock(side_effect=AssertionError("nao deveria chamar o LLM")),
        ):
            result = await run_delegation_coordinator("- [high] 1.1.1 -- img", {})
        assert result.success is True
        assert result.data["delegations"] == []

    async def test_coordinator_delegates_valid_skipped_agent(self):
        with patch(
            "backend.src.agents.delegation_coordinator.delegation_coordinator.call_llm_structured",
            new=AsyncMock(return_value={
                "delegations": [{"target_agent": "widgets_a11y", "reason": "achados sugerem widget custom"}]
            }),
        ):
            result = await run_delegation_coordinator(
                "- [high] 4.1.2 -- div[role=tab]",
                {"widgets_a11y": "sem evidencia estrutural de widget"},
            )
        assert result.success is True
        assert result.data["delegations"] == [
            {"target_agent": "widgets_a11y", "reason": "achados sugerem widget custom"}
        ]

    async def test_coordinator_ignores_hallucinated_agent_name(self):
        """target_agent que nao esta na lista de pulados (nome inventado pelo
        LLM) deve ser descartado -- nunca aciona agente fora do catalogo real."""
        with patch(
            "backend.src.agents.delegation_coordinator.delegation_coordinator.call_llm_structured",
            new=AsyncMock(return_value={
                "delegations": [{"target_agent": "agente_que_nao_existe", "reason": "x"}]
            }),
        ):
            result = await run_delegation_coordinator(
                "- [high] 4.1.2 -- div",
                {"widgets_a11y": "sem evidencia estrutural"},
            )
        assert result.data["delegations"] == []

    async def test_coordinator_caps_at_max_delegations(self):
        skipped = {f"agent_{i}": "motivo" for i in range(5)}
        many_delegations = [{"target_agent": name, "reason": "motivo"} for name in skipped]
        with patch(
            "backend.src.agents.delegation_coordinator.delegation_coordinator.call_llm_structured",
            new=AsyncMock(return_value={"delegations": many_delegations}),
        ):
            result = await run_delegation_coordinator("- [high] x -- y", skipped)
        assert len(result.data["delegations"]) == MAX_DELEGATIONS

    async def test_llm_failure_degrades_gracefully(self):
        """Delegacao e reforco best-effort -- falha do LLM nao deve propagar
        excecao nem derrubar o pipeline principal."""
        with patch(
            "backend.src.agents.delegation_coordinator.delegation_coordinator.call_llm_structured",
            new=AsyncMock(side_effect=Exception("provider indisponivel")),
        ):
            result = await run_delegation_coordinator(
                "- [high] 4.1.2 -- div",
                {"widgets_a11y": "sem evidencia"},
            )
        assert result.success is False
        assert result.data["delegations"] == []
        assert "provider indisponivel" in result.error
