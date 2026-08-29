from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.src.main import app

client = TestClient(app)

MOCK_XLSX_BYTES = b"PK\x03\x04fake_xlsx_header"


class TestExportXlsxRoute:
    def test_export_xlsx_success(self):
        with patch(
            "backend.src.routes.export_xlsx.export_issues_xlsx",
            return_value=MOCK_XLSX_BYTES,
        ):
            response = client.post("/export/xlsx", json={
                "url": "https://exemplo.com",
                "issues": [
                    {
                        "id": "issue-001",
                        "guideline": "WCAG 2.2",
                        "criterion": "1.1.1 Non-text Content",
                        "severity": "critical",
                        "element": "img",
                        "description": "Missing alt",
                        "suggestion": "Add alt",
                        "level": "A",
                        "wcag_url": "https://...",
                    }
                ],
            })
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        assert "attachment" in response.headers["content-disposition"]
        assert "exemplo.com" in response.headers["content-disposition"]
        assert response.content == MOCK_XLSX_BYTES

    def test_export_xlsx_empty_issues_returns_400(self):
        response = client.post("/export/xlsx", json={"url": "https://exemplo.com", "issues": []})
        assert response.status_code == 400
        assert "Nenhum issue" in response.json()["detail"]

    def test_export_xlsx_injects_url(self):
        with patch(
            "backend.src.routes.export_xlsx.export_issues_xlsx",
            return_value=MOCK_XLSX_BYTES,
        ) as mock_export:
            client.post("/export/xlsx", json={
                "url": "https://exemplo.com",
                "issues": [{"id": "i1", "severity": "high", "description": "test"}],
            })
        # Verify url was injected into issues before calling exporter
        call_issues = mock_export.call_args[0][0]
        assert call_issues[0]["url"] == "https://exemplo.com"

    def test_export_xlsx_preserves_existing_url(self):
        with patch(
            "backend.src.routes.export_xlsx.export_issues_xlsx",
            return_value=MOCK_XLSX_BYTES,
        ) as mock_export:
            client.post("/export/xlsx", json={
                "url": "https://exemplo.com",
                "issues": [{"id": "i1", "severity": "high", "url": "https://original.com", "description": "test"}],
            })
        call_issues = mock_export.call_args[0][0]
        assert call_issues[0]["url"] == "https://original.com"

    def test_export_xlsx_handles_exporter_failure(self):
        with patch(
            "backend.src.routes.export_xlsx.export_issues_xlsx",
            side_effect=RuntimeError("XLSX generation failed"),
        ):
            response = client.post("/export/xlsx", json={
                "url": "https://exemplo.com",
                "issues": [{"id": "i1", "severity": "high", "description": "test"}],
            })
        assert response.status_code == 500
        assert "Falha ao gerar planilha" in response.json()["detail"]

    def test_export_last_accessibility_statement_pdf_success(self):
        sample_issues = [{"id": "i1", "severity": "high", "description": "test", "criterion": "1.1.1", "element": "img", "suggestion": "fix", "guideline": "WCAG 2.2", "level": "A", "wcag_url": "https://..."}]
        with patch(
            "backend.src.services.last_analysis_store.get_last_analysis",
            return_value=(sample_issues, "https://exemplo.com"),
        ), patch(
            "backend.src.services.accessibility_statement_generator.export_accessibility_statement_pdf",
            return_value=b"%PDF-1.7 mock accessibility statement",
        ):
            response = client.get("/export/last_accessibility_statement_pdf")
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"
        assert "attachment" in response.headers["content-disposition"]
        assert "declaracao_acessibilidade_exemplo.com.pdf" in response.headers["content-disposition"]
        assert response.content == b"%PDF-1.7 mock accessibility statement"

    def test_export_last_accessibility_statement_pdf_empty_cache_returns_400(self):
        with patch(
            "backend.src.services.last_analysis_store.get_last_analysis",
            return_value=([], ""),
        ):
            response = client.get("/export/last_accessibility_statement_pdf")
        assert response.status_code == 400
        assert "Nenhuma auditoria recente" in response.json()["detail"]
