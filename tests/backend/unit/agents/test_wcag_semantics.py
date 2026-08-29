import json
from unittest.mock import AsyncMock, patch

import pytest

from backend.src.agents.wcag_semantics.wcag_semantics import run_wcag_semantics

from .conftest_agents import (
    HTML_CLEAN,
    assert_agent_contract,
    assert_issues_valid,
    make_issue,
)

HTML_SEMANTICS_ISSUES = """
<!DOCTYPE html>
<html>
  <head><title></title></head>
  <body>
    <div>Navigation</div>
    <div class="header"><h3>First heading is h3</h3></div>
    <a href="/about">Click here</a>
    <table><tr><td>Data</td></tr></table>
    <iframe src="/widget"></iframe>
  </body>
</html>
""".strip()

SEMANTICS_ISSUE = make_issue(
    {
        "id": "semantics-1",
        "guideline": "WCAG 2.2",
        "criterion": "2.4.2 Page Titled",
        "severity": "critical",
        "element": "<title>",
        "description": "Page title is empty; screen readers announce blank title",
        "suggestion": "Provide a descriptive <title> that identifies the page",
        "wcag_url": "https://www.w3.org/WAI/WCAG22/Understanding/page-titled",
    }
)


@pytest.mark.asyncio
class TestWCAGSemanticsAgent:
    async def test_contract_on_success(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value=json.dumps([SEMANTICS_ISSUE])),
        ):
            result = await run_wcag_semantics(HTML_SEMANTICS_ISSUES)
        assert_agent_contract(result, "wcag_semantics")
        assert_issues_valid(result.data["issues"])

    async def test_issue_id_starts_with_semantics(self):
        """Issues do wcag_semantics devem ter id prefixado com semantics-."""
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value=json.dumps([SEMANTICS_ISSUE])),
        ):
            result = await run_wcag_semantics(HTML_SEMANTICS_ISSUES)
        for issue in result.data.get("issues", []):
            assert issue["id"].startswith("semantics-"), f"ID deve começar com semantics-: {issue['id']}"

    async def test_empty_html_returns_success(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value="[]"),
        ):
            result = await run_wcag_semantics("")
        assert result.success is True
        assert result.data["issues"] == []

    async def test_clean_html_no_issues(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value="[]"),
        ):
            result = await run_wcag_semantics(HTML_CLEAN)
        assert result.success is True
        assert len(result.data["issues"]) == 0

    async def test_failure_on_invalid_json(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value="not json at all"),
        ):
            result = await run_wcag_semantics(HTML_SEMANTICS_ISSUES)
        assert result.success is False
        assert result.error is not None

    async def test_failure_on_llm_exception(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(side_effect=Exception("API error")),
        ):
            result = await run_wcag_semantics(HTML_SEMANTICS_ISSUES)
        assert result.success is False
        assert "API error" in (result.error or "")

    async def test_strips_markdown_fences_from_response(self):
        """extract_json_array deve aceitar resposta embrulhada em ```json```."""
        fenced = f"```json\n{json.dumps([SEMANTICS_ISSUE])}\n```"
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value=fenced),
        ):
            result = await run_wcag_semantics(HTML_SEMANTICS_ISSUES)
        assert result.success is True
        assert len(result.data["issues"]) == 1

    async def test_detects_title_unique_info_not_first(self):
        """Deve detectar <title> onde a info unica vem apos o nome da marca (WCAG 2.4.2)."""
        html = (
            "<!DOCTYPE html><html lang='pt-BR'><head>"
            "<title>Brand | Search results</title>"
            "</head><body><main><h1>Results</h1></main></body></html>"
        )
        issue = make_issue(
            {
                "id": "semantics-1",
                "criterion": "2.4.2 Page Titled",
                "severity": "medium",
                "element": "<title>",
                "description": "Unique page info comes after the brand name in the title",
                "suggestion": "Move the unique info first: 'Search results | Brand'",
                "wcag_url": "https://www.w3.org/WAI/WCAG22/Understanding/page-titled",
            }
        )
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value=json.dumps([issue])),
        ):
            result = await run_wcag_semantics(html)
        assert result.success is True
        ids = [i["id"] for i in result.data["issues"]]
        assert any(i.startswith("semantics-") for i in ids)

    async def test_detects_missing_aria_current(self):
        """Deve detectar item ativo de nav sem aria-current='page' (WCAG 2.4.8 / 3.2.3)."""
        html = (
            "<!DOCTYPE html><html lang='pt-BR'><head><title>Home</title></head>"
            "<body><nav><ul>"
            "<li><a href='/' class='active'>Home</a></li>"
            "<li><a href='/about'>About</a></li>"
            "</ul></nav><main><h1>Home</h1></main></body></html>"
        )
        issue = make_issue(
            {
                "id": "semantics-1",
                "criterion": "2.4.8 Location",
                "severity": "medium",
                "element": "nav a.active",
                "description": "Active nav item indicated only by CSS class, no aria-current",
                "suggestion": "Add aria-current='page' to the active link",
                "wcag_url": "https://www.w3.org/WAI/WCAG22/Understanding/location",
            }
        )
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value=json.dumps([issue])),
        ):
            result = await run_wcag_semantics(html)
        assert result.success is True
        assert len(result.data["issues"]) == 1
        assert_issues_valid(result.data["issues"])

    async def test_detects_b_instead_of_strong(self):
        """Deve detectar <b> usado para importancia semântica onde <strong> e correto (WCAG 1.3.1)."""
        html = (
            "<!DOCTYPE html><html lang='pt-BR'><head><title>Page</title></head>"
            "<body><main><h1>Doc</h1>"
            "<p>This is <b>very important</b> information.</p>"
            "</main></body></html>"
        )
        issue = make_issue(
            {
                "id": "semantics-1",
                "criterion": "1.3.1 Info and Relationships",
                "severity": "low",
                "element": "<b>",
                "description": "<b> used for emphasis but has no semantic weight for AT",
                "suggestion": "Replace <b> with <strong> for important content",
                "wcag_url": "https://www.w3.org/WAI/WCAG22/Understanding/info-and-relationships",
            }
        )
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value=json.dumps([issue])),
        ):
            result = await run_wcag_semantics(html)
        assert result.success is True
        assert len(result.data["issues"]) == 1
        assert result.data["issues"][0]["criterion"].startswith("1.3.1")

    async def test_detects_abbr_without_title(self):
        """Deve detectar sigla sem <abbr title='...'> na primeira ocorrencia (WCAG 3.1.4)."""
        html = (
            "<!DOCTYPE html><html lang='pt-BR'><head><title>Guide</title></head>"
            "<body><main><h1>Guide</h1>"
            "<p>Follow the WCAG guidelines to improve accessibility.</p>"
            "</main></body></html>"
        )
        issue = make_issue(
            {
                "id": "semantics-1",
                "criterion": "3.1.4 Abbreviations",
                "severity": "low",
                "level": "AAA",
                "element": "p",
                "description": "Abbreviation 'WCAG' used without <abbr> expansion on first use",
                "suggestion": "Wrap with <abbr title='Web Content Accessibility Guidelines'>WCAG</abbr>",
                "wcag_url": "https://www.w3.org/WAI/WCAG22/Understanding/abbreviations",
            }
        )
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value=json.dumps([issue])),
        ):
            result = await run_wcag_semantics(html)
        assert result.success is True
        assert len(result.data["issues"]) == 1
        assert result.data["issues"][0]["criterion"].startswith("3.1.4")
