from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.src.services import browser


def test_validates_focus_and_accessibility_expectations_without_audio():
    state = {
        "active": {"role": "button", "name": "Abrir detalhes", "visible": True},
        "tree": {
            "role": "WebArea",
            "children": [{"role": "dialog", "name": "Detalhes", "children": []}],
        },
    }

    errors = browser._validate_interaction_expectations(
        state,
        {
            "action": "tab",
            "expect": {"role": "button", "name": "Abrir detalhes", "dialog_name": "Detalhes"},
        },
    )

    assert errors == []


def test_reports_missing_focus_and_live_region():
    errors = browser._validate_interaction_expectations(
        {"active": None, "tree": {"role": "WebArea", "children": []}},
        {"action": "tab", "expect": {"live_text": "Salvo com sucesso"}},
    )

    assert "não deixou um elemento focado" in errors[0]
    assert any("Salvo com sucesso" in error for error in errors)


@pytest.mark.asyncio
async def test_limits_steps_before_opening_browser():
    with patch.object(browser, "get_settings") as settings, patch.object(browser, "async_playwright") as playwright:
        settings.return_value.browserless_ws_url = None
        result = await browser.run_accessibility_interaction_audit("https://example.com", [{}] * 31)

    assert result["status"] == "error"
    assert "30 passos" in result["error"]
    playwright.assert_not_called()


@pytest.mark.asyncio
async def test_falls_back_from_remote_to_local_for_interaction_audit():
    fake_context = MagicMock()
    fake_browser = MagicMock()
    fake_browser.close = AsyncMock()
    fake_pw = MagicMock()
    fake_pw.chromium.connect_over_cdp = AsyncMock(return_value=fake_browser)
    fake_pw.chromium.launch = AsyncMock(return_value=fake_browser)
    playwright_context = MagicMock()
    playwright_context.__aenter__ = AsyncMock(return_value=fake_pw)
    playwright_context.__aexit__ = AsyncMock(return_value=False)

    with (
        patch.object(browser, "get_settings") as settings,
        patch.object(browser, "async_playwright", return_value=playwright_context),
        patch.object(
            browser,
            "_run_interaction_audit_with_browser",
            new=AsyncMock(side_effect=[RuntimeError("remote unavailable"), {"status": "ok", "browser_mode": "local", "steps": []}]),
        ) as run_audit,
    ):
        settings.return_value.browserless_ws_url = "wss://browserless.example"
        result = await browser.run_accessibility_interaction_audit("https://example.com", [{"action": "tab"}])

    assert result["browser_mode"] == "local"
    assert run_audit.await_count == 2
    fake_pw.chromium.connect_over_cdp.assert_awaited_once_with("wss://browserless.example")
    fake_pw.chromium.launch.assert_awaited_once_with(headless=True)
