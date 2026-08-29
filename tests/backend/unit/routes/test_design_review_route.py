from unittest.mock import AsyncMock, patch

from backend.src.shared.models import AgentResult

RISK_FLAG = {
    "id": "risk-1",
    "risk": "Drag-and-drop reordering has no keyboard alternative described.",
    "wcag_criteria": ["2.1.1 Keyboard", "2.5.7 Dragging Movements"],
    "severity": "high",
    "rationale": "The requirement only describes drag handles, no keyboard-based reorder action.",
    "recommendation": "Add a 'Move up/down' button alternative alongside the drag handle.",
}


class TestDesignReviewRoute:
    def test_422_without_requirement_text(self, client):
        resp = client.post("/analyze/design-review", json={"requirement_text": "   "})
        assert resp.status_code == 422

    def test_calls_agent_and_returns_risk_flags(self, client):
        mock = AsyncMock(
            return_value=AgentResult(agent="design_review", success=True, data={"risk_flags": [RISK_FLAG]})
        )
        with patch("backend.src.routes.design_review_route.run_design_review", new=mock):
            resp = client.post(
                "/analyze/design-review",
                json={"requirement_text": "Allow reordering cards via drag-and-drop.", "component_type": "drag-and-drop"},
            )
        assert resp.status_code == 200
        assert resp.json()["agent"] == "design_review"
        assert len(resp.json()["data"]["risk_flags"]) == 1
        mock.assert_called_once_with("Allow reordering cards via drag-and-drop.", "drag-and-drop")

    def test_500_when_agent_fails(self, client):
        mock = AsyncMock(return_value=AgentResult(agent="design_review", success=False, data={}, error="boom"))
        with patch("backend.src.routes.design_review_route.run_design_review", new=mock):
            resp = client.post("/analyze/design-review", json={"requirement_text": "Add a modal."})
        assert resp.status_code == 500
