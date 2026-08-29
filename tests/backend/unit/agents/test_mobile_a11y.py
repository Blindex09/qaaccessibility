import json
from unittest.mock import AsyncMock, patch

import pytest

from backend.src.agents.mobile_a11y.mobile_a11y import run_mobile_a11y

from .conftest_agents import (
    HTML_CLEAN,
    assert_agent_contract,
    assert_issues_valid,
    make_issue,
)

HTML_WITH_MOBILE_ISSUES = """
<html>
  <head>
    <meta name="viewport" content="width=device-width, user-scalable=no">
  </head>
  <body>
    <input type="text" placeholder="seu email">
    <input type="text" placeholder="telefone">
    <button style="width:20px; height:20px">X</button>
    <div style="width:800px; overflow-x:auto">
      <table><tr><td>Dados</td></tr></table>
    </div>
  </body>
</html>
""".strip()

MOBILE_ISSUE = make_issue(
    {
        "id": "mobile-1",
        "guideline": "WCAG 2.2",
        "criterion": "1.4.4 Resize Text",
        "severity": "critical",
        "element": "meta[name=viewport]",
        "description": "user-scalable=no prevents pinch-to-zoom, violating 1.4.4",
        "suggestion": "Remove user-scalable=no or set user-scalable=yes",
    }
)


@pytest.mark.asyncio
class TestMobileA11yAgent:
    async def test_contract_on_success(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value=json.dumps([MOBILE_ISSUE])),
        ):
            result = await run_mobile_a11y(HTML_WITH_MOBILE_ISSUES)
        assert_agent_contract(result, "mobile_a11y")
        assert_issues_valid(result.data["issues"])

    async def test_mobile_issue_has_mobile_id_prefix(self):
        """Issues do mobile_a11y devem ter id prefixado com mobile-."""
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value=json.dumps([MOBILE_ISSUE])),
        ):
            result = await run_mobile_a11y(HTML_WITH_MOBILE_ISSUES)
        for issue in result.data.get("issues", []):
            assert issue["id"].startswith("mobile-"), f"ID deve começar com mobile-: {issue['id']}"

    async def test_empty_html_returns_success(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value="[]"),
        ):
            result = await run_mobile_a11y("")
        assert result.success is True
        assert result.data["issues"] == []

    async def test_clean_html_no_issues(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value="[]"),
        ):
            result = await run_mobile_a11y(HTML_CLEAN)
        assert result.success is True
        assert len(result.data["issues"]) == 0

    async def test_failure_on_invalid_json(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value="not json"),
        ):
            result = await run_mobile_a11y(HTML_WITH_MOBILE_ISSUES)
        assert result.success is False
        assert result.error is not None

    async def test_failure_on_llm_exception(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(side_effect=Exception("timeout")),
        ):
            result = await run_mobile_a11y(HTML_WITH_MOBILE_ISSUES)
        assert result.success is False
        assert "timeout" in result.error

    async def test_target_size_2258_criterion_accepted(self):
        """2.5.8 Target Size (WCAG 2.2 novo) deve ser aceito como criterio valido."""
        issue_258 = make_issue(
            {
                "id": "mobile-2",
                "guideline": "WCAG 2.2",
                "criterion": "2.5.8 Target Size (Minimum)",
                "severity": "medium",
                "level": "AA",
                "element": "button.close",
                "description": "Button target area is 20x20px — below minimum 24x24 CSS px (2.5.8)",
                "suggestion": "Increase button size to at least 24x24 CSS px or add spacing",
            }
        )
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value=json.dumps([issue_258])),
        ):
            result = await run_mobile_a11y(HTML_WITH_MOBILE_ISSUES)
        assert result.success is True
        issues = result.data["issues"]
        assert any(i["criterion"].startswith("2.5.8") for i in issues)

    async def test_reduced_motion_criterion_accepted(self):
        """prefers-reduced-motion ausente deve gerar issue para 2.3.3 ou 2.5.4."""
        motion_issue = make_issue(
            {
                "id": "mobile-3",
                "guideline": "WCAG 2.2",
                "criterion": "2.3.3 Animation from Interactions",
                "severity": "medium",
                "level": "AAA",
                "element": "style",
                "description": "CSS animations present but @media (prefers-reduced-motion) not set",
                "suggestion": "Add @media (prefers-reduced-motion: reduce) block to disable/reduce animations",
            }
        )
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value=json.dumps([motion_issue])),
        ):
            result = await run_mobile_a11y(HTML_WITH_MOBILE_ISSUES)
        assert result.success is True
        issues = result.data["issues"]
        assert any("animation" in i["criterion"].lower() or "motion" in i["criterion"].lower() for i in issues)

    async def test_orientation_lock_1134_criterion_accepted(self):
        """1.3.4 Orientation deve ser aceito como criterio valido."""
        orient_issue = make_issue(
            {
                "id": "mobile-4",
                "guideline": "WCAG 2.2",
                "criterion": "1.3.4 Orientation",
                "severity": "high",
                "level": "AA",
                "element": "style",
                "description": "CSS locks page to portrait via orientation: portrait",
                "suggestion": "Remove orientation lock to allow landscape viewing",
            }
        )
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value=json.dumps([orient_issue])),
        ):
            result = await run_mobile_a11y(HTML_WITH_MOBILE_ISSUES)
        assert result.success is True
