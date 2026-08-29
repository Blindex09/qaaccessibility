"""Testes do exportador de PDF acessível do checklist.

Verifica que o PDF gerado é PDF/UA-1 taggeado de verdade (StructTreeRoot,
/Marked, /Lang), com estrutura semântica hierárquica (h1/h2/h3), sumário navegável
com links âncora semânticos baseados no critério WCAG, níveis de conformidade (A, AA, AAA),
princípios WCAG (POUR), diretrizes WCAG, localização exata do problema, separação entre
criticidade normativa e prioridade de atendimento da equipe, e links oficiais do W3C.
"""
import io

import pypdf

from backend.src.services.checklist_pdf_exporter import export_checklist_pdf, render_checklist_html
from backend.src.shared.models import ChecklistItem
from tests.backend.native_deps import requires_weasyprint

_ITEMS = [
    ChecklistItem(
        id="chk-1",
        criterion="1.1.1 Non-text Content",
        guideline="WCAG 2.2",
        status="fail",
        priority="critical",
        notes="1. Localize no cabeçalho a tag `<img>` do logotipo.\n2. Adicione `alt=\"Logotipo da Loja\"` descritivo.",
    ),
    ChecklistItem(
        id="chk-2",
        criterion="2.5.8 Target Size (Minimum)",
        guideline="WCAG 2.2",
        status="manual",
        priority="medium",
        notes="MANUAL QA CHECK: 1. No rodapé, meça o tamanho do botão.\n2. Garanta pelo menos 24x24px de dimensão.",
    ),
    ChecklistItem(
        id="chk-3",
        criterion="4.1.2 Name, Role, Value",
        guideline="WAI-ARIA",
        status="pass",
        priority="low",
        notes=None,
    ),
]


class TestRenderChecklistHtml:
    def test_html_declares_language_and_title(self):
        html = render_checklist_html(_ITEMS, "https://example.com")
        assert 'lang="pt-BR"' in html
        assert "<title>" in html
        assert "Relatório de Conformidade e Checklist de Acessibilidade" in html
        assert "Site / Página Avaliada:" in html
        assert "O Que Foi Testado (Escopo):" in html
        assert "Leitor de Tela Testado:" in html

    def test_status_never_relies_on_color_alone(self):
        html = render_checklist_html(_ITEMS, "https://example.com")
        assert "[FALHA]" in html
        assert "[VERIFICAÇÃO MANUAL]" in html
        assert "[OK]" in html

    def test_uses_semantic_headings_and_chapters(self):
        html = render_checklist_html(_ITEMS, "https://example.com")
        assert "<h1>" in html
        assert "<h2" in html
        assert "<h3" in html
        assert "Capítulo 1: Resumo Executivo e Guia de Entendimento da Auditoria" in html
        assert "Capítulo 2:" in html

    def test_renders_educational_guide_on_criticality_and_priorities(self):
        html = render_checklist_html(_ITEMS, "https://example.com")
        assert "Como Compreender os Níveis de Criticidade e Prioridades" in html
        assert "Criticidade Normativa (Níveis WCAG):" in html
        assert "Prioridade de Atendimento da Equipe:" in html
        assert "Nível A (Criticidade Máxima)" in html
        assert "Nível AA (Criticidade Padrão Legal)" in html

    def test_renders_table_of_contents_with_semantic_anchor_links(self):
        html = render_checklist_html(_ITEMS, "https://example.com")
        assert '<nav class="toc"' in html
        assert 'role="doc-toc"' in html
        assert 'href="#capitulo-resumo-executivo"' in html
        assert 'href="#criterio-1-1-1-conteudo-nao-textual"' in html
        assert 'href="#criterio-2-5-8-tamanho-do-alvo-minimo"' in html
        assert 'href="#criterio-4-1-2-nome-funcao-e-valor"' in html

    def test_renders_conformance_levels_and_principles(self):
        html = render_checklist_html(_ITEMS, "https://example.com")
        assert "Nível A" in html
        assert "Princípio 1: Perceptível" in html
        assert "Princípio 2: Operável" in html
        assert "Princípio 4: Robusto" in html

    def test_renders_back_to_toc_links(self):
        html = render_checklist_html(_ITEMS, "https://example.com")
        assert 'href="#capitulo-sumario"' in html
        assert "Voltar ao Sumário" in html

    def test_renders_accessible_summary_table(self):
        html = render_checklist_html(_ITEMS, "https://example.com")
        assert '<table class="summary-table"' in html
        assert '<th scope="col">Status de Conformidade</th>' in html
        assert '<th scope="col"' in html

    def test_renders_structured_fields_with_location_and_separated_criticality(self):
        html = render_checklist_html(_ITEMS, "https://example.com")
        assert "1. Princípio WCAG:" in html
        assert "2. Diretriz WCAG:" in html
        assert "3. Critério de Sucesso:" in html
        assert "4. Criticidade Normativa (WCAG):" in html
        assert "5. Prioridade de Atendimento:" in html
        assert "6. Onde Está o Problema (Localização e Elemento):" in html
        assert "7. O Que Aconteceu (Diagnóstico):" in html
        assert "8. Por Que Isso Prejudica o Usuário (Impacto):" in html
        assert "9. Como Resolver (Plano de Remediação Semântica):" in html
        assert "9. Roteiro de Teste Manual com Leitor de Tela (Como Avaliar):" in html

    def test_renders_rich_lists_links_and_code(self):
        html = render_checklist_html(_ITEMS, "https://example.com")
        assert "<ol class=\"steps-list\">" in html or "<ul class=\"bullet-list\">" in html
        assert "<li>" in html
        assert "<code>" in html
        assert "https://www.w3.org/WAI/WCAG22/Understanding/" in html
        assert 'target="_blank"' in html
        assert "Guia Oficial do W3C:" in html


@requires_weasyprint
class TestExportChecklistPdf:
    def test_pdf_is_real_tagged_pdf_ua(self):
        pdf_bytes = export_checklist_pdf(_ITEMS, "https://example.com")
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        root = reader.trailer["/Root"]

        # pypdf devolve BooleanObject, não o singleton `True` -- comparar com ==
        assert root.get("/MarkInfo", {}).get("/Marked") == True  # noqa: E712
        assert root.get("/Lang") == "pt-BR"
        assert "/StructTreeRoot" in root
        assert "Relatório de Conformidade e Checklist de Acessibilidade" in reader.metadata.title

    def test_pdf_has_at_least_one_page(self):
        pdf_bytes = export_checklist_pdf(_ITEMS, "https://example.com")
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        assert len(reader.pages) >= 1
