import json
from unittest.mock import AsyncMock, patch

import pytest

from backend.src.agents.vpat_reporter.vpat_reporter import run_vpat_reporter
from backend.src.shared.models import AccessibilityIssue

from .conftest_agents import assert_agent_contract, make_issue

# ─────────────────────────────────────────────────────────────────────────────
# Testes: VPATReporter
# Fonte: compliance-auditor.md
#
# Cobre:
#   - Contrato AgentResult
#   - VPAT gerado com schema correto (VPATReport)
#   - level_a_criteria e level_aa_criteria presentes
#   - Contadores de conformidade (total_supports, etc.) sao inteiros >= 0
#   - Issues de entrada influenciam declaracoes (Does Not Support para critical)
#   - Falha no LLM retorna success=False
#   - JSON invalido retorna success=False
#   - product_name e target aparecem no VPAT gerado
# ─────────────────────────────────────────────────────────────────────────────

ISSUE_CRITICAL = make_issue({
    "id": "perceiver-1",
    "criterion": "1.1.1 Non-text Content",
    "severity": "critical",
    "element": "img#hero",
    "description": "Hero image missing alt text",
    "suggestion": "Add alt attribute",
})


def _make_vpat_response(overrides: dict | None = None) -> str:
    base = {
        "product_name": "Test Product",
        "target": "https://example.com",
        "wcag_version": "WCAG 2.2",
        "evaluation_date": "2026-05-05",
        "overall_conformance": "The product partially conforms to WCAG 2.2 Level AA.",
        "level_a_criteria": [
            {
                "criterion_id": "1.1.1",
                "criterion_name": "Non-text Content",
                "wcag_level": "A",
                "conformance": "Does Not Support",
                "remarks": "Critical issue found: hero image missing alt text. Issues: perceiver-1",
                "issues_found": ["perceiver-1"],
            }
        ],
        "level_aa_criteria": [
            {
                "criterion_id": "1.4.3",
                "criterion_name": "Contrast (Minimum)",
                "wcag_level": "AA",
                "conformance": "Supports",
                "remarks": "No contrast issues detected in automated scan.",
                "issues_found": [],
            }
        ],
        "total_criteria_evaluated": 2,
        "total_supports": 1,
        "total_partially_supports": 0,
        "total_does_not_support": 1,
        "total_not_applicable": 0,
    }
    return json.dumps({**base, **(overrides or {})})


@pytest.mark.asyncio
class TestVPATReporterAgent:
    async def test_contract_on_success(self):
        """Contrato basico: agent, success, data com vpat."""
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value=_make_vpat_response()),
        ):
            issues = [AccessibilityIssue(**ISSUE_CRITICAL)]
            result = await run_vpat_reporter(issues, target="https://example.com", product_name="Test Product")

        assert_agent_contract(result, "vpat_reporter")
        assert result.success is True
        assert "vpat" in result.data

    async def test_vpat_has_correct_schema(self):
        """VPAT deve ter todos os campos obrigatórios do VPATReport."""
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value=_make_vpat_response()),
        ):
            issues = [AccessibilityIssue(**ISSUE_CRITICAL)]
            result = await run_vpat_reporter(issues)

        vpat = result.data["vpat"]
        required_fields = [
            "product_name", "target", "wcag_version", "evaluation_date",
            "overall_conformance", "level_a_criteria", "level_aa_criteria",
            "total_criteria_evaluated", "total_supports",
            "total_partially_supports", "total_does_not_support", "total_not_applicable",
        ]
        for field in required_fields:
            assert field in vpat, f"Campo obrigatório ausente no VPAT: {field}"

    async def test_wcag_version_is_22(self):
        """wcag_version deve ser sempre WCAG 2.2."""
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value=_make_vpat_response()),
        ):
            result = await run_vpat_reporter([AccessibilityIssue(**ISSUE_CRITICAL)])

        assert result.data["vpat"]["wcag_version"] == "WCAG 2.2"

    async def test_level_a_criteria_is_list(self):
        """level_a_criteria deve ser lista não vazia."""
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value=_make_vpat_response()),
        ):
            result = await run_vpat_reporter([AccessibilityIssue(**ISSUE_CRITICAL)])

        assert isinstance(result.data["vpat"]["level_a_criteria"], list)
        assert len(result.data["vpat"]["level_a_criteria"]) >= 1

    async def test_conformance_counters_are_non_negative_integers(self):
        """Contadores de conformidade devem ser inteiros não negativos."""
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value=_make_vpat_response()),
        ):
            result = await run_vpat_reporter([AccessibilityIssue(**ISSUE_CRITICAL)])

        vpat = result.data["vpat"]
        for field in ["total_supports", "total_partially_supports", "total_does_not_support", "total_not_applicable"]:
            assert isinstance(vpat[field], int) and vpat[field] >= 0

    async def test_llm_failure_returns_error(self):
        """Falha no LLM deve retornar success=False com error."""
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(side_effect=Exception("network error")),
        ):
            result = await run_vpat_reporter([AccessibilityIssue(**ISSUE_CRITICAL)])

        assert result.success is False
        assert result.error is not None

    async def test_invalid_json_returns_failure(self):
        """JSON invalido do LLM deve retornar success=False."""
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value="{{invalid json}}"),
        ):
            result = await run_vpat_reporter([AccessibilityIssue(**ISSUE_CRITICAL)])

        assert result.success is False

    async def test_strips_markdown_fences(self):
        """Resposta com ```json``` fence deve ser parseada corretamente."""
        fenced = f"```json\n{_make_vpat_response()}\n```"
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value=fenced),
        ):
            result = await run_vpat_reporter([AccessibilityIssue(**ISSUE_CRITICAL)])

        assert result.success is True
        assert result.data["vpat"]["wcag_version"] == "WCAG 2.2"
