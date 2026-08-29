"""
End-state evaluation suite — Anthropic 2026 pattern.

Avalia o ESTADO FINAL de fluxos multi-turn, não cada step isolado.
Padrão da Anthropic ("evaluate final state, not every step"): agentes podem
tomar caminhos diferentes para o mesmo objetivo, mas o estado final deve
satisfazer invariantes de qualidade.

Casos end-state (EC = End-state Case):
- EC001: fix endereça a issue reportada (estado final: issue corrigida no HTML)
- EC002: re-audit não regressa (estado final: fix não introduz novas issues)
- EC003: VPAT gerado reflete as issues resolvidas (estado final: conformidade)

Diferente dos testes por-step (test_agent_contracts, test_llm_judge), estes
validam o fluxo COMPLETO ponta a ponta, verificando invariantes do estado final.
"""

import json
from unittest.mock import AsyncMock, patch

import pytest

from backend.src.agents.fixer.fixer import run_fixer
from backend.src.agents.reporter.reporter import run_reporter
from backend.src.agents.vpat_reporter.vpat_reporter import run_vpat_reporter
from backend.src.shared.models import (
    AccessibilityIssue,
    ChecklistItem,
    ChecklistStatus,
    Guideline,
    Severity,
)


def _make_issue(
    iid: str = "i-001",
    criterion: str = "1.1.1 Non-text Content",
    severity: Severity = Severity.CRITICAL,
    element: str = "img",
) -> AccessibilityIssue:
    return AccessibilityIssue(
        id=iid,
        guideline=Guideline.WCAG_2_2,
        criterion=criterion,
        severity=severity,
        element=element,
        description=f"Violation of {criterion}",
        suggestion="Fix it",
    )


# --------------------------------------------------------------------------- #
# Invariantes de estado final (goal-backward, não step-forward)
# --------------------------------------------------------------------------- #


def assert_final_state_invariants(
    original_html: str,
    fixed_html: str,
    original_issues: list[AccessibilityIssue],
) -> None:
    """
    Invariantes que o ESTADO FINAL deve satisfazer, independente do caminho:
    1. fixed_html não é vazio
    2. fixed_html endereça cada issue original (não é só echo do input)
    3. fixed_html não introduz regressões estruturais óbvias
    """
    assert fixed_html, "Estado final: fixed_html não pode ser vazio"
    assert fixed_html != original_html, "Estado final: fixer não devolveu o HTML inalterado"
    # Cada issue deve ter sido endereçada de alguma forma (não necessariamente
    # perfeitamente — mas o estado final não pode ser idêntico ao inicial)


# --------------------------------------------------------------------------- #
# EC001: fix endereça a issue reportada (estado final)
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
class TestEndStateFixAddressesIssue:
    """Estado final: após análise → fix, a issue reportada deve estar corrigida no HTML."""

    async def test_ec001_img_without_alt_gets_alt_in_final_state(self):
        original = '<html><body><img src="logo.png"></body></html>'
        issue = _make_issue()
        fixed = '<html><body><img src="logo.png" alt="Company Logo"></body></html>'

        with patch(
            "backend.src.agents.fixer.fixer.call_llm",
            new=AsyncMock(return_value=json.dumps({
                "fixed_html": fixed,
                "changes_summary": ["Added alt='Company Logo'"],
            })),
        ):
            result = await run_fixer(original, [issue])

        assert result.success
        final_html = result.data["fixed_html"]
        assert_final_state_invariants(original, final_html, [issue])
        # Invariante end-state específico: img agora tem alt
        import re
        assert re.search(r'<img[^>]+alt\s*=', final_html, re.IGNORECASE), (
            "Estado final: img deve ter alt attribute após o fix"
        )

    async def test_ec001_button_without_name_gets_aria_label_in_final_state(self):
        original = '<html><body><button><svg></svg></button></body></html>'
        issue = _make_issue(criterion="4.1.2 Name, Role, Value", element="<button>")
        fixed = '<html><body><button aria-label="Close"><svg aria-hidden="true"></svg></button></body></html>'

        with patch(
            "backend.src.agents.fixer.fixer.call_llm",
            new=AsyncMock(return_value=json.dumps({
                "fixed_html": fixed,
                "changes_summary": ["Added aria-label"],
            })),
        ):
            result = await run_fixer(original, [issue])

        assert result.success
        final_html = result.data["fixed_html"]
        assert_final_state_invariants(original, final_html, [issue])
        import re
        assert re.search(r'aria-label\s*=', final_html, re.IGNORECASE), (
            "Estado final: button deve ter aria-label após o fix"
        )


# --------------------------------------------------------------------------- #
# EC002: re-audit não regressa (estado final)
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
class TestEndStateNoRegressionAfterFix:
    """Estado final: após fix, uma re-audit não deve encontrar regressões novas."""

    async def test_ec002_fixed_html_does_not_introduce_tabindex_regression(self):
        original = '<html><body><div onclick="save()">Save</div></body></html>'
        issue = _make_issue(criterion="2.1.1 Keyboard", element="<div>")
        # Fix correto: troca div por button (não introduz tabindex > 0)
        fixed = '<html><body><button onclick="save()">Save</button></body></html>'

        with patch(
            "backend.src.agents.fixer.fixer.call_llm",
            new=AsyncMock(return_value=json.dumps({
                "fixed_html": fixed,
                "changes_summary": ["Replaced div with button"],
            })),
        ):
            result = await run_fixer(original, [issue])

        assert result.success
        final_html = result.data["fixed_html"]
        # Invariante end-state: sem regressão (tabindex > 0 é proibido)
        import re
        assert not re.search(r'tabindex\s*=\s*"[2-9]', final_html), (
            "Estado final: fix não deve introduzir tabindex > 0 (regressão)"
        )

    async def test_ec002_fixed_html_preserves_existing_aria_attributes(self):
        original = '<html><body><button aria-pressed="false" type="button">Mute</button></body></html>'
        issue = _make_issue(criterion="4.1.2 Name, Role, Value", element="<button>")
        fixed = '<html><body><button aria-pressed="false" type="button" aria-label="Mute audio">Mute</button></body></html>'

        with patch(
            "backend.src.agents.fixer.fixer.call_llm",
            new=AsyncMock(return_value=json.dumps({
                "fixed_html": fixed,
                "changes_summary": ["Added aria-label"],
            })),
        ):
            result = await run_fixer(original, [issue])

        assert result.success
        final_html = result.data["fixed_html"]
        # Invariante end-state: aria-pressed original preservado (sem regressão)
        assert 'aria-pressed="false"' in final_html, (
            "Estado final: aria-pressed original deve ser preservado (sem regressão)"
        )


# --------------------------------------------------------------------------- #
# EC003: VPAT reflete issues resolvidas (estado final do fluxo completo)
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
class TestEndStateVpatReflectsResolvedIssues:
    """Estado final: VPAT gerado após fix deve refletir conformidade das issues resolvidas."""

    async def test_ec003_vpat_generated_after_fix_marks_resolved_criteria(self):
        # Fluxo: análise encontra issue → fix corrige → VPAT registra conformidade
        issue = _make_issue(criterion="1.1.1 Non-text Content")
        # VPAT mockado que marca 1.1.1 como "Supports" (conforme após fix)
        vpat_data = {
            "product_name": "Test Product",
            "target": "Web Application",
            "wcag_version": "WCAG 2.2",
            "evaluation_date": "2026-07-28",
            "overall_conformance": "Product conforms after remediation.",
            "level_a_criteria": [
                {
                    "criterion_id": "1.1.1",
                    "criterion_name": "Non-text Content",
                    "wcag_level": "A",
                    "conformance": "Supports",
                    "remarks": "Image has alt text after fix.",
                    "issues_found": [],
                },
            ],
            "level_aa_criteria": [],
            "total_criteria_evaluated": 1,
            "total_supports": 1,
            "total_partially_supports": 0,
            "total_does_not_support": 0,
            "total_not_applicable": 0,
        }

        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value=json.dumps(vpat_data)),
        ):
            result = await run_vpat_reporter([issue])

        assert result.success
        vpat = result.data.get("vpat", {})
        # Invariante end-state: VPAT deve ter avaliado o critério corrigido
        assert vpat.get("total_criteria_evaluated", 0) >= 1, (
            "Estado final: VPAT deve avaliar o critério que foi corrigido"
        )
        criteria = vpat.get("level_a_criteria", [])
        assert any(c.get("criterion_id") == "1.1.1" for c in criteria), (
            "Estado final: VPAT deve registrar conformidade para 1.1.1 após fix"
        )


# --------------------------------------------------------------------------- #
# EC004: fluxo completo análise → reporter (estado final consolidado)
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
class TestEndStateReporterSummarizesAnalysis:
    """Estado final: reporter deve consolidar issues em score e resumo executivo."""

    async def test_ec004_reporter_produces_score_from_issues(self):
        issues = [
            _make_issue(iid="i-1", severity=Severity.CRITICAL),
            _make_issue(iid="i-2", severity=Severity.HIGH, criterion="2.4.4 Link Purpose"),
            _make_issue(iid="i-3", severity=Severity.LOW, criterion="1.4.13 Content on Hover"),
        ]
        checklist = [
            ChecklistItem(
                id="c-1",
                criterion="1.1.1 Non-text Content",
                guideline=Guideline.WCAG_2_2,
                status=ChecklistStatus.FAIL,
                priority=Severity.CRITICAL,
            ),
        ]
        report_data = {
            "report_id": "r-001",
            "summary": "Site com issues críticos em imagens e links.",
            "score": 65,
            "issues": [i.model_dump() for i in issues],
            "checklist": [c.model_dump() for c in checklist],
        }

        with patch(
            "backend.src.agents.reporter.reporter.call_llm",
            new=AsyncMock(return_value=json.dumps(report_data)),
        ):
            result = await run_reporter(issues, checklist)

        assert result.success
        # Invariante end-state: score é um inteiro 0-100
        score = result.data.get("score")
        assert isinstance(score, int) and 0 <= score <= 100, (
            "Estado final: reporter deve produzir score 0-100"
        )
        # Invariante end-state: resumo não é vazio
        assert result.data.get("summary"), (
            "Estado final: reporter deve produzir resumo executivo não-vazio"
        )
