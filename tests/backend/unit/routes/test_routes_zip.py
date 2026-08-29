import io
import json
import zipfile
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from backend.src.main import app

client = TestClient(app)


class TestProjectZipRoutes:
    @patch("backend.src.routes.analyze.orchestrate", new_callable=AsyncMock)
    def test_analyze_project_zip_success(self, mock_orchestrate):
        # Mock orchestrate response
        mock_orchestrate.return_value = {
            "agent": "orchestrator",
            "success": True,
            "data": {
                "issues": [
                    {
                        "id": "react-1",
                        "guideline": "WCAG 2.2",
                        "criterion": "1.1.1 Non-text Content",
                        "severity": "critical",
                        "element": "<img>",
                        "description": "Alt tag missing",
                        "suggestion": "Add alt tag",
                        "url": "index.html"
                    }
                ]
            }
        }

        # Create a dummy zip in memory
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("index.html", "<html><body><img src='logo.png'></body></html>")
            z.writestr("ignored_folder/node_modules/dummy.js", "console.log('ignore')")

        zip_buffer.seek(0)

        response = client.post(
            "/analyze/project/zip",
            files={"file": ("project.zip", zip_buffer, "application/zip")}
        )

        assert response.status_code == 200
        res_json = response.json()
        assert res_json["success"] is True
        assert res_json["data"]["issues"][0]["url"] == "index.html"
        mock_orchestrate.assert_called_once()

    @patch("backend.src.services.self_healing.run_self_healing_loop", new_callable=AsyncMock)
    def test_fix_project_zip_success(self, mock_self_healing):
        # Mock self healing response
        mock_self_healing.return_value = ("<html><body><img src='logo.png' alt='logo'></body></html>", ["Fixed alt tag"], [])

        # Create a dummy zip in memory
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("index.html", "<html><body><img src='logo.png'></body></html>")

        zip_buffer.seek(0)

        issues = [
            {
                "id": "react-1",
                "guideline": "WCAG 2.2",
                "criterion": "1.1.1 Non-text Content",
                "severity": "critical",
                "element": "<img>",
                "description": "Alt tag missing",
                "suggestion": "Add alt tag",
                "url": "index.html"
            }
        ]

        response = client.post(
            "/fix/project/zip",
            files={"file": ("project.zip", zip_buffer, "application/zip")},
            data={
                "issues": json.dumps(issues),
                "self_healing": "true"
            }
        )

        assert response.status_code == 200
        res_json = response.json()
        assert res_json["success"] is True
        assert "qa-project-fixed" in res_json["data"]["zip_filename"]
        assert len(res_json["data"]["changes_summary"]) == 1
        assert res_json["data"]["changes_summary"][0] == "[index.html] Fixed alt tag"
