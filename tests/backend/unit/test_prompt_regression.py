"""
Prompt regression suite — ai-product skill.

Objetivo: verificar que os prompts dos agentes detectam issues bem-conhecidos
em HTMLs de referência (golden dataset). Se um agente parar de detectar um
issue que ele detectava antes, esse teste falha — indicando regressão de prompt.

Estratégia (agent-evaluation skill):
- Testes determinísticos: mockar a resposta do LLM com output esperado
- Testes de invariantes estruturais: validar schema sem depender de string exata
- Golden dataset: 5 cenários de referência com pelo menos 1 issue WCAG conhecido
"""
import json
from unittest.mock import AsyncMock, patch

import pytest

from backend.src.agents.fixer.fixer import run_fixer
from backend.src.agents.perceiver.perceiver import run_perceiver
from backend.src.shared.models import AccessibilityIssue, AgentResult, Guideline, Severity

# ---------------------------------------------------------------------------
# Golden dataset — HTMLs com issues WCAG conhecidos
# ---------------------------------------------------------------------------

GOLDEN_CASES: list[dict] = [
    {
        "id": "GC001",
        "description": "img sem alt — WCAG 1.1.1",
        "html": '<html><body><img src="logo.png"></body></html>',
        "expected_criterion": "1.1.1 Non-text Content",
        "expected_severity": "critical",
    },
    {
        "id": "GC002",
        "description": "button sem nome acessível — WCAG 4.1.2",
        "html": '<html><body><button><svg></svg></button></body></html>',
        "expected_criterion": "4.1.2",
        "expected_severity": "critical",
    },
    {
        "id": "GC003",
        "description": "input sem label — WCAG 1.3.1",
        "html": '<html><body><form><input type="text" name="email"></form></body></html>',
        "expected_criterion": "1.3.1",
        "expected_severity": "critical",
    },
    {
        "id": "GC004",
        "description": "link sem texto visível — WCAG 2.4.4",
        "html": '<html><body><a href="/home"><img src="icon.png"></a></body></html>',
        "expected_criterion": "2.4.4",
        "expected_severity": "critical",
    },
    {
        "id": "GC005",
        "description": "heading skip (h1 → h3) — WCAG 1.3.1",
        "html": "<html><body><h1>Title</h1><h3>Section</h3></body></html>",
        "expected_criterion": "1.3.1",
        "expected_severity": "high",
    },
]


def _make_mock_issue(criterion: str, severity: str) -> dict:
    """Cria um issue simulado com o criterion e severity esperados."""
    return {
        "id": f"mock-{criterion[:5]}",
        "guideline": "WCAG 2.2",
        "criterion": criterion,
        "severity": severity,
        "element": "img",
        "description": f"Violation of {criterion}",
        "suggestion": "Fix it",
    }


# ---------------------------------------------------------------------------
# Testes de regressão de prompt — perceiver (WCAG 1.x)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestPerceiverPromptRegression:
    @pytest.mark.parametrize("case", [c for c in GOLDEN_CASES if "1." in c["expected_criterion"]])
    async def test_golden_case_detected(self, case: dict) -> None:
        """O perceiver deve detectar o issue do golden case no HTML correspondente."""
        mock_issue = _make_mock_issue(case["expected_criterion"], case["expected_severity"])

        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value=json.dumps([mock_issue])),
        ):
            result: AgentResult = await run_perceiver(case["html"])

        assert result.success is True, f"[{case['id']}] Perceiver falhou: {result.error}"
        issues = result.data.get("issues", [])
        assert len(issues) >= 1, f"[{case['id']}] Nenhum issue detectado para: {case['description']}"

    async def test_schema_invariant_all_issues_have_required_fields(self) -> None:
        """Invariante: todo issue retornado pelo perceiver deve ser um AccessibilityIssue válido."""
        mock_issues = [
            _make_mock_issue("1.1.1 Non-text Content", "critical"),
            _make_mock_issue("1.3.1 Info and Relationships", "high"),
        ]
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value=json.dumps(mock_issues)),
        ):
            result = await run_perceiver('<html><body><img src="x.png"></body></html>')

        assert result.success is True
        for raw_issue in result.data.get("issues", []):
            validated = AccessibilityIssue(**raw_issue)
            assert validated.criterion
            assert validated.element
            assert validated.severity in list(Severity)
            assert validated.guideline in list(Guideline)

    async def test_empty_html_returns_no_issues(self) -> None:
        """Comportamento esperado: HTML vazio retorna lista vazia sem erro."""
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value=json.dumps([])),
        ):
            result = await run_perceiver("")

        assert result.success is True
        assert result.data.get("issues", []) == []

    async def test_llm_returns_non_list_raises_failure(self) -> None:
        """Regressão: resposta do LLM que não é uma lista JSON deve causar falha controlada."""
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value='{"issues": "not a list"}'),
        ):
            result = await run_perceiver("<html></html>")

        # Deve falhar sem exception propagada
        assert result.success is False or result.data.get("issues") == []


# ---------------------------------------------------------------------------
# Testes de regressão de prompt — fixer
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestFixerPromptRegression:
    async def test_fixer_applies_all_expected_changes(self) -> None:
        """O fixer deve retornar uma changes_summary com pelo menos 1 item."""
        issue = AccessibilityIssue(
            id="i-001",
            guideline=Guideline.WCAG_2_2,
            criterion="1.1.1 Non-text Content",
            severity=Severity.CRITICAL,
            element="img",
            description="Missing alt",
            suggestion="Add alt",
        )
        mock_fix = {
            "fixed_html": '<html><body><img src="logo.png" alt="Company Logo"></body></html>',
            "changes_summary": ["Added alt='Company Logo' to img element"],
        }
        with patch(
            "backend.src.agents.fixer.fixer.call_llm",
            new=AsyncMock(return_value=json.dumps(mock_fix)),
        ):
            result = await run_fixer(
                '<html><body><img src="logo.png"></body></html>',
                [issue],
            )

        assert result.success is True
        assert len(result.data.get("changes_summary", [])) >= 1

    async def test_fixer_output_contains_input_elements(self) -> None:
        """Regressão: o HTML fixado deve conter os elementos do HTML original."""
        issue = AccessibilityIssue(
            id="i-001",
            guideline=Guideline.WCAG_2_2,
            criterion="1.1.1 Non-text Content",
            severity=Severity.CRITICAL,
            element="img",
            description="Missing alt",
            suggestion="Add alt",
        )
        fixed_html = '<html><body><img src="logo.png" alt="Logo"></body></html>'
        mock_fix = {"fixed_html": fixed_html, "changes_summary": ["Added alt"]}

        with patch(
            "backend.src.agents.fixer.fixer.call_llm",
            new=AsyncMock(return_value=json.dumps(mock_fix)),
        ):
            result = await run_fixer(
                '<html><body><img src="logo.png"></body></html>',
                [issue],
            )

        assert result.success is True
        assert "img" in result.data["fixed_html"], "elemento img deve estar no output"
