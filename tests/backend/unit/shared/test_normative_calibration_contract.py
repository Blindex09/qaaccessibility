from unittest.mock import AsyncMock, patch

import pytest

from backend.src.agents.a11y_expert_reviewer.a11y_expert_reviewer import SYSTEM_PROMPT as REVIEW_PROMPT
from backend.src.agents.wcag_semantics import wcag_semantics
from backend.src.shared.normative_calibration import NORMATIVE_CALIBRATION


def test_reviewer_and_specialist_share_normative_not_pattern_only_contract():
    assert REVIEW_PROMPT.endswith(NORMATIVE_CALIBRATION)
    assert wcag_semantics.SYSTEM_PROMPT.endswith(NORMATIVE_CALIBRATION)


@pytest.mark.asyncio
async def test_squad_roles_also_receive_the_shared_normative_contract():
    from backend.src.agents.squad.role_agents import _runner
    from backend.src.agents.squad.roles import SquadRole

    model = AsyncMock(return_value={"summary": "Revisão limitada", "handoff": {}})
    with patch.object(_runner, "call_llm_structured", model):
        await _runner.run_role(role=SquadRole.QA_LEAD, system_prompt="QA", context={"observed_structure": {"headings": []}})
    assert model.call_args.kwargs["system_prompt"].endswith(NORMATIVE_CALIBRATION)
    assert '"headings": []' in model.call_args.kwargs["user_prompt"]


@pytest.mark.asyncio
async def test_specialist_passes_calibrated_contract_to_model_without_keyword_filter():
    model = AsyncMock(return_value=[])
    html = '<html lang="en"><title>Example</title><body><p>Short notice without a heading.</p></body></html>'
    with patch.object(wcag_semantics, "call_llm_structured", model):
        result = await wcag_semantics.run_wcag_semantics(html)
    assert result.success
    assert result.data["issues"] == []
    assert model.call_args.kwargs["system_prompt"].endswith(NORMATIVE_CALIBRATION)
    assert html in model.call_args.kwargs["user_prompt"]
