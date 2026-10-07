from unittest.mock import patch


def test_cached_sarif_is_a_downloadable_file_with_page_urls(client, sample_issue):
    urls = ["https://example.com/home.html", "https://example.com/survey.html"]
    issues = [sample_issue.model_copy(update={"url": url}).model_dump() for url in urls]
    with patch("backend.src.services.last_analysis_store.get_last_analysis", return_value=(issues, "Crawl / Lista de URLs")):
        response = client.get("/export/last_sarif?conversation_id=sarif-route-test")
    assert response.status_code == 200
    assert response.headers["content-disposition"] == 'attachment; filename="qa-accessibility.sarif"'
    doc = response.json()
    assert doc["version"] == "2.1.0"
    assert [r["locations"][0]["physicalLocation"]["artifactLocation"]["uri"]
            for r in doc["runs"][0]["results"]] == urls
