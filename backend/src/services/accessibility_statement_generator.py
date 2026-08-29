"""
accessibility_statement_generator.py
Gera uma Declaração de Acessibilidade (Accessibility Statement) real, a partir
dos issues da última análise em cache -- não um texto solto inventado pelo
modelo. Segue o mesmo padrão de `checklist_pdf_exporter.py`: monta HTML
semântico e deixa o WeasyPrint (>=54, `pdf_variant="pdf/ua-1"`) gerar a árvore
de tags do PDF a partir dessa semântica.

Por que não é gerada por LLM: uma declaração de acessibilidade é um documento
de conformidade que a organização publica publicamente -- inventar "o que já
foi corrigido" ou dados de contato da organização seria fabricar conteúdo
apresentado como genuíno. Este gerador só relata o que a análise real
encontrou (issues, critérios WCAG, severidades) e usa placeholders visíveis
("[Nome da Organização]" etc.) quando a organização não informa esses dados
-- nunca inventa um nome de empresa, e-mail ou telefone.
"""
import logging
from html import escape
from typing import Any

logger = logging.getLogger(__name__)

# Mesma string real usada em checklist_pdf_exporter.py/xlsx_exporter.py --
# é literalmente o motor usado no pipeline, não um navegador genérico chutado.
_METHODOLOGY = (
    "Varredura automatizada com axe-core real (via Chromium/Browserless CDP) combinada com "
    "revisão de especialistas de IA em WCAG 2.2 (por princípio: Perceptível, Operável, "
    "Compreensível, Robusto) e verificação determinística de contraste de cores. "
    "Ferramentas automatizadas detectam aproximadamente 30-40% dos problemas de acessibilidade; "
    "os itens sinalizados como verificação manual no checklist completam essa cobertura e "
    "precisam de confirmação humana com leitor de tela."
)

_PLACEHOLDER_ORG = "[Nome da Organização]"
_PLACEHOLDER_EMAIL = "[e-mail de contato da organização]"
_PLACEHOLDER_PHONE = "[telefone de contato da organização]"

_CSS = """
@page { size: A4; margin: 2.2cm; }
body { font-family: Arial, Helvetica, sans-serif; font-size: 11pt; color: #1a1a1a; line-height: 1.5; }
h1 { font-size: 20pt; margin-bottom: 0.2em; }
.meta { color: #444; font-size: 10pt; margin-bottom: 1.5em; }
h2 { font-size: 14pt; margin-top: 1.6em; border-bottom: 1px solid #ccc; padding-bottom: 0.2em; }
p { margin: 0.6em 0; }
ul { padding-left: 0; list-style: none; }
li { margin-bottom: 0.7em; padding: 0.5em 0.8em; border-left: 4px solid #ccc; background: #fafafa; }
.severity { font-weight: bold; }
.criterion { font-weight: bold; }
.placeholder { color: #8a5a00; font-style: italic; }
"""

_SEVERITY_LABELS = {
    "critical": "[CRÍTICO]",
    "high": "[ALTO]",
    "medium": "[MÉDIO]",
    "low": "[BAIXO]",
}
_SEVERITY_COLORS = {
    "critical": "#b3261e",
    "high": "#c2660e",
    "medium": "#8a5a00",
    "low": "#5f6368",
}
_SEVERITY_ORDER = ("critical", "high", "medium", "low")


def _severity_of(issue: dict[str, Any]) -> str:
    """Mesmo bug já corrigido em chat_tools.py::_summarize_issues: nunca usar
    str(issue.get("severity")) direto -- Severity(str, Enum) tem __str__
    sobrescrito ("Severity.LOW"). .lower() no valor real evita isso."""
    return (issue.get("severity") or "").lower()


def _group_by_criterion(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Agrupa issues reais por critério WCAG, mantendo a severidade mais alta
    e uma descrição representativa real (não inventada) por grupo."""
    groups: dict[str, dict[str, Any]] = {}
    for issue in issues:
        criterion = str(issue.get("criterion") or "Critério não identificado")
        sev = _severity_of(issue)
        group = groups.setdefault(
            criterion, {"criterion": criterion, "count": 0, "severity": sev, "description": issue.get("description") or ""}
        )
        group["count"] += 1
        is_ranked_pair = sev in _SEVERITY_ORDER and group["severity"] in _SEVERITY_ORDER
        if is_ranked_pair and _SEVERITY_ORDER.index(sev) < _SEVERITY_ORDER.index(group["severity"]):
            group["severity"] = sev
    return sorted(
        groups.values(),
        key=lambda g: _SEVERITY_ORDER.index(g["severity"]) if g["severity"] in _SEVERITY_ORDER else len(_SEVERITY_ORDER),
    )


def build_accessibility_statement(
    issues: list[dict[str, Any]],
    url: str,
    organization_name: str | None = None,
    product_name: str | None = None,
    contact_email: str | None = None,
    contact_phone: str | None = None,
) -> dict[str, Any]:
    """Monta os dados estruturados reais da declaração (sem HTML/PDF ainda) --
    usado tanto para a resposta compacta do chat quanto para o export."""
    counts: dict[str, int] = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for issue in issues:
        sev = _severity_of(issue)
        if sev in counts:
            counts[sev] += 1

    total = len(issues)
    conformance_level = "Conforme" if total == 0 else "Parcialmente conforme"

    return {
        "organization_name": organization_name or _PLACEHOLDER_ORG,
        "product_name": product_name or "Produto Avaliado",
        "url": url or "não informada",
        "contact_email": contact_email or _PLACEHOLDER_EMAIL,
        "contact_phone": contact_phone or _PLACEHOLDER_PHONE,
        "conformance_target": "WCAG 2.2 Nível AA",
        "conformance_level": conformance_level,
        "total_issues": total,
        "counts_by_severity": counts,
        "known_limitations": _group_by_criterion(issues),
        "methodology": _METHODOLOGY,
    }


def render_accessibility_statement_html(statement: dict[str, Any]) -> str:
    """Monta o HTML semântico que vira a base do PDF taggeado."""
    org = escape(statement["organization_name"])
    product = escape(statement["product_name"])
    url = escape(statement["url"])
    is_placeholder_org = statement["organization_name"] == _PLACEHOLDER_ORG
    org_html = f'<span class="placeholder">{org}</span>' if is_placeholder_org else org

    limitations_html = ""
    limitations = statement["known_limitations"]
    if limitations:
        rows = []
        for item in limitations:
            sev = item["severity"] if item["severity"] in _SEVERITY_ORDER else "low"
            color = _SEVERITY_COLORS.get(sev, "#333")
            label = _SEVERITY_LABELS.get(sev, sev.upper())
            rows.append(
                f'<li style="border-left-color:{color}">'
                f'<span class="severity" style="color:{color}">{escape(label)}</span> '
                f'<span class="criterion">{escape(item["criterion"])}</span> '
                f'({item["count"]} ocorrência(s))'
                + (f'<div>{escape(item["description"][:240])}</div>' if item["description"] else "")
                + "</li>"
            )
        limitations_html = f"<h2>Limitações conhecidas</h2><ul>{''.join(rows)}</ul>"
    else:
        limitations_html = "<h2>Limitações conhecidas</h2><p>Nenhum problema de acessibilidade automatizado ou revisado por IA foi detectado na última auditoria desta página.</p>"

    contact_email = escape(statement["contact_email"])
    contact_phone = escape(statement["contact_phone"])
    is_placeholder_contact = statement["contact_email"] == _PLACEHOLDER_EMAIL

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<title>Declaração de Acessibilidade - {product}</title>
<style>{_CSS}</style>
</head>
<body>
<h1>Declaração de Acessibilidade para {org_html}</h1>
<p class="meta">Produto/página avaliada: {product} &middot; {url}</p>

<h2>Situação de conformidade</h2>
<p>Esta página tem como meta a conformidade com <strong>{escape(statement["conformance_target"])}</strong>.</p>
<p>Resultado da última auditoria automatizada + revisão por IA: <strong>{escape(statement["conformance_level"])}</strong>
({statement["total_issues"]} problema(s) detectado(s): {statement["counts_by_severity"]["critical"]} crítico(s),
{statement["counts_by_severity"]["high"]} alto(s), {statement["counts_by_severity"]["medium"]} médio(s),
{statement["counts_by_severity"]["low"]} baixo(s)).</p>

<h2>Metodologia de avaliação</h2>
<p>{escape(statement["methodology"])}</p>

{limitations_html}

<h2>Como reportar um problema de acessibilidade</h2>
<p>Se você encontrar uma barreira de acessibilidade nesta página, entre em contato:</p>
<ul>
  <li>E-mail: {f'<span class="placeholder">{contact_email}</span>' if is_placeholder_contact else contact_email}</li>
  <li>Telefone: {f'<span class="placeholder">{contact_phone}</span>' if is_placeholder_contact else contact_phone}</li>
</ul>
{'<p class="placeholder">Os dados de contato acima são placeholders -- substitua pelos dados reais da sua organização antes de publicar esta declaração.</p>' if is_placeholder_contact else ""}
</body>
</html>"""


def export_accessibility_statement_pdf(statement: dict[str, Any]) -> bytes:
    """Gera o PDF/UA-1 taggeado em bytes, pronto para download."""
    html = render_accessibility_statement_html(statement)
    logger.info(
        "[AccessibilityStatementGenerator] Gerando PDF/UA-1 (%d limitações conhecidas)",
        len(statement["known_limitations"]),
    )
    # Import tardio: ver nota em checklist_pdf_exporter.py -- as bibliotecas
    # nativas do WeasyPrint só são necessárias na hora de renderizar o PDF.
    from weasyprint import HTML

    return HTML(string=html).write_pdf(pdf_variant="pdf/ua-1")
