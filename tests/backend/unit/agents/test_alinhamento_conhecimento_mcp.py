"""Comportamento dos agentes alinhado ao conhecimento do repositório mcp (web-accessibility).

Divergências reais achadas em 2026-10-17 e corrigidas: o gerador de testes tratava alt vazio como falha e
exigia uma técnica de foco específica; o relator comemorava e chamava de "totalmente acessível" um resultado
sem achados, o que o próprio mcp (e o CLAUDE.md, regra 11) proíbe: verde não é acessível.
"""

import json
from unittest.mock import AsyncMock, patch

import pytest

from backend.src.agents.reporter import reporter
from backend.src.agents.test_generator import test_generator
from backend.src.shared.models import AccessibilityIssue

from .conftest_agents import make_issue

_ISSUE = AccessibilityIssue(
    **make_issue(
        {
            "id": "x-1",
            "criterion": "4.1.2 Name, Role, Value",
            "element": "nav button",
            "description": "Submenu button without expanded state.",
            "suggestion": "Add aria-expanded.",
        }
    )
)


class TestGeneratedTestsFollowTheKnowledge:
    def test_empty_alt_is_valid_so_the_test_must_not_demand_a_non_empty_alt(self):
        prompt = test_generator.SYSTEM_PROMPT
        assert 'check img.getAttribute("alt") not null/empty' not in prompt
        assert 'alt="" is a deliberate "decorative" mark and is valid' in prompt

    def test_route_focus_is_asserted_by_outcome_not_by_one_technique(self):
        prompt = test_generator.SYSTEM_PROMPT
        assert 'verify focus moves to h1[tabindex="-1"] on route change' not in prompt
        assert 'Do not require h1[tabindex="-1"] specifically' in prompt

    @pytest.mark.parametrize(
        "fragment",
        [
            "Dialog: opened by keyboard",
            "do not assert aria-modal on it",
            "A navigation submenu is a disclosure, not a menu",
            "never assert\n  role=\"menu\" or menuitem for it",
            "A green axe run is not proof of accessibility",
            "Target size",
            "Form errors: submit by keyboard",
        ],
    )
    def test_behavior_contracts_reach_both_the_single_and_the_batch_prompt(self, fragment):
        assert fragment in test_generator.SYSTEM_PROMPT
        assert fragment in test_generator.SYSTEM_PROMPT_LOTE

    @pytest.mark.asyncio
    async def test_batch_call_sends_the_contracts_with_the_issues(self):
        model = AsyncMock(return_value=[])
        with patch.object(test_generator, "call_llm_structured", model):
            await test_generator._gerar_testes_do_lote([_ISSUE], "https://example.com")
        assert "Behavior contracts" in model.call_args.kwargs["system_prompt"]
        assert "nav button" in model.call_args.kwargs["user_prompt"]


class TestReportDoesNotCertify:
    def test_report_prompt_never_celebrates_an_empty_result_as_accessible(self):
        prompt = reporter.SYSTEM_PROMPT
        assert "celebrate" not in prompt
        assert "100 = fully accessible" not in prompt
        assert "not a certification" in prompt
        assert "never present the score as a conformance verdict" in prompt

    @pytest.mark.asyncio
    async def test_empty_issue_list_reaches_the_model_with_the_no_certification_rule(self):
        model = AsyncMock(return_value=json.dumps({"summary": "Nenhuma violação confirmada no escopo avaliado.", "score": 100}))
        with patch.object(reporter, "call_llm", model):
            result = await reporter.run_reporter([], [])
        assert result.success
        assert "not a certification" in model.call_args.kwargs["system_prompt"]
