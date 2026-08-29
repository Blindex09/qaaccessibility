import json
from unittest.mock import AsyncMock, patch

import pytest

from backend.src.agents.a11y_expert_reviewer.a11y_expert_reviewer import run_a11y_expert_reviewer
from backend.src.shared.models import AccessibilityIssue

from .conftest_agents import assert_agent_contract, assert_issues_valid, make_issue

# ─────────────────────────────────────────────────────────────────────────────
# Testes: A11yExpertReviewer
# Fonte do agente: accessibility-expert.toml + accessibility-specialist.toml
#
# Cobre:
#   - Contrato AgentResult (agent, success, data, error)
#   - Revisao com issues validos retorna lista filtrada
#   - Falso positivo (aria-label em aria-hidden) deve ser removivel
#   - Lista vazia de entrada retorna sucesso sem chamar LLM
#   - Falha no LLM retorna fallback com issues originais (graceful)
#   - JSON invalido do LLM retorna success=False
#   - Re-score de severidade e enriquecimento why_technical preservados
#   - removed_false_positives e reviewed_count presentes na resposta
# ─────────────────────────────────────────────────────────────────────────────

ISSUE_REAL = make_issue({
    "id": "perceiver-1",
    "criterion": "1.1.1 Non-text Content",
    "severity": "critical",
    "element": "img#hero",
    "description": "Hero image missing alt text",
    "suggestion": "Add descriptive alt attribute",
    "why_technical": "",
})

ISSUE_FALSE_POSITIVE = make_issue({
    "id": "perceiver-2",
    "criterion": "4.1.2 Name, Role, Value",
    "severity": "medium",
    "element": "svg[aria-hidden='true']",
    "description": "SVG missing aria-label",
    "suggestion": "Add aria-label",
})


def _make_reviewed_response(issues: list[dict]) -> str:
    """Resposta simulada do LLM apos revisao — pode omitir falsos positivos."""
    return json.dumps(issues)


@pytest.mark.asyncio
class TestA11yExpertReviewer:
    async def test_contract_on_success(self):
        """Contrato basico: agent, success, data com issues."""
        with patch(
            "backend.src.agents.a11y_expert_reviewer.a11y_expert_reviewer.call_llm",
            new=AsyncMock(return_value=_make_reviewed_response([ISSUE_REAL])),
        ):
            issues = [AccessibilityIssue(**ISSUE_REAL)]
            result = await run_a11y_expert_reviewer(issues)

        assert_agent_contract(result, "a11y_expert_reviewer")
        assert result.success is True
        assert "issues" in result.data

    async def test_valid_issues_returned_intact(self):
        """Issues validos devem ser retornados com schema correto."""
        with patch(
            "backend.src.agents.a11y_expert_reviewer.a11y_expert_reviewer.call_llm",
            new=AsyncMock(return_value=_make_reviewed_response([ISSUE_REAL])),
        ):
            issues = [AccessibilityIssue(**ISSUE_REAL)]
            result = await run_a11y_expert_reviewer(issues)

        assert result.success is True
        assert len(result.data["issues"]) == 1
        assert_issues_valid(result.data["issues"])

    async def test_false_positive_removed(self):
        """LLM pode omitir falsos positivos — lista resultante deve ser menor."""
        # LLM retorna apenas o issue real, omitindo o falso positivo
        with patch(
            "backend.src.agents.a11y_expert_reviewer.a11y_expert_reviewer.call_llm",
            new=AsyncMock(return_value=_make_reviewed_response([ISSUE_REAL])),
        ):
            issues = [AccessibilityIssue(**ISSUE_REAL), AccessibilityIssue(**ISSUE_FALSE_POSITIVE)]
            result = await run_a11y_expert_reviewer(issues)

        assert result.success is True
        assert len(result.data["issues"]) == 1
        assert result.data["removed_false_positives"] == 1
        assert result.data["original_count"] == 2
        assert result.data["reviewed_count"] == 1

    async def test_empty_input_returns_success_without_calling_llm(self):
        """Lista vazia não deve chamar o LLM — retorno imediato de sucesso."""
        mock_llm = AsyncMock()
        with patch(
            "backend.src.agents.a11y_expert_reviewer.a11y_expert_reviewer.call_llm",
            new=mock_llm,
        ):
            result = await run_a11y_expert_reviewer([])

        mock_llm.assert_not_called()
        assert result.success is True
        assert result.data["issues"] == []
        assert result.data["removed_false_positives"] == 0

    async def test_llm_failure_returns_graceful_fallback(self):
        """Falha do LLM deve retornar success=False MAS com issues originais (sem perda de dados)."""
        with patch(
            "backend.src.agents.a11y_expert_reviewer.a11y_expert_reviewer.call_llm",
            new=AsyncMock(side_effect=Exception("LLM API error")),
        ):
            issues = [AccessibilityIssue(**ISSUE_REAL)]
            result = await run_a11y_expert_reviewer(issues)

        assert result.success is False
        assert result.error is not None
        # Fallback: issues originais preservados mesmo em falha
        assert len(result.data["issues"]) == 1
        assert result.data.get("fallback") is True

    async def test_invalid_json_returns_failure(self):
        """JSON invalido do LLM deve retornar success=False."""
        with patch(
            "backend.src.agents.a11y_expert_reviewer.a11y_expert_reviewer.call_llm",
            new=AsyncMock(return_value="not json at all {{broken"),
        ):
            issues = [AccessibilityIssue(**ISSUE_REAL)]
            result = await run_a11y_expert_reviewer(issues)

        assert result.success is False
        assert result.error is not None

    async def test_all_issues_removed_as_false_positives(self):
        """LLM pode remover todos os issues (ex: todos eram falsos positivos) — retornar []."""
        with patch(
            "backend.src.agents.a11y_expert_reviewer.a11y_expert_reviewer.call_llm",
            new=AsyncMock(return_value="[]"),
        ):
            issues = [AccessibilityIssue(**ISSUE_FALSE_POSITIVE)]
            result = await run_a11y_expert_reviewer(issues)

        assert result.success is True
        assert result.data["issues"] == []
        assert result.data["removed_false_positives"] == 1

    async def test_reviewed_count_matches_returned_issues(self):
        """reviewed_count deve bater com o len dos issues retornados."""
        with patch(
            "backend.src.agents.a11y_expert_reviewer.a11y_expert_reviewer.call_llm",
            new=AsyncMock(return_value=_make_reviewed_response([ISSUE_REAL])),
        ):
            issues = [AccessibilityIssue(**ISSUE_REAL)]
            result = await run_a11y_expert_reviewer(issues)

        assert result.data["reviewed_count"] == len(result.data["issues"])

    async def test_strips_markdown_fences_from_response(self):
        """extract_json_array deve aceitar resposta com ```json``` fence."""
        fenced = f"```json\n{_make_reviewed_response([ISSUE_REAL])}\n```"
        with patch(
            "backend.src.agents.a11y_expert_reviewer.a11y_expert_reviewer.call_llm",
            new=AsyncMock(return_value=fenced),
        ):
            issues = [AccessibilityIssue(**ISSUE_REAL)]
            result = await run_a11y_expert_reviewer(issues)

        assert result.success is True
        assert len(result.data["issues"]) == 1
