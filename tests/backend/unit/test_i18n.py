"""
Testes unitarios para o modulo de i18n (criteria_pt.py).
Regras:
- Zero emojis em logger
- Imports no topo
- Testa translate_issue e translate_issues
"""

from backend.src.shared.i18n.criteria_pt import translate_issue, translate_issues
from backend.src.shared.models import AccessibilityIssue, Guideline, Severity


def _make_issue(criterion: str, severity: Severity) -> AccessibilityIssue:
    return AccessibilityIssue(
        id="test-1",
        guideline=Guideline.WCAG_2_2,
        criterion=criterion,
        severity=severity,
        element="<img src='logo.png'>",
        description="Test description",
        suggestion="Test suggestion",
    )


class TestTranslateIssue:
    def test_known_criterion_gets_translated(self):
        issue = _make_issue("1.1.1 Non-text Content", Severity.CRITICAL)
        result = translate_issue(issue)
        assert result.criterion_pt == "1.1.1 Conteúdo Não Textual"

    def test_known_criterion_wcag2x(self):
        issue = _make_issue("2.4.2 Page Titled", Severity.HIGH)
        result = translate_issue(issue)
        assert result.criterion_pt == "2.4.2 Página com Título"

    def test_known_criterion_wcag3x(self):
        issue = _make_issue("3.3.8 Accessible Authentication (Minimum)", Severity.CRITICAL)
        result = translate_issue(issue)
        assert result.criterion_pt == "3.3.8 Autenticação Acessível (Mínima)"

    def test_known_criterion_wcag4x(self):
        issue = _make_issue("4.1.2 Name, Role, Value", Severity.HIGH)
        result = translate_issue(issue)
        assert result.criterion_pt == "4.1.2 Nome, Função e Valor"

    def test_unknown_criterion_falls_back_to_original(self):
        issue = _make_issue("9.9.9 Unknown Criterion", Severity.LOW)
        result = translate_issue(issue)
        assert result.criterion_pt == "9.9.9 Unknown Criterion"

    def test_severity_critical_translated(self):
        issue = _make_issue("1.1.1 Non-text Content", Severity.CRITICAL)
        result = translate_issue(issue)
        assert result.severity_pt == "Crítica"

    def test_severity_high_translated(self):
        issue = _make_issue("1.1.1 Non-text Content", Severity.HIGH)
        result = translate_issue(issue)
        assert result.severity_pt == "Alta"

    def test_severity_medium_translated(self):
        issue = _make_issue("1.1.1 Non-text Content", Severity.MEDIUM)
        result = translate_issue(issue)
        assert result.severity_pt == "Média"

    def test_severity_low_translated(self):
        issue = _make_issue("1.1.1 Non-text Content", Severity.LOW)
        result = translate_issue(issue)
        assert result.severity_pt == "Baixa"

    def test_original_criterion_preserved(self):
        """campo criterion original não deve ser alterado."""
        issue = _make_issue("1.1.1 Non-text Content", Severity.HIGH)
        result = translate_issue(issue)
        assert result.criterion == "1.1.1 Non-text Content"

    def test_original_severity_preserved(self):
        """campo severity original não deve ser alterado."""
        issue = _make_issue("1.1.1 Non-text Content", Severity.CRITICAL)
        result = translate_issue(issue)
        assert result.severity == Severity.CRITICAL

    def test_criterion_with_only_code(self):
        """Criterio que contem apenas o código numerico deve ser traduzido."""
        issue = _make_issue("1.3.1", Severity.MEDIUM)
        result = translate_issue(issue)
        assert result.criterion_pt == "1.3.1 Informações e Relações"


class TestTranslateIssues:
    def test_empty_list_returns_empty(self):
        assert translate_issues([]) == []

    def test_all_issues_get_criterion_pt(self):
        issues = [
            _make_issue("1.1.1 Non-text Content", Severity.CRITICAL),
            _make_issue("2.4.2 Page Titled", Severity.HIGH),
            _make_issue("4.1.2 Name, Role, Value", Severity.MEDIUM),
        ]
        results = translate_issues(issues)
        assert len(results) == 3
        assert all(r.criterion_pt is not None for r in results)
        assert all(r.severity_pt is not None for r in results)

    def test_does_not_mutate_originals(self):
        issue = _make_issue("1.1.1 Non-text Content", Severity.CRITICAL)
        original_criterion = issue.criterion
        translate_issues([issue])
        assert issue.criterion == original_criterion
        assert issue.criterion_pt is None
