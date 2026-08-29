import json

from backend.src.services.chat_runtime import _extract_result_summary


class TestExtractResultSummaryCounts:
    def test_fix_and_zip_files_counts_total_files(self):
        result = json.dumps({"download_url": "http://x/zip", "total_files": 8})
        summary = _extract_result_summary("fix_and_zip_files", result)
        assert summary == {
            "count": 8,
            "item_singular": "arquivo corrigido",
            "item_plural": "arquivos corrigidos",
        }

    def test_generate_checklist_counts_checklist_items(self):
        result = json.dumps({"checklist": [{"id": "1"}, {"id": "2"}, {"id": "3"}], "url": "https://x"})
        summary = _extract_result_summary("generate_checklist", result)
        assert summary["count"] == 3
        assert summary["item_plural"] == "itens no checklist"

    def test_analyze_page_counts_issues(self):
        result = json.dumps({"issues": [{"id": "1"}], "agent_metrics": []})
        summary = _extract_result_summary("analyze_page", result)
        assert summary["count"] == 1
        assert summary["item_singular"] == "problema de acessibilidade encontrado"

    def test_cross_browser_counts_succeeded_engines(self):
        result = json.dumps({"engines_succeeded": ["chromium", "firefox", "webkit"], "engines_failed": []})
        summary = _extract_result_summary("run_cross_browser_test", result)
        assert summary["count"] == 3

    def test_tool_without_mapping_returns_none(self):
        result = json.dumps({"status": "ok"})
        assert _extract_result_summary("export_xlsx", result) is None

    def test_error_result_returns_none(self):
        result = json.dumps({"error": "algo deu errado"})
        assert _extract_result_summary("fix_and_zip_files", result) is None

    def test_malformed_json_returns_none(self):
        assert _extract_result_summary("fix_and_zip_files", "not json{{{") is None

    def test_missing_field_returns_none(self):
        result = json.dumps({"download_url": "http://x"})
        assert _extract_result_summary("fix_and_zip_files", result) is None


class TestExtractResultSummarySources:
    def test_tavily_search_extracts_sources(self):
        result = json.dumps({
            "success": True,
            "data": {"web": [
                {"title": "WCAG 2.2", "url": "https://www.w3.org/TR/WCAG22/"},
                {"title": "", "url": "https://example.com"},
            ]},
        })
        summary = _extract_result_summary("tavily_search", result)
        assert summary["sources"] == [
            {"title": "WCAG 2.2", "url": "https://www.w3.org/TR/WCAG22/"},
            {"title": "https://example.com", "url": "https://example.com"},
        ]

    def test_exa_search_extracts_sources(self):
        result = json.dumps({"results": [{"title": "AccName", "url": "https://www.w3.org/TR/accname-1.2/"}]})
        summary = _extract_result_summary("exa_search", result)
        assert summary["sources"] == [{"title": "AccName", "url": "https://www.w3.org/TR/accname-1.2/"}]

    def test_deep_research_extracts_urls_from_answer_text(self):
        result = json.dumps({
            "status": "ok",
            "question": "...",
            "answer": "Definido em https://www.w3.org/TR/accname-1.2/ na seção 4.3. "
                      "Veja também https://www.w3.org/TR/accname-1.2/ (mesma URL de novo).",
        })
        summary = _extract_result_summary("run_deep_research", result)
        assert summary["sources"] == [{"title": "https://www.w3.org/TR/accname-1.2/", "url": "https://www.w3.org/TR/accname-1.2/"}]

    def test_deep_research_without_urls_has_no_sources_key(self):
        result = json.dumps({"status": "ok", "question": "...", "answer": "Sem nenhuma URL aqui."})
        summary = _extract_result_summary("run_deep_research", result)
        assert summary is None

    def test_web_search_tool_without_sources_and_without_count_returns_none(self):
        result = json.dumps({"success": True, "data": {"web": []}})
        assert _extract_result_summary("tavily_search", result) is None
