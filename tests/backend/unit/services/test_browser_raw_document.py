from unittest.mock import MagicMock

import httpx
import pytest

from backend.src.services import browser


def _response(body: dict) -> MagicMock:
    response = MagicMock()
    response.json.return_value = body
    return response


def test_scrape_requests_original_document_including_head_and_landmarks(monkeypatch):
    original = '<html lang="en"><head><title>Example Domain</title><style>p{color:black}</style></head><body><nav>Menu</nav><main>Example</main></body></html>'
    captured = []

    def post(url, **kwargs):
        captured.append(kwargs["json"])
        return _response({"success": True, "data": {"rawHtml": original, "html": "<p>cleaned article</p>"}})

    monkeypatch.setattr(browser.httpx, "post", post)
    assert browser._scrape_with_firecrawl("https://example.com", "dummy") == original
    assert captured[0]["formats"] == ["rawHtml"]
    assert captured[0]["onlyMainContent"] is False


def test_scrape_only_limits_the_connection_not_the_time_the_page_takes_to_render(monkeypatch):
    seen = {}

    def post(url, **kwargs):
        seen["timeout"] = kwargs["timeout"]
        return _response({"success": True, "data": {"rawHtml": "<html>ok</html>"}})

    monkeypatch.setattr(browser.httpx, "post", post)
    browser._scrape_with_firecrawl("https://example.com", "dummy")
    timeout = seen["timeout"]
    assert isinstance(timeout, httpx.Timeout)
    assert timeout.read is None and timeout.write is None and timeout.connect is not None


def test_cleaned_fragment_is_not_a_silent_fallback_for_full_document(monkeypatch):
    monkeypatch.setattr(browser.httpx, "post", lambda *a, **kw: _response({"success": True, "data": {"html": "<p>fragment</p>"}}))
    with pytest.raises(RuntimeError, match="documento HTML completo"):
        browser._scrape_with_firecrawl("https://example.com", "dummy")


@pytest.mark.parametrize("status", [403, 404, 500])
def test_target_error_page_is_not_audited_as_requested_page(monkeypatch, status):
    body = {"success": True, "data": {"rawHtml": "<html>Error page</html>", "metadata": {"statusCode": status}}}
    monkeypatch.setattr(browser.httpx, "post", lambda *a, **kw: _response(body))
    with pytest.raises(RuntimeError, match="conteúdo não foi auditado"):
        browser._scrape_with_firecrawl("https://example.com", "dummy")
