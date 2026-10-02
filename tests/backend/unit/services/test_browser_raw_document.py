import json
from unittest.mock import MagicMock

import pytest

from backend.src.services import browser


def test_scrape_requests_original_document_including_head_and_landmarks(monkeypatch):
    original = '<html lang="en"><head><title>Example Domain</title><style>p{color:black}</style></head><body><nav>Menu</nav><main>Example</main></body></html>'
    captured = []

    def request(req, **kwargs):
        captured.append(json.loads(req.data))
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps({
            "success": True, "data": {"rawHtml": original, "html": "<p>cleaned article</p>"},
        }).encode()
        return response

    monkeypatch.setattr(browser.urllib.request, "urlopen", request)
    assert browser._scrape_with_firecrawl("https://example.com", "dummy") == original
    assert captured[0]["formats"] == ["rawHtml"]
    assert captured[0]["onlyMainContent"] is False


def test_cleaned_fragment_is_not_a_silent_fallback_for_full_document(monkeypatch):
    response = MagicMock()
    response.__enter__.return_value.read.return_value = b'{"success":true,"data":{"html":"<p>fragment</p>"}}'
    monkeypatch.setattr(browser.urllib.request, "urlopen", lambda *a, **kw: response)
    with pytest.raises(RuntimeError, match="documento HTML completo"):
        browser._scrape_with_firecrawl("https://example.com", "dummy")


@pytest.mark.parametrize("status", [403, 404, 500])
def test_target_error_page_is_not_audited_as_requested_page(monkeypatch, status):
    response = MagicMock()
    response.__enter__.return_value.read.return_value = json.dumps({
        "success": True, "data": {"rawHtml": "<html>Error page</html>", "metadata": {"statusCode": status}},
    }).encode()
    monkeypatch.setattr(browser.urllib.request, "urlopen", lambda *a, **kw: response)
    with pytest.raises(RuntimeError, match="conteúdo não foi auditado"):
        browser._scrape_with_firecrawl("https://example.com", "dummy")
