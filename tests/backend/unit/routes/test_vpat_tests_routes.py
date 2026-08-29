from unittest.mock import AsyncMock, patch

from backend.src.shared.models import AgentResult

_ISSUE = {
    "id": "p-1",
    "guideline": "WCAG 2.2",
    "criterion": "1.1.1 Non-text Content",
    "severity": "critical",
    "element": "img",
    "description": "img sem alt",
    "suggestion": "adicionar alt",
}


class TestVpatRoute:
    def test_422_without_issues_or_html(self, client):
        resp = client.post("/analyze/vpat", json={})
        assert resp.status_code == 422

    def test_issues_path_calls_agent(self, client):
        mock = AsyncMock(return_value=AgentResult(agent="vpat_reporter", success=True, data={"vpat": {}}))
        with patch("backend.src.routes.vpat_route.run_vpat_reporter", new=mock):
            resp = client.post("/analyze/vpat", json={"issues": [_ISSUE], "product_name": "App"})
        assert resp.status_code == 200
        assert resp.json()["agent"] == "vpat_reporter"
        mock.assert_called_once()

    def test_html_path_calls_orchestrate(self, client):
        mock = AsyncMock(return_value=AgentResult(agent="vpat_reporter", success=True, data={"vpat": {}}))
        with patch("backend.src.routes.vpat_route.orchestrate", new=mock):
            resp = client.post("/analyze/vpat", json={"html_content": "<img src=x>", "target": "u"})
        assert resp.status_code == 200
        mock.assert_called_once()
        # task_type VPAT repassado
        assert mock.call_args.args[1].value == "vpat"


class TestTestsRoute:
    def test_422_without_issues_or_html(self, client):
        resp = client.post("/analyze/tests", json={})
        assert resp.status_code == 422

    def test_issues_path_calls_agent(self, client):
        mock = AsyncMock(return_value=AgentResult(agent="test_generator", success=True, data={"suite": {}}))
        with patch("backend.src.routes.tests_route.run_test_generator", new=mock):
            resp = client.post("/analyze/tests", json={"issues": [_ISSUE], "target": "file.html"})
        assert resp.status_code == 200
        assert resp.json()["agent"] == "test_generator"
        mock.assert_called_once()

    def test_html_path_calls_orchestrate(self, client):
        mock = AsyncMock(return_value=AgentResult(agent="test_generator", success=True, data={"suite": {}}))
        with patch("backend.src.routes.tests_route.orchestrate", new=mock):
            resp = client.post("/analyze/tests", json={"html_content": "<img src=x>"})
        assert resp.status_code == 200
        mock.assert_called_once()
        assert mock.call_args.args[1].value == "tests"
