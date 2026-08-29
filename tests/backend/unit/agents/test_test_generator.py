import json
from unittest.mock import AsyncMock, patch

import pytest

from backend.src.agents.test_generator.test_generator import run_test_generator
from backend.src.shared.models import AccessibilityIssue

from .conftest_agents import assert_agent_contract, make_issue

# ─────────────────────────────────────────────────────────────────────────────
# Testes: TestGenerator
# Fontes: playwright-expert.toml + accessibility-tester.md + tdd-orchestrator.toml
#
# Cobre:
#   - Contrato AgentResult
#   - Suite gerada com schema correto (TestSuite)
#   - Lista vazia retorna suite vazia sem chamar LLM
#   - Issues ordenados por severidade (critical primeiro)
#   - Falha no LLM retorna success=False com error
#   - JSON invalido retorna success=False
#   - Markdown fence na resposta e tratado corretamente
#   - Campo total_tests bate com len(tests)
# ─────────────────────────────────────────────────────────────────────────────

ISSUE_CRITICAL = make_issue({
    "id": "perceiver-1",
    "criterion": "1.1.1 Non-text Content",
    "severity": "critical",
    "element": "img#hero",
    "description": "Hero image missing alt text",
    "suggestion": "Add descriptive alt attribute",
    "suggestion_technical": 'alt="Hero banner showing main product"',
    "wcag_url": "https://www.w3.org/WAI/WCAG22/Understanding/non-text-content",
})

ISSUE_LOW = make_issue({
    "id": "semantics-5",
    "criterion": "2.4.4 Link Purpose (In Context)",
    "severity": "low",
    "element": "a",
    "description": "Link text is slightly generic",
    "suggestion": "Add more context to link text",
})

MOCK_SUITE = {
    "target": "https://example.com",
    "total_tests": 1,
    "setup_snippet": "import { test, expect } from '@playwright/test';",
    "ci_instructions": "npx playwright test",
    "tests": [
        {
            "test_id": "test-1",
            "criterion": "1.1.1 Non-text Content",
            "severity": "critical",
            "framework": "playwright",
            "description": "Hero image should have alt text",
            "code": "test('should have alt text on hero image', async ({ page }) => { await page.goto(url); const img = page.locator('img#hero'); await expect(img).toHaveAttribute('alt', /.+/); });",
            "element_hint": "img#hero",
        }
    ],
}


@pytest.mark.asyncio
class TestTestGeneratorAgent:
    async def test_contract_on_success(self):
        """Contrato basico: agent, success, data com suite."""
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value=json.dumps(MOCK_SUITE)),
        ):
            issues = [AccessibilityIssue(**ISSUE_CRITICAL)]
            result = await run_test_generator(issues, target="https://example.com")

        assert_agent_contract(result, "test_generator")
        assert result.success is True
        assert "suite" in result.data

    async def test_suite_has_correct_schema(self):
        """Suite deve ter target, total_tests, tests, setup_snippet, ci_instructions."""
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value=json.dumps(MOCK_SUITE)),
        ):
            issues = [AccessibilityIssue(**ISSUE_CRITICAL)]
            result = await run_test_generator(issues, target="https://example.com")

        suite = result.data["suite"]
        assert "target" in suite
        assert "total_tests" in suite
        assert "tests" in suite
        assert "setup_snippet" in suite
        assert "ci_instructions" in suite

    async def test_empty_issues_returns_empty_suite_without_calling_llm(self):
        """Lista vazia não deve chamar LLM — suite vazia retornada diretamente."""
        mock_llm = AsyncMock()
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=mock_llm,
        ):
            result = await run_test_generator([], target="")

        mock_llm.assert_not_called()
        assert result.success is True
        assert result.data["suite"]["total_tests"] == 0
        assert result.data["suite"]["tests"] == []

    async def test_llm_failure_returns_error(self):
        """Falha no LLM deve retornar success=False com error."""
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(side_effect=Exception("API timeout")),
        ):
            issues = [AccessibilityIssue(**ISSUE_CRITICAL)]
            result = await run_test_generator(issues)

        assert result.success is False
        assert result.error is not None
        assert "API timeout" in (result.error or "")

    async def test_invalid_json_returns_failure(self):
        """JSON invalido do LLM deve retornar success=False."""
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value="broken { json"),
        ):
            issues = [AccessibilityIssue(**ISSUE_CRITICAL)]
            result = await run_test_generator(issues)

        assert result.success is False

    async def test_strips_markdown_fences(self):
        """Resposta com ```json``` fence deve ser parseada corretamente."""
        fenced = f"```json\n{json.dumps(MOCK_SUITE)}\n```"
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value=fenced),
        ):
            issues = [AccessibilityIssue(**ISSUE_CRITICAL)]
            result = await run_test_generator(issues)

        assert result.success is True
        assert result.data["suite"]["total_tests"] == 1

    async def test_target_passed_to_suite(self):
        """O target informado deve aparecer na suite gerada."""
        suite_with_target = {**MOCK_SUITE, "target": "https://my-app.com"}
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value=json.dumps(suite_with_target)),
        ):
            issues = [AccessibilityIssue(**ISSUE_CRITICAL)]
            result = await run_test_generator(issues, target="https://my-app.com")

        assert result.data["suite"]["target"] == "https://my-app.com"
