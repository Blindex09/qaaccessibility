import json
from unittest.mock import AsyncMock, patch

import pytest

from backend.src.agents.widgets_a11y.widgets_a11y import run_widgets_a11y

from .conftest_agents import (
    HTML_CLEAN,
    assert_agent_contract,
    assert_issues_valid,
    make_issue,
)

HTML_WITH_WIDGET_ISSUES = """
<html>
  <body>
    <div role="dialog">
      <h2>Confirmação</h2>
      <p>Deseja continuar?</p>
      <button>Sim</button>
    </div>
    <div role="tablist">
      <button role="tab">Aba 1</button>
    </div>
    <div role="tabpanel">Conteúdo da aba 1</div>
    <div role="progressbar" style="width:40%"></div>
    <div role="combobox">
      <input type="text">
    </div>
  </body>
</html>
""".strip()

WIDGET_ISSUE = make_issue(
    {
        "id": "widget-1",
        "guideline": "WAI-ARIA",
        "criterion": "4.1.2 Name, Role, Value",
        "severity": "critical",
        "element": "div[role=dialog]",
        "description": "role=dialog missing aria-labelledby pointing to dialog title",
        "suggestion": "Add aria-labelledby='dialog-title' to the dialog and id='dialog-title' to the h2",
    }
)


@pytest.mark.asyncio
class TestWidgetsA11yAgent:
    async def test_contract_on_success(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value=json.dumps([WIDGET_ISSUE])),
        ):
            result = await run_widgets_a11y(HTML_WITH_WIDGET_ISSUES)
        assert_agent_contract(result, "widgets_a11y")
        assert_issues_valid(result.data["issues"])

    async def test_widgets_issue_has_widget_id_prefix(self):
        """Issues do widgets_a11y devem ter id prefixado com widget-."""
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value=json.dumps([WIDGET_ISSUE])),
        ):
            result = await run_widgets_a11y(HTML_WITH_WIDGET_ISSUES)
        for issue in result.data.get("issues", []):
            assert issue["id"].startswith("widget-"), f"ID deve começar com widget-: {issue['id']}"

    async def test_empty_html_returns_success(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value="[]"),
        ):
            result = await run_widgets_a11y("")
        assert result.success is True
        assert result.data["issues"] == []

    async def test_clean_html_no_issues(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value="[]"),
        ):
            result = await run_widgets_a11y(HTML_CLEAN)
        assert result.success is True
        assert len(result.data["issues"]) == 0

    async def test_failure_on_invalid_json(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value="not json"),
        ):
            result = await run_widgets_a11y(HTML_WITH_WIDGET_ISSUES)
        assert result.success is False
        assert result.error is not None

    async def test_switch_widget_criterion_accepted(self):
        """role=switch sem aria-checked deve gerar issue valida."""
        switch_issue = make_issue(
            {
                "id": "widget-10",
                "guideline": "WAI-ARIA",
                "criterion": "4.1.2 Name, Role, Value",
                "severity": "critical",
                "element": "button[role=switch]",
                "description": "role=switch missing required aria-checked attribute",
                "suggestion": "Add aria-checked='false' or 'true' reflecting the switch state",
            }
        )
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value=json.dumps([switch_issue])),
        ):
            result = await run_widgets_a11y(HTML_WITH_WIDGET_ISSUES)
        assert result.success is True
        issues = result.data["issues"]
        assert any("switch" in i["element"].lower() for i in issues)

    async def test_listbox_widget_criterion_accepted(self):
        """role=listbox sem aria-selected nos options deve gerar issue valida."""
        listbox_issue = make_issue(
            {
                "id": "widget-11",
                "guideline": "WAI-ARIA",
                "criterion": "4.1.2 Name, Role, Value",
                "severity": "high",
                "element": "ul[role=listbox] > li",
                "description": "role=option items missing aria-selected attribute",
                "suggestion": "Add aria-selected='false' to each option; update to 'true' when selected",
            }
        )
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value=json.dumps([listbox_issue])),
        ):
            result = await run_widgets_a11y(HTML_WITH_WIDGET_ISSUES)
        assert result.success is True

    async def test_tooltip_1413_criterion_accepted(self):
        """1.4.13 Content on Hover or Focus cobre tooltips que desaparecem no hover."""
        tip_issue = make_issue(
            {
                "id": "widget-12",
                "guideline": "WAI-ARIA",
                "criterion": "1.4.13 Content on Hover or Focus",
                "severity": "medium",
                "level": "AA",
                "element": "div[role=tooltip]",
                "description": "Tooltip dismisses when pointer moves over it (not persistent)",
                "suggestion": "Ensure tooltip persists while pointer is over the tooltip element",
            }
        )
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value=json.dumps([tip_issue])),
        ):
            result = await run_widgets_a11y(HTML_WITH_WIDGET_ISSUES)
        assert result.success is True

    async def test_failure_on_llm_exception(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(side_effect=Exception("LLM timeout")),
        ):
            result = await run_widgets_a11y(HTML_WITH_WIDGET_ISSUES)
        assert result.success is False
        assert "LLM timeout" in result.error
