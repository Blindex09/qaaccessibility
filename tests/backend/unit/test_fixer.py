import json
from unittest.mock import AsyncMock, patch

import pytest

from backend.src.agents.fixer.fixer import (
    _enrich_issues_with_fixed_element,
    _extract_fixed_snippet,
    run_fixer,
)

MOCK_FIX_RESPONSE = {
    "fixed_html": "<html><body><img src='logo.png' alt='Logo'/><button aria-label='Close'>X</button></body></html>",
    "changes_summary": [
        "Added alt='Logo' to img element",
        "Added aria-label='Close' to button",
    ],
}


@pytest.mark.asyncio
class TestFixerAgent:
    async def test_returns_fixed_html_on_success(self, sample_html, sample_issue):
        with patch(
            "backend.src.agents.fixer.fixer.call_llm",
            new=AsyncMock(return_value=json.dumps(MOCK_FIX_RESPONSE)),
        ):
            result = await run_fixer(sample_html, [sample_issue])

        assert result.success is True
        assert result.agent == "fixer"
        assert "alt='Logo'" in result.data["fixed_html"]
        assert len(result.data["changes_summary"]) == 2

    async def test_failure_on_invalid_json(self, sample_html, sample_issue):
        with patch(
            "backend.src.agents.fixer.fixer.call_llm",
            new=AsyncMock(return_value="invalid"),
        ):
            result = await run_fixer(sample_html, [sample_issue])

        assert result.success is False
        assert result.error is not None

    async def test_failure_on_llm_exception(self, sample_html, sample_issue):
        with patch(
            "backend.src.agents.fixer.fixer.call_llm",
            new=AsyncMock(side_effect=RuntimeError("Timeout")),
        ):
            result = await run_fixer(sample_html, [sample_issue])

        assert result.success is False
        assert "Timeout" in result.error

    async def test_enriched_issues_returned_on_success(self, sample_html, sample_issue):
        """Resultado deve incluir enriched_issues com fixed_element_html quando possivel."""
        with patch(
            "backend.src.agents.fixer.fixer.call_llm",
            new=AsyncMock(return_value=json.dumps(MOCK_FIX_RESPONSE)),
        ):
            result = await run_fixer(sample_html, [sample_issue])

        assert result.success is True
        assert "enriched_issues" in result.data
        assert isinstance(result.data["enriched_issues"], list)
        assert len(result.data["enriched_issues"]) == 1

    async def test_enriched_issue_has_fixed_element_html(self, sample_html, sample_issue):
        """fixed_element_html deve ser preenchido quando o elemento existe no HTML corrigido."""
        # O sample_issue tem element='img' (sem <) — o regex extrai o tag corretamente
        # O MOCK_FIX_RESPONSE tem <img src='logo.png' alt='Logo'> no fixed_html
        issue_with_tag = sample_issue.model_copy(update={"element": "<img src='logo.png'>"})
        with patch(
            "backend.src.agents.fixer.fixer.call_llm",
            new=AsyncMock(return_value=json.dumps(MOCK_FIX_RESPONSE)),
        ):
            result = await run_fixer(sample_html, [issue_with_tag])

        enriched = result.data["enriched_issues"][0]
        assert enriched.get("fixed_element_html") is not None
        assert "alt=" in enriched["fixed_element_html"]

    async def test_empty_fixed_html_causes_failure(self, sample_html, sample_issue):
        """Gap fix: fixed_html vazio deve causar success=False (não success=True com fallback)."""
        empty_fix = {"fixed_html": "", "changes_summary": []}
        with patch(
            "backend.src.agents.fixer.fixer.call_llm",
            new=AsyncMock(return_value=json.dumps(empty_fix)),
        ):
            result = await run_fixer(sample_html, [sample_issue])
        assert result.success is False

    async def test_request_id_accepted(self, sample_html, sample_issue):
        """request_id deve ser aceito sem erros (gap tracing)."""
        with patch(
            "backend.src.agents.fixer.fixer.call_llm",
            new=AsyncMock(return_value=json.dumps(MOCK_FIX_RESPONSE)),
        ):
            result = await run_fixer(sample_html, [sample_issue], request_id="abc123")
        assert result.success is True
        assert result.agent == "fixer"


class TestExtractFixedSnippet:
    def test_extracts_img_tag(self):
        html = "<body><img src='logo.png' alt='Logo'/></body>"
        result = _extract_fixed_snippet("<img src='logo.png'>", html)
        assert result is not None
        assert "alt='Logo'" in result

    def test_extracts_button_with_content(self):
        html = "<body><button aria-label='Close'>X</button></body>"
        result = _extract_fixed_snippet("<button>X</button>", html)
        assert result is not None
        assert "aria-label" in result

    def test_returns_none_for_unknown_tag(self):
        html = "<body><p>Hello</p></body>"
        result = _extract_fixed_snippet("<div>content</div>", html)
        # div não existe no html — deve retornar None
        assert result is None

    def test_returns_none_for_empty_element(self):
        result = _extract_fixed_snippet("", "<body></body>")
        assert result is None

    def test_returns_none_for_empty_html(self):
        result = _extract_fixed_snippet("<img src='x'>", "")
        assert result is None

    def test_limits_snippet_to_500_chars(self):
        long_html = "<img " + ("data-x='y' " * 100) + "/>"
        result = _extract_fixed_snippet("<img src='x'>", f"<body>{long_html}</body>")
        if result:
            assert len(result) <= 503  # 500 + "..."


class TestEnrichIssuesWithFixedElement:
    def test_returns_same_count(self, sample_issue):
        fixed_html = "<img src='logo.png' alt='Logo'/>"
        result = _enrich_issues_with_fixed_element([sample_issue], fixed_html)
        assert len(result) == 1

    def test_enriches_fixed_element_html(self, sample_issue):
        fixed_html = "<img src='logo.png' alt='Logo da empresa'/>"
        issue_with_tag = sample_issue.model_copy(update={"element": "<img src='logo.png'>"})
        result = _enrich_issues_with_fixed_element([issue_with_tag], fixed_html)
        assert result[0].fixed_element_html is not None
        assert "alt=" in result[0].fixed_element_html

    def test_does_not_mutate_original(self, sample_issue):
        fixed_html = "<img src='logo.png' alt='Logo'/>"
        _enrich_issues_with_fixed_element([sample_issue], fixed_html)
        assert sample_issue.fixed_element_html is None
