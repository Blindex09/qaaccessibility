"""Tests for SSRF validation, upload size limits, and file count limits."""
import io
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.src.main import app
from backend.src.routes.analyze import _validate_url_ssrf


@pytest.fixture
def client():
    return TestClient(app)


class TestSSRFValidation:
    """Tests for _validate_url_ssrf — blocks private IPs and non-HTTP protocols."""

    def test_rejects_file_protocol(self):
        with pytest.raises(Exception) as exc_info:
            _validate_url_ssrf("file:///etc/passwd")
        assert "Protocolo não suportado" in str(exc_info.value.detail)

    def test_rejects_ftp_protocol(self):
        with pytest.raises(Exception) as exc_info:
            _validate_url_ssrf("ftp://internal-server/data")
        assert "Protocolo não suportado" in str(exc_info.value.detail)

    def test_rejects_localhost(self):
        with pytest.raises(Exception) as exc_info:
            _validate_url_ssrf("http://localhost:8080/admin")
        assert "localhost" in str(exc_info.value.detail).lower()

    def test_rejects_zero_address(self):
        with pytest.raises(Exception) as exc_info:
            _validate_url_ssrf("http://0.0.0.0:8080/admin")
        assert "localhost" in str(exc_info.value.detail).lower() or "internas" in str(exc_info.value.detail).lower()

    def test_rejects_127_ip(self):
        with pytest.raises(Exception) as exc_info:
            _validate_url_ssrf("http://127.0.0.1:8080/admin")
        assert "internas" in str(exc_info.value.detail).lower()

    def test_rejects_private_10_range(self):
        with pytest.raises(Exception) as exc_info:
            _validate_url_ssrf("http://10.0.0.5/internal")
        assert "internas" in str(exc_info.value.detail).lower()

    def test_rejects_private_172_range(self):
        with pytest.raises(Exception) as exc_info:
            _validate_url_ssrf("http://172.16.0.1/")
        assert "internas" in str(exc_info.value.detail).lower()

    def test_rejects_private_192_range(self):
        with pytest.raises(Exception) as exc_info:
            _validate_url_ssrf("http://192.168.1.1/")
        assert "internas" in str(exc_info.value.detail).lower()

    def test_rejects_empty_hostname(self):
        with pytest.raises(Exception) as exc_info:
            _validate_url_ssrf("http://")
        assert "hostname" in str(exc_info.value.detail).lower()

    def test_accepts_valid_external_url(self):
        # Should not raise — google.com is a valid external URL
        _validate_url_ssrf("https://www.google.com")

    def test_accepts_http_protocol(self):
        _validate_url_ssrf("http://www.example.com")


class TestUploadSizeLimits:
    """Tests for file upload size and count limits."""

    def test_file_too_large_returns_413(self, client):
        """A file larger than _MAX_BYTES_PER_FILE should be rejected."""
        # 70 KB file — exceeds 60 KB limit
        large_content = b"a" * 70_000
        response = client.post(
            "/analyze/file",
            files={"file": ("large.html", io.BytesIO(large_content), "text/html")},
        )
        assert response.status_code == 413
        assert "limite" in response.json()["detail"].lower()

    def test_file_within_limit_passes(self, client):
        """A file within size limits should be accepted (mocking orchestrate)."""
        small_content = b"<html><body><p>OK</p></body></html>"
        with patch(
            "backend.src.routes.analyze.orchestrate",
            new_callable=AsyncMock,
            return_value={"agent": "orchestrator", "success": True, "data": {"issues": []}},
        ):
            response = client.post(
                "/analyze/file",
                files={"file": ("small.html", io.BytesIO(small_content), "text/html")},
            )
        # Should not be 413
        assert response.status_code != 413

    def test_project_too_many_files_returns_413(self, client):
        """More than 200 files should be rejected."""
        files = []
        for i in range(201):
            files.append(("files", (f"file_{i}.html", io.BytesIO(b"<p>x</p>"), "text/html")))
        response = client.post("/analyze/project", files=files)
        assert response.status_code == 413
        assert "200" in response.json()["detail"]

    def test_project_empty_returns_400(self, client):
        """Empty file list should return 400."""
        response = client.post("/analyze/project", files=[])
        assert response.status_code in (400, 422)


class TestCrawlSSRFProtection:
    """Tests that the crawl endpoint also validates URLs against SSRF."""

    def test_crawl_rejects_localhost(self, client):
        response = client.post(
            "/analyze/crawl",
            json={"url": "http://localhost:8080", "max_pages": 5},
        )
        assert response.status_code == 400
        detail = response.json()["detail"]
        assert "localhost" in detail.lower() or "internas" in detail.lower()

    def test_crawl_rejects_private_ip(self, client):
        response = client.post(
            "/analyze/crawl",
            json={"url": "http://192.168.1.1/", "max_pages": 5},
        )
        assert response.status_code == 400
