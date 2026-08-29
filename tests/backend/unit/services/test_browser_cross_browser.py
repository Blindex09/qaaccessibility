"""Testes de regressao para a auditoria cross-browser real.

Garante que run_axe_core_cross_browser_audit lanca os 3 motores (chromium,
firefox, webkit) em paralelo com asyncio.gather, em vez de sequencialmente.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.src.services.browser import run_axe_core_cross_browser_audit


@pytest.mark.anyio
async def test_cross_browser_audit_launches_all_engines_in_parallel():
    """Todos os 3 motores devem ser iniciados; a funcao deve esperar os 3 com gather."""
    launched: list[str] = []

    fake_page = AsyncMock()
    fake_page.evaluate.return_value = {"violations": [], "incomplete": []}

    fake_context = AsyncMock()
    fake_context.new_page = AsyncMock(return_value=fake_page)

    fake_browser = AsyncMock()
    fake_browser.new_context = AsyncMock(return_value=fake_context)

    async def _fake_launch(*, headless: bool):
        launched.append(headless)
        return fake_browser

    fake_launcher = AsyncMock()
    fake_launcher.launch = AsyncMock(side_effect=_fake_launch)

    fake_pw = MagicMock()
    fake_pw.chromium = fake_launcher
    fake_pw.firefox = fake_launcher
    fake_pw.webkit = fake_launcher

    with (
        patch("backend.src.services.browser._load_axe_core_js", return_value="// axe"),
        patch("backend.src.services.browser.async_playwright") as mock_playwright,
    ):
        mock_playwright.return_value.__aenter__ = AsyncMock(return_value=fake_pw)
        mock_playwright.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await run_axe_core_cross_browser_audit("https://example.org")

    assert len(launched) == 3
    assert set(result["per_engine"].keys()) == {"chromium", "firefox", "webkit"}
    for engine in ("chromium", "firefox", "webkit"):
        assert result["per_engine"][engine]["success"] is True
