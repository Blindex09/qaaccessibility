"""Fixtures e helpers compartilhados para testes dos sub-agentes."""

HTML_WITH_ISSUES = """
<html>
  <body>
    <img src="logo.png">
    <div onclick="submit()" style="color:red">Clique aqui</div>
    <input type="text" placeholder="Digite seu nome">
    <p style="color:#aaa">Texto com baixo contraste</p>
  </body>
</html>
""".strip()

HTML_CLEAN = "<html lang='pt-BR'><body><main><h1>Título</h1><button>OK</button></main></body></html>"

ISSUE_TEMPLATE = {
    "id": "test-001",
    "guideline": "WCAG 2.2",
    "criterion": "1.1.1 Non-text Content",
    "severity": "critical",
    "level": "A",
    "element": "img",
    "description": "Image missing alt attribute",
    "description_technical": "img element lacks an alt attribute, violating WCAG 2.2 SC 1.1.1 (Non-text Content).",
    "why_simple": "A blind user relying on a screen reader will hear nothing when this image is reached, losing the information it conveys.",
    "why_technical": "Screen readers expose the alt attribute as the accessible name of the img element. Without it, the AT announces the src filename or 'image', providing no semantic value.",
    "suggestion": "Add a short, meaningful alt text that describes what the image shows.",
    "suggestion_technical": 'Add alt="<descriptive text>" to the <img> element, or alt="" if the image is purely decorative.',
    "wcag_url": "https://www.w3.org/WAI/WCAG22/Understanding/non-text-content.html",
}

VALID_SEVERITIES = {"critical", "high", "medium", "low"}
VALID_GUIDELINES = {"WCAG 2.2", "WAI-ARIA", "ADA/Section 508"}


def make_issue(overrides: dict | None = None) -> dict:
    return {**ISSUE_TEMPLATE, **(overrides or {})}


def assert_agent_contract(result, expected_agent: str) -> None:
    assert result.agent == expected_agent
    assert isinstance(result.success, bool)
    assert isinstance(result.data, dict)
    if not result.success:
        assert result.error is not None


def assert_issues_valid(issues: list[dict]) -> None:
    for issue in issues:
        assert issue["severity"] in VALID_SEVERITIES, f"severity invalida: {issue['severity']}"
        assert issue["guideline"] in VALID_GUIDELINES, f"guideline invalida: {issue['guideline']}"
        assert isinstance(issue["description"], str) and issue["description"]
        assert isinstance(issue["suggestion"], str) and issue["suggestion"]
