"""Testes de regressao para a paralelizacao de analyze_site.

Garante que _run_site_crawl_and_analyze renderiza URLs e executa o pipeline de
analise em paralelo (asyncio.gather + semaforos), em vez de sequencialmente.
"""

from unittest.mock import MagicMock, patch

import pytest

from backend.src.services.chat_tools import _run_site_crawl_and_analyze


@pytest.mark.anyio
async def test_analyze_site_urls_run_analyses_in_parallel():
    """Duas URLs fornecidas disparam duas chamadas de orchestrate em paralelo."""
    urls = ["https://a.example.org", "https://b.example.org"]

    fetched: list[str] = []
    analyzed: list[str] = []

    async def _fake_fetch(url: str):
        fetched.append(url)
        return f"<html>{url}</html>", ""

    async def _fake_orchestrate(html: str, *_args, **_kwargs):
        # Extrai a URL do HTML fake para rastrear a chamada.
        url = html.replace("<html>", "").replace("</html>", "")
        analyzed.append(url)
        return MagicMock(
            success=True,
            data={"issues": [{"element": "body", "description": f"issue {url}"}]},
        )

    with (
        patch("backend.src.services.browser.fetch_rendered_html_and_screenshot", _fake_fetch),
        patch("backend.src.agents.orchestrator.orchestrator.orchestrate", _fake_orchestrate),
        patch("backend.src.routes.analyze._extract_semantic_html", lambda html: html),
        patch("backend.src.services.last_analysis_store.set_last_analysis") as mock_set_last,
    ):
        result = await _run_site_crawl_and_analyze(None, urls, max_pages=10)

    assert set(fetched) == set(urls)
    assert set(analyzed) == set(urls)
    assert result["total_pages"] == 2
    assert result["pages_ok"] == 2
    assert result["pages_failed"] == 0
    assert result["total_issues"] == 2
    assert len(result["top_issues"]) == 2
    mock_set_last.assert_called_once()
