from unittest.mock import AsyncMock

import pytest

from backend.src.services.chat_tools import _resolve_and_analyze
from backend.src.shared.models import AgentResult


@pytest.mark.asyncio
async def test_audit_tree_and_fix_cache_share_original_document(monkeypatch):
    original = '<html><head><style>.layout{display:grid}</style></head><body><div id="page">Demo</div></body></html>'
    fetch = AsyncMock(return_value=(original, None))
    tree = AsyncMock(return_value="WebArea Demo")
    audit = AsyncMock(return_value=AgentResult(agent="audit", success=True, data={"issues": []}))
    monkeypatch.setattr("backend.src.services.browser.fetch_rendered_html_and_screenshot", fetch)
    monkeypatch.setattr("backend.src.services.browser.fetch_accessibility_tree_snapshot", tree)
    monkeypatch.setattr("backend.src.agents.orchestrator.orchestrator.orchestrate", audit)
    _, cache_content = await _resolve_and_analyze("", "https://example.com/")
    tree.assert_awaited_once_with("https://example.com/", html_content=original)
    assert cache_content == original
    assert audit.call_args.kwargs["source_document"] == original
