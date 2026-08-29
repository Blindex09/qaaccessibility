import json
from unittest.mock import AsyncMock, patch

import pytest

from backend.src.agents.checklist.checklist import run_checklist
from backend.src.shared.models import AccessibilityIssue, Guideline, Severity

CHECKLIST_ITEM = {
    "id": "chk-alt-manual",
    "criterion": "1.1.1 Non-text Content",
    "guideline": "WCAG 2.2",
    "status": "manual",
    "priority": "medium",
    "notes": "MANUAL QA CHECK: verifique se o alt text descreve o conteúdo real da imagem.",
}


def _issue() -> AccessibilityIssue:
    return AccessibilityIssue(
        id="issue-1",
        guideline=Guideline.WCAG_2_2,
        criterion="1.1.1 Non-text Content",
        severity=Severity.HIGH,
        element="<img src='logo.png'>",
        description="Missing alt attribute",
        suggestion="Add alt attribute",
    )


@pytest.mark.asyncio
class TestChecklistAgent:
    async def test_contract_on_success(self):
        with patch(
            "backend.src.agents.checklist.checklist.call_llm",
            new=AsyncMock(return_value=json.dumps([CHECKLIST_ITEM])),
        ):
            result = await run_checklist([_issue()])
        assert result.agent == "checklist"
        assert result.success is True
        assert len(result.data["checklist"]) == 1
        assert result.data["checklist"][0]["status"] == "manual"

    async def test_html_content_is_forwarded_when_provided(self):
        mock_llm = AsyncMock(return_value=json.dumps([CHECKLIST_ITEM]))
        with patch("backend.src.agents.checklist.checklist.call_llm", new=mock_llm):
            await run_checklist([_issue()], html_content="<html><body><img src='x.png'></body></html>")
        _, kwargs = mock_llm.call_args
        assert "<img" in kwargs["user_prompt"]

    async def test_no_html_content_still_succeeds(self):
        with patch(
            "backend.src.agents.checklist.checklist.call_llm",
            new=AsyncMock(return_value=json.dumps([CHECKLIST_ITEM])),
        ):
            result = await run_checklist([_issue()], html_content=None)
        assert result.success is True

    async def test_failure_on_invalid_json(self):
        with patch(
            "backend.src.agents.checklist.checklist.call_llm",
            new=AsyncMock(return_value="not json"),
        ):
            result = await run_checklist([_issue()])
        assert result.success is False
        assert result.error is not None

    async def test_failure_on_llm_exception(self):
        with patch(
            "backend.src.agents.checklist.checklist.call_llm",
            new=AsyncMock(side_effect=Exception("timeout")),
        ):
            result = await run_checklist([_issue()])
        assert result.success is False
        assert "timeout" in result.error
