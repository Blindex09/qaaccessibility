import json
from unittest.mock import AsyncMock, patch

import pytest

from backend.src.agents.design_review.design_review import run_design_review

RISK_FLAG = {
    "id": "risk-1",
    "risk": "Drag-and-drop reordering has no keyboard alternative described.",
    "wcag_criteria": ["2.1.1 Keyboard", "2.5.7 Dragging Movements"],
    "severity": "high",
    "rationale": "The requirement only describes drag handles, no keyboard-based reorder action.",
    "recommendation": "Add a 'Move up/down' button alternative alongside the drag handle.",
}


@pytest.mark.asyncio
class TestDesignReviewAgent:
    """Achado real (2026-08-27): diferente dos outros 29 especialistas (que
    auditam HTML/codigo que ja existe), este agente antecipa risco a partir de
    requisito em texto livre -- ANTES do codigo existir (shift-left)."""

    async def test_contract_on_success(self):
        with patch(
            "backend.src.agents.design_review.design_review.call_llm",
            new=AsyncMock(return_value=json.dumps([RISK_FLAG])),
        ):
            result = await run_design_review("Allow users to reorder a list of cards via drag-and-drop.")
        assert result.agent == "design_review"
        assert result.success is True
        assert len(result.data["risk_flags"]) == 1
        assert result.data["risk_flags"][0]["severity"] == "high"
        assert "2.5.7 Dragging Movements" in result.data["risk_flags"][0]["wcag_criteria"]

    async def test_empty_risk_list_is_a_valid_success(self):
        """Um requisito sem risco real de acessibilidade -> lista vazia, nao falha."""
        with patch(
            "backend.src.agents.design_review.design_review.call_llm",
            new=AsyncMock(return_value="[]"),
        ):
            result = await run_design_review("Update the copyright year in the footer.")
        assert result.success is True
        assert result.data["risk_flags"] == []

    async def test_component_type_is_forwarded_when_provided(self):
        mock_llm = AsyncMock(return_value="[]")
        with patch("backend.src.agents.design_review.design_review.call_llm", new=mock_llm):
            await run_design_review("Add a settings panel.", component_type="modal")
        _, kwargs = mock_llm.call_args
        assert "modal" in kwargs["user_prompt"]

    async def test_no_component_type_still_succeeds(self):
        with patch(
            "backend.src.agents.design_review.design_review.call_llm",
            new=AsyncMock(return_value="[]"),
        ):
            result = await run_design_review("Add a settings panel.")
        assert result.success is True

    async def test_failure_on_invalid_json(self):
        with patch(
            "backend.src.agents.design_review.design_review.call_llm",
            new=AsyncMock(return_value="not json"),
        ):
            result = await run_design_review("Add a modal.")
        assert result.success is False
        assert result.error is not None

    async def test_failure_on_llm_exception(self):
        with patch(
            "backend.src.agents.design_review.design_review.call_llm",
            new=AsyncMock(side_effect=Exception("timeout")),
        ):
            result = await run_design_review("Add a modal.")
        assert result.success is False
        assert "timeout" in result.error

    async def test_requirement_text_is_truncated_for_very_long_input(self):
        long_text = "x" * 20_000
        mock_llm = AsyncMock(return_value="[]")
        with patch("backend.src.agents.design_review.design_review.call_llm", new=mock_llm):
            await run_design_review(long_text)
        _, kwargs = mock_llm.call_args
        assert len(kwargs["user_prompt"]) < 20_000


# ── Regressão: `id` numérico não pode derrubar a análise inteira ─────────────


def test_id_numerico_do_modelo_e_aceito():
    """Bug real (2026-08-30), achado delegando design_review via A2A.

    O SYSTEM_PROMPT pedia "keys: id, risk, ..." sem dizer que `id` e string e
    -- diferente dos outros agentes -- sem exemplo de saida. O modelo emitia
    `"id": 1` e a validacao derrubava a resposta inteira:

        1 validation error for DesignRiskFlag
        id  Input should be a valid string [input_value=1, input_type=int]

    Um identificador numerico e resposta legitima; recusar a analise por causa
    do TIPO de um rotulo desperdicia a chamada. O prompt ganhou exemplo, mas
    prompt nao garante formato -- a coercao e a rede de baixo.
    """
    from backend.src.shared.models import DesignRiskFlag

    flag = DesignRiskFlag(
        id=1,
        risk="Sem alternativa de teclado para o drag",
        wcag_criteria=["2.1.1 Keyboard"],
        severity="high",
        rationale="O requisito descreve reordenar so arrastando.",
        recommendation="Oferecer Ctrl+Setas com anuncio em live region.",
    )
    assert flag.id == "1"
    assert isinstance(flag.id, str)


def test_id_string_continua_intacto():
    from backend.src.shared.models import DesignRiskFlag

    flag = DesignRiskFlag(
        id="risk-1",
        risk="x",
        wcag_criteria=[],
        severity="low",
        rationale="y",
        recommendation="z",
    )
    assert flag.id == "risk-1"


def test_booleano_nao_vira_id():
    """`True` virando "True" seria mascarar um erro de verdade do modelo."""
    import pytest
    from pydantic import ValidationError

    from backend.src.shared.models import DesignRiskFlag

    with pytest.raises(ValidationError):
        DesignRiskFlag(
            id=True,
            risk="x",
            wcag_criteria=[],
            severity="low",
            rationale="y",
            recommendation="z",
        )
