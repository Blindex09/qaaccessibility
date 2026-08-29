from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.src.main import app
from backend.src.shared.models import AgentResult

client = TestClient(app)

@pytest.mark.asyncio
async def test_fix_route_with_self_healing_enabled():
    mock_self_healing = AsyncMock(return_value=(
        "<html><body>fixed</body></html>",
        ["Fixed image"],
        [{"id": "issue-1", "fixed_element_html": "<img>"}]
    ))

    payload = {
        "html_content": "<html><body><img></body></html>",
        "issues": [
            {
                "id": "issue-1",
                "guideline": "WCAG 2.2",
                "criterion": "alt",
                "severity": "high",
                "element": "img",
                "description": "Missing alt",
                "suggestion": "Add alt",
            }
        ],
        "self_healing": True
    }

    with patch("backend.src.services.self_healing.run_self_healing_loop", mock_self_healing):
        response = client.post("/fix/", json=payload)

    assert response.status_code == 200
    res_json = response.json()
    assert res_json["success"] is True
    assert res_json["agent"] == "fixer"
    assert res_json["data"]["fixed_html"] == "<html><body>fixed</body></html>"
    assert res_json["data"]["changes_summary"] == ["Fixed image"]

    mock_self_healing.assert_called_once()


@pytest.mark.asyncio
async def test_fix_route_with_self_healing_disabled():
    mock_run_fixer = AsyncMock(return_value=AgentResult(
        agent="fixer",
        success=True,
        data={
            "fixed_html": "<html><body>fixed output</body></html>",
            "changes_summary": ["Fixed output"],
            "enriched_issues": []
        }
    ))

    payload = {
        "html_content": "<html><body><img></body></html>",
        "issues": [
            {
                "id": "issue-1",
                "guideline": "WCAG 2.2",
                "criterion": "alt",
                "severity": "high",
                "element": "img",
                "description": "Missing alt",
                "suggestion": "Add alt",
            }
        ],
        "self_healing": False
    }

    with patch("backend.src.routes.fix.run_fixer", mock_run_fixer):
        response = client.post("/fix/", json=payload)

    assert response.status_code == 200
    res_json = response.json()
    assert res_json["success"] is True
    assert res_json["data"]["fixed_html"] == "<html><body>fixed output</body></html>"

    mock_run_fixer.assert_called_once()


@pytest.mark.asyncio
async def test_fix_route_self_healing_exception_returns_failure():
    mock_self_healing = AsyncMock(side_effect=RuntimeError("Self-healing crashed"))

    payload = {
        "html_content": "<html><body><img></body></html>",
        "issues": [
            {
                "id": "issue-1",
                "guideline": "WCAG 2.2",
                "criterion": "alt",
                "severity": "high",
                "element": "img",
                "description": "Missing alt",
                "suggestion": "Add alt",
            }
        ],
        "self_healing": True
    }

    with patch("backend.src.services.self_healing.run_self_healing_loop", mock_self_healing):
        response = client.post("/fix/", json=payload)

    assert response.status_code == 200
    res_json = response.json()
    assert res_json["success"] is False
    assert "Self-healing crashed" in res_json["error"]
