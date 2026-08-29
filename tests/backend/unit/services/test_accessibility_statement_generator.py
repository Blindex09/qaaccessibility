"""Testes do gerador de Declaração de Acessibilidade.

Verifica: (1) dados reais dos issues (nunca inventados), (2) placeholders
visíveis quando organização/contato não são informados -- nunca fabricados,
(3) PDF gerado é PDF/UA-1 taggeado de verdade, igual ao checklist_pdf_exporter.
"""
import io

import pypdf

from backend.src.services.accessibility_statement_generator import (
    build_accessibility_statement,
    export_accessibility_statement_pdf,
    render_accessibility_statement_html,
)
from backend.src.shared.models import Severity
from tests.backend.native_deps import requires_weasyprint

_ISSUES = [
    {"id": "p-1", "criterion": "1.1.1 Non-text Content", "severity": Severity.CRITICAL, "description": "Imagem sem alt."},
    {"id": "p-2", "criterion": "1.1.1 Non-text Content", "severity": Severity.HIGH, "description": "Alt genérico."},
    {"id": "p-3", "criterion": "2.4.4 Link Purpose", "severity": "medium", "description": "Link sem nome acessível."},
]


class TestBuildAccessibilityStatement:
    def test_counts_by_severity_use_real_enum_values_not_str_dunder(self):
        """Regressão do mesmo bug corrigido em chat_tools.py::_summarize_issues --
        severity pode vir como Severity(str, Enum) real (não string), e
        str(Severity.CRITICAL) quebraria a contagem."""
        statement = build_accessibility_statement(_ISSUES, "https://example.com")
        assert statement["counts_by_severity"]["critical"] == 1
        assert statement["counts_by_severity"]["high"] == 1
        assert statement["counts_by_severity"]["medium"] == 1
        assert statement["total_issues"] == 3

    def test_groups_by_criterion_with_highest_severity(self):
        statement = build_accessibility_statement(_ISSUES, "https://example.com")
        by_criterion = {g["criterion"]: g for g in statement["known_limitations"]}
        assert by_criterion["1.1.1 Non-text Content"]["count"] == 2
        assert by_criterion["1.1.1 Non-text Content"]["severity"] == "critical"

    def test_zero_issues_means_conforme(self):
        statement = build_accessibility_statement([], "https://example.com")
        assert statement["conformance_level"] == "Conforme"
        assert statement["known_limitations"] == []

    def test_nonzero_issues_means_parcialmente_conforme(self):
        statement = build_accessibility_statement(_ISSUES, "https://example.com")
        assert statement["conformance_level"] == "Parcialmente conforme"

    def test_missing_org_and_contact_use_visible_placeholders_never_fabricated(self):
        statement = build_accessibility_statement(_ISSUES, "https://example.com")
        assert statement["organization_name"] == "[Nome da Organização]"
        assert statement["contact_email"] == "[e-mail de contato da organização]"
        assert statement["contact_phone"] == "[telefone de contato da organização]"

    def test_real_org_and_contact_are_used_verbatim_when_provided(self):
        statement = build_accessibility_statement(
            _ISSUES, "https://example.com",
            organization_name="Acme Ltda", contact_email="a11y@acme.com", contact_phone="+55 11 5555-0000",
        )
        assert statement["organization_name"] == "Acme Ltda"
        assert statement["contact_email"] == "a11y@acme.com"
        assert statement["contact_phone"] == "+55 11 5555-0000"


class TestRenderAccessibilityStatementHtml:
    def test_html_declares_language_and_title(self):
        statement = build_accessibility_statement(_ISSUES, "https://example.com", product_name="Site X")
        html = render_accessibility_statement_html(statement)
        assert 'lang="pt-BR"' in html
        assert "<title>Declaração de Acessibilidade - Site X</title>" in html

    def test_placeholder_contact_is_visually_flagged(self):
        statement = build_accessibility_statement(_ISSUES, "https://example.com")
        html = render_accessibility_statement_html(statement)
        assert 'class="placeholder"' in html
        assert "substitua pelos dados reais" in html

    def test_real_contact_is_not_flagged_as_placeholder(self):
        statement = build_accessibility_statement(
            _ISSUES, "https://example.com", organization_name="Acme", contact_email="a11y@acme.com",
        )
        html = render_accessibility_statement_html(statement)
        assert "substitua pelos dados reais" not in html

    def test_zero_issues_states_none_detected_not_a_fabricated_claim(self):
        statement = build_accessibility_statement([], "https://example.com")
        html = render_accessibility_statement_html(statement)
        assert "Nenhum problema de acessibilidade automatizado ou revisado por IA foi detectado" in html


@requires_weasyprint
class TestExportAccessibilityStatementPdf:
    def test_pdf_is_real_tagged_pdf_ua(self):
        statement = build_accessibility_statement(_ISSUES, "https://example.com", product_name="Site X")
        pdf_bytes = export_accessibility_statement_pdf(statement)
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        root = reader.trailer["/Root"]

        assert root.get("/MarkInfo", {}).get("/Marked") == True  # noqa: E712
        assert root.get("/Lang") == "pt-BR"
        assert "/StructTreeRoot" in root

    def test_pdf_has_at_least_one_page(self):
        statement = build_accessibility_statement(_ISSUES, "https://example.com")
        pdf_bytes = export_accessibility_statement_pdf(statement)
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        assert len(reader.pages) >= 1
