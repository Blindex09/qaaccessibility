from unittest.mock import AsyncMock, patch

from backend.src.services.screen_reader_verification import (
    ScreenReaderFinding,
    ScreenReaderVerificationResult,
)


class TestScreenReaderRoute:
    def test_returns_empty_findings_when_none_detected(self, client):
        mock = AsyncMock(return_value=ScreenReaderVerificationResult(url="https://example.com", total_interactive_nodes=3))
        with patch("backend.src.routes.screen_reader_route.verify_screen_reader_announcements", new=mock):
            resp = client.post("/analyze/screen-reader", json={"url": "https://example.com"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_interactive_nodes"] == 3
        assert body["findings"] == []

    def test_returns_findings_without_audio_integration(self, client):
        finding = ScreenReaderFinding(
            role="button", path="main > button", severity="critical",
            problem="Sem nome acessivel", announcement_preview="button",
        )
        mock = AsyncMock(
            return_value=ScreenReaderVerificationResult(
                url="https://example.com", total_interactive_nodes=1, findings=[finding],
            )
        )
        with patch("backend.src.routes.screen_reader_route.verify_screen_reader_announcements", new=mock):
            resp = client.post("/analyze/screen-reader", json={"url": "https://example.com"})
        assert resp.status_code == 200
        assert resp.json()["findings"][0]["role"] == "button"
        mock.assert_called_once_with("https://example.com")

    def test_forwards_declarative_interaction_steps(self, client):
        mock = AsyncMock(
            return_value=ScreenReaderVerificationResult(
                url="https://example.com", total_interactive_nodes=1,
                interaction_steps=[{"index": 0, "action": "tab", "ok": True}],
            )
        )
        steps = [{"action": "tab", "expect": {"role": "button"}}]
        with patch("backend.src.routes.screen_reader_route.verify_screen_reader_announcements", new=mock):
            resp = client.post("/analyze/screen-reader", json={"url": "https://example.com", "interaction_steps": steps})

        assert resp.status_code == 200
        assert resp.json()["interaction_steps"][0]["ok"] is True
        mock.assert_called_once_with("https://example.com", interaction_steps=steps)
