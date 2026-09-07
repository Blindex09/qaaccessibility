import io
import zipfile
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from backend.src.main import app

client = TestClient(app)


def _success_result():
    return {
        "agent": "agent_project_auditor",
        "success": True,
        "data": {
            "findings": [
                {
                    "id": "F-1",
                    "category": "recovery",
                    "severity": "high",
                    "confidence": "high",
                    "file": "src/agent.py",
                    "evidence": "no timeout handling",
                    "description": "Tool failures are not recovered",
                    "impact": "The agent can remain stuck",
                    "recommendation": "Add bounded retries and a terminal failure state",
                }
            ],
            "files_analyzed": ["src/agent.py"],
            "skipped": {},
        },
        "error": None,
    }


@patch("backend.src.routes.analyze.audit_agent_project", new_callable=AsyncMock)
def test_agent_project_route_accepts_python_and_markdown(mock_audit):
    mock_audit.return_value = _success_result()
    response = client.post(
        "/analyze/agent-project",
        files=[
            ("files", ("src/agent.py", b"def run(): pass", "text/x-python")),
            ("files", ("README.md", b"Agent", "text/markdown")),
        ],
    )

    assert response.status_code == 200
    assert response.json()["data"]["findings"][0]["category"] == "recovery"
    selected = mock_audit.await_args.args[0]
    assert [name for name, _ in selected] == ["src/agent.py", "README.md"]


@patch("backend.src.routes.analyze.audit_agent_project", new_callable=AsyncMock)
def test_agent_project_zip_route_does_not_extract_to_disk(mock_audit):
    mock_audit.return_value = _success_result()
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as project:
        project.writestr("src/agent.py", "def run(): pass")
        project.writestr(".venv/lib.py", "should be ignored")
    archive.seek(0)

    response = client.post(
        "/analyze/agent-project/zip",
        files={"file": ("project.zip", archive, "application/zip")},
    )

    assert response.status_code == 200
    selected = mock_audit.await_args.args[0]
    assert [name for name, _ in selected] == ["src/agent.py"]


def test_agent_project_route_rejects_empty_upload_list():
    response = client.post("/analyze/agent-project", files=[])

    # FastAPI valida a lista multipart antes de entrar na função da rota.
    assert response.status_code == 422
