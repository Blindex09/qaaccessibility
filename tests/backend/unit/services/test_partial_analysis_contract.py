"""Regression: incomplete analysis must not turn into a clean score at the chat boundary."""
import json
from unittest.mock import AsyncMock, patch

from backend.src.services.chat_tools import analyze_page
from backend.src.shared.models import AgentResult


def test_partial_analysis_never_has_conformance_score():
    partial = AgentResult(agent="orchestrator", success=True, data={
        "issues": [], "warning": "Revisor falhou",
        "agent_metrics": [{"agent": "reviewer", "success": False}],
    })
    with (patch("backend.src.services.chat_tools._resolve_and_analyze", new=AsyncMock(return_value=(partial, "<html/>"))),
          patch("backend.src.services.last_analysis_store.set_last_analysis"),
          patch("backend.src.services.last_analyzed_content_store.set_last_analyzed_content")):
        output = json.loads(analyze_page({"html": "<html/>"}))
    assert output["warning"] == "Revisor falhou"
    assert output["complete"] is False
    assert output["score"] is None
    assert output["agent_metrics"][0]["success"] is False
