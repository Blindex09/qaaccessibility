from unittest.mock import AsyncMock, patch

from backend.src.services.screen_reader_verification import (
    ScreenReaderFinding,
    ScreenReaderVerificationResult,
)


class TestScreenReaderRoute:
    def test_returns_empty_findings_when_none_detected(self, client):
        mock = AsyncMock(
            return_value=ScreenReaderVerificationResult(
                url="https://example.com", total_interactive_nodes=3, findings=[],
                nvda_running=False, spoken_findings=0,
            )
        )
        with patch("backend.src.routes.screen_reader_route.verify_screen_reader_announcements", new=mock):
            resp = client.post("/analyze/screen-reader", json={"url": "https://example.com"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_interactive_nodes"] == 3
        assert body["findings"] == []

    def test_returns_findings_and_forwards_speak_via_nvda(self, client):
        finding = ScreenReaderFinding(
            role="button", path="main > button", severity="critical",
            problem="Sem nome acessivel", announcement_preview="button",
        )
        mock = AsyncMock(
            return_value=ScreenReaderVerificationResult(
                url="https://example.com", total_interactive_nodes=1, findings=[finding],
                nvda_running=True, spoken_findings=1,
            )
        )
        with patch("backend.src.routes.screen_reader_route.verify_screen_reader_announcements", new=mock):
            resp = client.post(
                "/analyze/screen-reader", json={"url": "https://example.com", "speak_via_nvda": True}
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["findings"][0]["role"] == "button"
        assert body["nvda_running"] is True
        assert body["spoken_findings"] == 1
        mock.assert_called_once_with("https://example.com", speak_via_nvda=True)
