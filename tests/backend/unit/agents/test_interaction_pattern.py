import json
from unittest.mock import AsyncMock, patch

import pytest

from backend.src.agents.interaction_pattern.interaction_pattern import run_interaction_pattern

from .conftest_agents import HTML_CLEAN, assert_agent_contract, assert_issues_valid, make_issue

HTML_INPUT_WITH_SUGGESTIONS = """
<!DOCTYPE html>
<html lang="pt-BR">
  <head><title>Busca</title></head>
  <body>
    <input type="text" id="city-search" oninput="filterCities()">
    <ul class="suggestions" id="suggestions"></ul>
    <div class="section-title">Horário de funcionamento</div>
    <p>Segunda a sexta, 9h às 18h.</p>
  </body>
</html>
""".strip()

WIDGET_MISMATCH_ISSUE = make_issue(
    {
        "id": "pattern-1",
        "guideline": "WAI-ARIA",
        "criterion": "4.1.2 Name, Role, Value",
        "severity": "high",
        "element": '<input type="text" id="city-search"> + <ul class="suggestions">',
        "description": "Campo de busca com sugestões sem semântica de combobox",
        "suggestion": "Transformar em combobox ARIA real",
        "suggestion_technical": "REQUIRES JS BEYOND MARKUP: add role=combobox etc.",
        "wcag_url": "https://www.w3.org/WAI/WCAG22/Understanding/name-role-value.html",
    }
)

HEADING_MISMATCH_ISSUE = make_issue(
    {
        "id": "pattern-2",
        "guideline": "WCAG 2.2",
        "criterion": "1.3.1 Info and Relationships",
        "severity": "medium",
        "element": '<div class="section-title">Horário de funcionamento</div>',
        "description": "Texto de título de seção marcado como div, não como heading",
        "suggestion": "Promover para <h2>/<h3> mantendo o texto exato",
        "suggestion_technical": "Change <div class=\"section-title\"> to <h3 class=\"section-title\">, markup-only.",
        "wcag_url": "https://www.w3.org/WAI/WCAG22/Understanding/info-and-relationships.html",
    }
)


@pytest.mark.asyncio
class TestInteractionPatternAgent:
    async def test_contract_on_success(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value=json.dumps([WIDGET_MISMATCH_ISSUE, HEADING_MISMATCH_ISSUE])),
        ):
            result = await run_interaction_pattern(HTML_INPUT_WITH_SUGGESTIONS)
        assert_agent_contract(result, "interaction_pattern")
        assert_issues_valid(result.data["issues"])

    async def test_issue_id_starts_with_pattern(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value=json.dumps([WIDGET_MISMATCH_ISSUE])),
        ):
            result = await run_interaction_pattern(HTML_INPUT_WITH_SUGGESTIONS)
        for issue in result.data.get("issues", []):
            assert issue["id"].startswith("pattern-"), f"ID deve começar com pattern-: {issue['id']}"

    async def test_widget_mismatch_flags_requires_js_in_suggestion_technical(self):
        """Contrato central da categoria: quando a correção exige comportamento
        de teclado além de markup, isso deve estar explícito no texto, para o
        fixer saber que precisa escrever JS, não só atributos."""
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value=json.dumps([WIDGET_MISMATCH_ISSUE])),
        ):
            result = await run_interaction_pattern(HTML_INPUT_WITH_SUGGESTIONS)
        assert len(result.data["issues"]) == 1
        assert "REQUIRES JS BEYOND MARKUP" in result.data["issues"][0]["suggestion_technical"]

    async def test_heading_mismatch_criterion(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value=json.dumps([HEADING_MISMATCH_ISSUE])),
        ):
            result = await run_interaction_pattern(HTML_INPUT_WITH_SUGGESTIONS)
        assert result.data["issues"][0]["criterion"].startswith("1.3.1")

    async def test_empty_html_returns_success(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value="[]"),
        ):
            result = await run_interaction_pattern("")
        assert result.success is True
        assert result.data["issues"] == []

    async def test_clean_html_no_issues(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value="[]"),
        ):
            result = await run_interaction_pattern(HTML_CLEAN)
        assert result.success is True
        assert len(result.data["issues"]) == 0

    async def test_failure_on_invalid_json(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value="not json at all"),
        ):
            result = await run_interaction_pattern(HTML_INPUT_WITH_SUGGESTIONS)
        assert result.success is False
        assert result.error is not None

    async def test_failure_on_llm_exception(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(side_effect=Exception("API error")),
        ):
            result = await run_interaction_pattern(HTML_INPUT_WITH_SUGGESTIONS)
        assert result.success is False
        assert "API error" in (result.error or "")

    async def test_strips_markdown_fences_from_response(self):
        fenced = f"```json\n{json.dumps([WIDGET_MISMATCH_ISSUE])}\n```"
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value=fenced),
        ):
            result = await run_interaction_pattern(HTML_INPUT_WITH_SUGGESTIONS)
        assert result.success is True
        assert len(result.data["issues"]) == 1
