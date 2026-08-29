"""Tests for the security headers and PII redaction middlewares."""

from unittest.mock import AsyncMock, patch

import pytest
from starlette.testclient import TestClient

from backend.src.security.pii_guard import contains_pii, redact_pii

# ---------- PII Guard unit tests (re-verify existing module) ----------


class TestPIIGuardPatterns:
    """Verify PII detection patterns from the security module."""

    def test_detects_ssn(self):
        assert contains_pii("SSN: 123-45-6789") is True

    def test_detects_cpf(self):
        assert contains_pii("CPF: 123.456.789-09") is True

    def test_detects_email(self):
        assert contains_pii("Contact: user@example.com") is True

    def test_clean_text_returns_false(self):
        assert contains_pii("The page has no alt text.") is False

    def test_redacts_email(self):
        result = redact_pii("Email: user@example.com here")
        assert "user@example.com" not in result
        assert "[REDACTED]" in result

    def test_redacts_multiple(self):
        text = "Email: a@b.com SSN: 123-45-6789"
        result = redact_pii(text)
        assert "a@b.com" not in result
        assert "123-45-6789" not in result


# ---------- Security Headers middleware ----------


class TestSecurityHeadersMiddleware:
    """Ensure every response includes OWASP security headers."""

    @pytest.fixture
    def client(self):
        """Create a test client with the full app middleware stack."""
        # Patch settings to avoid requiring env vars in tests
        mock_settings = AsyncMock()
        mock_settings.llm_api_key = "test-key"
        mock_settings.llm_provider = "openai"
        mock_settings.debug = False
        mock_settings.allowed_origins = ["http://localhost:3000"]
        mock_settings.secret_key = "test-secret"
        mock_settings.max_upload_size_mb = 10
        mock_settings.upload_dir = "./uploads"
        mock_settings.backend_host = "127.0.0.1"
        mock_settings.backend_port = 8001
        mock_settings.qa_api_token = None

        with patch("backend.src.main.get_settings", return_value=mock_settings), \
             patch("backend.src.config.settings.get_settings", return_value=mock_settings):
            from importlib import reload

            import backend.src.main as main_mod
            reload(main_mod)
            yield TestClient(main_mod.app)

    def test_health_has_security_headers(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.headers.get("X-Content-Type-Options") == "nosniff"
        assert response.headers.get("X-Frame-Options") == "DENY"
        assert response.headers.get("X-XSS-Protection") == "1; mode=block"
        assert "default-src" in response.headers.get("Content-Security-Policy", "")
        assert response.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"


def test_private_routes_require_configured_session_token(monkeypatch):
    import backend.src.main as main_mod

    monkeypatch.setattr(main_mod.settings, "qa_api_token", "session-token")
    with TestClient(main_mod.app) as client:
        assert client.get("/settings/").status_code == 401
        assert client.get(
            "/settings/",
            headers={"X-QA-Accessibility-Token": "wrong"},
        ).status_code == 401
        assert client.get(
            "/settings/",
            headers={"X-QA-Accessibility-Token": "session-token"},
        ).status_code == 200
        assert client.get("/health").status_code == 200


# ---------- PII Middleware integration ----------


class TestPIIMiddlewareRecursive:
    """Test the recursive redaction helper used by the middleware."""

    def test_redact_recursive_string(self):
        from backend.src.middleware.pii_middleware import _redact_recursive

        result = _redact_recursive("user@example.com is the contact")
        assert "user@example.com" not in result
        assert "[REDACTED]" in result

    def test_redact_recursive_dict(self):
        from backend.src.middleware.pii_middleware import _redact_recursive

        data = {"email": "test@test.com", "score": 85}
        result = _redact_recursive(data)
        assert "test@test.com" not in result["email"]
        assert result["score"] == 85

    def test_redact_recursive_nested_list(self):
        from backend.src.middleware.pii_middleware import _redact_recursive

        data = [{"description": "Contact: a@b.com"}]
        result = _redact_recursive(data)
        assert "a@b.com" not in result[0]["description"]

    def test_no_pii_unchanged(self):
        from backend.src.middleware.pii_middleware import _redact_recursive

        data = {"message": "No personal data here"}
        result = _redact_recursive(data)
        assert result == data
