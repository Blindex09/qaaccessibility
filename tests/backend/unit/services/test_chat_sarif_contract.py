import json

from backend.src.services.chat_tools import _EXPORT_SARIF_SCHEMA, export_sarif_tool
from backend.src.services.last_analysis_store import set_last_analysis
from backend.src.services.sarif_exporter import export_to_sarif
from backend.src.services.session_context import reset_current_session, set_current_session
from backend.src.shared.models import AccessibilityIssue


def issue(url):
    return AccessibilityIssue(id="language", guideline="WCAG 2.2", criterion="3.1.1", severity="high",
                              element="<html>", description="Idioma ausente", suggestion="Declare o idioma real", url=url)


def test_sarif_preserves_each_page_uri():
    urls = ["https://example.com/home.html", "https://example.com/survey.html"]
    doc = export_to_sarif([issue(url) for url in urls], "Crawl / Lista de URLs")
    assert [r["locations"][0]["physicalLocation"]["artifactLocation"]["uri"]
            for r in doc["runs"][0]["results"]] == urls


def test_chat_sarif_link_uses_only_current_conversation_cache(monkeypatch, tmp_path):
    from backend.src.services import last_analysis_store

    monkeypatch.setattr(last_analysis_store, "get_cache_filepath", lambda session_id=None: str(tmp_path / "analysis.json"))
    monkeypatch.setattr(last_analysis_store, "_sessions", {})
    token = set_current_session("sarif-contract-empty")
    try:
        assert "error" in json.loads(export_sarif_tool({}))
        set_last_analysis([issue("https://example.com/home.html").model_dump()], "https://example.com/home.html")
        result = json.loads(export_sarif_tool({}))
        assert result["download_url"].endswith("/export/last_sarif")
        assert result["format"] == "SARIF 2.1.0"
    finally:
        reset_current_session(token)
    assert _EXPORT_SARIF_SCHEMA["parameters"]["required"] == ["pre_exec_msg"]
