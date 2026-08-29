import json
from unittest.mock import AsyncMock, patch

import pytest

from backend.src.agents.perceiver.perceiver import run_perceiver

from .conftest_agents import (
    HTML_CLEAN,
    HTML_WITH_ISSUES,
    assert_agent_contract,
    assert_issues_valid,
    make_issue,
)

PERCEIVER_ISSUE = make_issue(
    {
        "id": "perceiver-1",
        "criterion": "1.1.1 Non-text Content",
        "severity": "critical",
        "element": "img",
        "description": "Image missing alt attribute",
        "suggestion": "Add alt attribute",
    }
)


@pytest.mark.asyncio
class TestPerceiverAgent:
    async def test_contract_on_success(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value=json.dumps([PERCEIVER_ISSUE])),
        ):
            result = await run_perceiver(HTML_WITH_ISSUES)
        assert_agent_contract(result, "perceiver")
        assert_issues_valid(result.data["issues"])

    async def test_only_wcag1x_criterion(self):
        """Perceiver deve retornar apenas criterios 1.x."""
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value=json.dumps([PERCEIVER_ISSUE])),
        ):
            result = await run_perceiver(HTML_WITH_ISSUES)
        for issue in result.data.get("issues", []):
            crit = issue["criterion"]
            assert crit.startswith("1."), f"Perceiver retornou criterio não-1.x: {crit}"

    async def test_empty_html_returns_success(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value="[]"),
        ):
            result = await run_perceiver("")
        assert result.success is True
        assert result.data["issues"] == []

    async def test_clean_html_returns_no_issues(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value="[]"),
        ):
            result = await run_perceiver(HTML_CLEAN)
        assert result.success is True
        assert len(result.data["issues"]) == 0

    async def test_failure_on_invalid_json(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value="not json"),
        ):
            result = await run_perceiver(HTML_WITH_ISSUES)
        assert result.success is False
        assert result.error is not None

    async def test_failure_on_llm_exception(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(side_effect=Exception("timeout")),
        ):
            result = await run_perceiver(HTML_WITH_ISSUES)
        assert result.success is False
        assert "timeout" in result.error

    async def test_images_of_text_criterion_accepted(self):
        """1.4.5 Images of Text deve ser aceito como criterio valido do perceiver."""
        issue_145 = make_issue(
            {
                "id": "perceiver-2",
                "criterion": "1.4.5 Images of Text",
                "severity": "medium",
                "level": "AA",
                "element": "img.banner-text",
                "description": "Text rendered as image instead of styled HTML text",
                "suggestion": "Replace image with CSS-styled HTML text",
            }
        )
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value=json.dumps([issue_145])),
        ):
            result = await run_perceiver(HTML_WITH_ISSUES)
        assert result.success is True
        issues = result.data["issues"]
        assert any(i["criterion"] == "1.4.5 Images of Text" for i in issues)

    async def test_all_issues_have_wcag1x_criterions(self):
        """Todos os criterios retornados devem começar com 1."""
        multi = [
            make_issue({"id": f"perceiver-{i}", "criterion": c})
            for i, c in enumerate(
                [
                    "1.1.1 Non-text Content",
                    "1.4.3 Contrast Minimum",
                    "1.4.5 Images of Text",
                    "1.4.10 Reflow",
                    "1.4.13 Content on Hover or Focus",
                ]
            )
        ]
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value=json.dumps(multi)),
        ):
            result = await run_perceiver(HTML_WITH_ISSUES)
        for issue in result.data.get("issues", []):
            assert issue["criterion"].startswith("1."), f"Perceiver emitiu criterio fora de 1.x: {issue['criterion']}"
