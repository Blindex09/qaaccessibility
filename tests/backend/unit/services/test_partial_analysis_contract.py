"""Regression: incomplete analysis must not turn into a clean score at the chat boundary."""
import json
from unittest.mock import AsyncMock, patch

import pytest

from backend.src.services.chat_tools import _observed_page_structure, _resolve_and_analyze, analyze_page
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
    assert "score" not in output  # nenhuma nota numérica, nem em análise completa
    assert output["agent_metrics"][0]["success"] is False


@pytest.mark.asyncio
async def test_original_dom_facts_reach_narrator_even_when_no_issue_is_reported():
    original = '<html lang="en"><title>Notice</title><body><p>Short notice.</p></body></html>'
    successful = AgentResult(agent="orchestrator", success=True, data={"issues": []})
    with patch("backend.src.agents.orchestrator.orchestrator.orchestrate", new=AsyncMock(return_value=successful)) as pipeline:
        result, content = await _resolve_and_analyze(original, "", only_agents=["wcag_semantics"])
    assert pipeline.call_args.kwargs["source_document"] == original
    with (
        patch("backend.src.services.chat_tools._resolve_and_analyze", new=AsyncMock(return_value=(result, content))),
        patch("backend.src.services.last_analysis_store.set_last_analysis"),
        patch("backend.src.services.last_analyzed_content_store.set_last_analyzed_content"),
    ):
        output = json.loads(analyze_page({"html": original}))
    assert output["observed_structure"]["h1_count"] == 0
    assert output["observed_structure"]["headings"] == []
    assert output["observed_structure"]["lang"] == "en"


def test_heading_counts_are_literal_not_whether_a_heading_is_required():
    facts = _observed_page_structure('<html><body><h1>Title</h1><h3>Detail</h3></body></html>')
    assert facts["h1_count"] == 1
    assert facts["headings"] == [{"level": 1, "text": "Title"}, {"level": 3, "text": "Detail"}]
