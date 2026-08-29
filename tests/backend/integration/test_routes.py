from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from backend.src.main import app
from backend.src.shared.models import AgentResult

client = TestClient(app)

MOCK_RESULT = AgentResult(
    agent="analyzer",
    success=True,
    data={"issues": []},
)


class TestHealthRoute:
    def test_health_returns_ok(self):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"


class TestAnalyzeUrlRoute:
    def test_analyze_url_success(self):
        with patch(
            "backend.src.routes.analyze.orchestrate",
            new=AsyncMock(return_value=MOCK_RESULT),
        ), patch(
            "backend.src.routes.analyze.fetch_rendered_html_screenshot_and_focus_states",
            new=AsyncMock(return_value=("<html></html>", "fake_screenshot", None)),
        ):
            response = client.post("/analyze/url", json={"url": "https://example.com"})
        assert response.status_code == 200
        assert response.json()["success"] is True

    def test_analyze_url_invalid_url_returns_400(self):
        with patch(
            "backend.src.routes.analyze.fetch_rendered_html_screenshot_and_focus_states",
            new=AsyncMock(side_effect=Exception("Connection refused")),
        ):
            response = client.post("/analyze/url", json={"url": "https://bad-url.test"})
        assert response.status_code == 400


class TestAnalyzeFileRoute:
    def test_analyze_file_success(self):
        with patch(
            "backend.src.routes.analyze.orchestrate",
            new=AsyncMock(return_value=MOCK_RESULT),
        ):
            response = client.post(
                "/analyze/file",
                files={"file": ("index.html", b"<html></html>", "text/html")},
            )
        assert response.status_code == 200
        assert response.json()["success"] is True


class TestAnalyzeProjectRoute:
    def test_analyze_project_success(self):
        with patch(
            "backend.src.routes.analyze.orchestrate",
            new=AsyncMock(return_value=MOCK_RESULT),
        ):
            response = client.post(
                "/analyze/project",
                files=[
                    ("files", ("index.html", b"<h1>Hello</h1>", "text/html")),
                    ("files", ("styles.css", b"body{color:red}", "text/css")),
                ],
            )
        assert response.status_code == 200
        assert response.json()["success"] is True

    def test_analyze_project_no_files_returns_400(self):
        response = client.post("/analyze/project", files=[])
        assert response.status_code in (400, 422)

    def test_analyze_project_unsupported_only_returns_422(self):
        with patch(
            "backend.src.routes.analyze.orchestrate",
            new=AsyncMock(return_value=MOCK_RESULT),
        ):
            response = client.post(
                "/analyze/project",
                files=[
                    ("files", ("readme.md", b"# Hello", "text/plain")),
                ],
            )
        assert response.status_code == 422


class TestFixRoute:
    def test_fix_success(self, sample_issue):
        mock_result = AgentResult(
            agent="fixer",
            success=True,
            data={
                "fixed_html": "<html></html>",
                "changes_summary": ["Added alt text"],
            },
        )
        with patch(
            "backend.src.routes.fix.run_fixer",
            new=AsyncMock(return_value=mock_result),
        ):
            response = client.post(
                "/fix/",
                json={
                    "html_content": "<html></html>",
                    "issues": [sample_issue.model_dump()],
                    "self_healing": False,  # usa run_fixer direto (caminho testado pelo mock)
                },
            )
        assert response.status_code == 200
        assert response.json()["success"] is True


class TestReportRoute:
    def test_report_success(self):
        mock_result = AgentResult(
            agent="reporter",
            success=True,
            data={
                "report_id": "r-1",
                "summary": "All good",
                "score": 95,
                "issues": [],
                "checklist": [],
            },
        )
        with patch(
            "backend.src.routes.report.orchestrate",
            new=AsyncMock(return_value=mock_result),
        ):
            response = client.post("/report/", json={"html_content": "<html></html>"})
        assert response.status_code == 200
        assert response.json()["data"]["score"] == 95
