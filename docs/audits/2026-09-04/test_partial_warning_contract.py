"""A partial analysis must stay explicitly partial at the chat tool boundary."""
import json
from unittest.mock import AsyncMock, patch

from backend.src.services.chat_tools import analyze_page
from backend.src.shared.models import AgentResult


def test_chat_tool_preserves_partial_analysis_warning():
    warning = "1/19 agentes falharam -- resultado pode estar incompleto."
    partial = AgentResult(agent="orchestrator", success=True, data={
        "issues": [], "warning": warning,
        "agent_metrics": [{"agent": "a11y_expert_reviewer", "success": False, "duration_ms": 0}],
    })
    with (patch("backend.src.services.chat_tools._resolve_and_analyze",
                new=AsyncMock(return_value=(partial, "<html></html>"))),
          patch("backend.src.services.last_analysis_store.set_last_analysis"),
          patch("backend.src.services.last_analyzed_content_store.set_last_analyzed_content")):
        payload = json.loads(analyze_page({"html": "<html></html>"}))
    assert payload.get("warning") == warning, "partial-analysis warning lost before reaching chat agent"
