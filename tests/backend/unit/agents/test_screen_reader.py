import json
from unittest.mock import AsyncMock, patch

import pytest

from backend.src.agents.screen_reader.screen_reader import run_screen_reader

from .conftest_agents import (
    HTML_CLEAN,
    assert_agent_contract,
    assert_issues_valid,
    make_issue,
)

HTML_WITH_SR_ISSUES = """
<html>
  <body>
    <h1>Título principal</h1>
    <h3>Subtitulo pulando h2</h3>
    <nav>Menu principal</nav>
    <nav>Menu secundario</nav>
    <a href="/page1">clique aqui</a>
    <a href="/page2">clique aqui</a>
    <input type="text" id="nome">
    <iframe src="ad.html"></iframe>
    <img src="photo.jpg">
  </body>
</html>
""".strip()

SR_ISSUE = make_issue(
    {
        "id": "screen-reader-1",
        "guideline": "WCAG 2.2",
        "criterion": "1.3.1 Info and Relationships",
        "severity": "high",
        "element": "h3 after h1",
        "description": "Heading level skipped from h1 to h3 — screen readers lose document structure",
        "suggestion": "Add h2 between h1 and h3 to maintain heading hierarchy",
    }
)


@pytest.mark.asyncio
class TestScreenReaderAgent:
    async def test_contract_on_success(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value=json.dumps([SR_ISSUE])),
        ):
            result = await run_screen_reader(HTML_WITH_SR_ISSUES)
        assert_agent_contract(result, "screen_reader")
        assert_issues_valid(result.data["issues"])

    async def test_screen_reader_issue_has_correct_id_prefix(self):
        """Issues do screen_reader devem ter id prefixado com screen-reader-."""
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value=json.dumps([SR_ISSUE])),
        ):
            result = await run_screen_reader(HTML_WITH_SR_ISSUES)
        for issue in result.data.get("issues", []):
            assert issue["id"].startswith("screen-reader-"), f"ID deve começar com screen-reader-: {issue['id']}"

    async def test_empty_html_returns_success(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value="[]"),
        ):
            result = await run_screen_reader("")
        assert result.success is True
        assert result.data["issues"] == []

    async def test_clean_html_no_issues(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value="[]"),
        ):
            result = await run_screen_reader(HTML_CLEAN)
        assert result.success is True
        assert len(result.data["issues"]) == 0

    async def test_failure_on_invalid_json(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value="not json"),
        ):
            result = await run_screen_reader(HTML_WITH_SR_ISSUES)
        assert result.success is False
        assert result.error is not None

    async def test_failure_on_llm_exception(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(side_effect=Exception("timeout")),
        ):
            result = await run_screen_reader(HTML_WITH_SR_ISSUES)
        assert result.success is False

    async def test_skip_link_criterion_accepted(self):
        """2.4.1 Bypass Blocks (skip link) deve ser aceito como criterio valido."""
        skip_link_issue = make_issue(
            {
                "id": "screen-reader-2",
                "guideline": "WCAG 2.2",
                "criterion": "2.4.1 Bypass Blocks",
                "severity": "high",
                "level": "A",
                "element": "body",
                "description": "No skip-to-content link found at top of page",
                "suggestion": "Add <a href='#main'>Skip to main content</a> as first focusable element",
            }
        )
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value=json.dumps([skip_link_issue])),
        ):
            result = await run_screen_reader(HTML_WITH_SR_ISSUES)
        assert result.success is True
        issues = result.data["issues"]
        assert any(i["criterion"] == "2.4.1 Bypass Blocks" for i in issues)

    async def test_aria_hidden_on_focusable_criterion_accepted(self):
        """1.3.1 Info and Relationships cobre aria-hidden em elementos focalizaveis."""
        issue = make_issue(
            {
                "id": "screen-reader-3",
                "guideline": "WCAG 2.2",
                "criterion": "4.1.2 Name, Role, Value",
                "severity": "critical",
                "element": "button[aria-hidden=true]",
                "description": "Focusable button has aria-hidden=true — screen reader skips but keyboard reaches it",
                "suggestion": "Remove aria-hidden=true from button or add tabindex='-1'",
            }
        )
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value=json.dumps([issue])),
        ):
            result = await run_screen_reader(HTML_WITH_SR_ISSUES)
        assert result.success is True
