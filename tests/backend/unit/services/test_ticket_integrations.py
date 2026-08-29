"""Testes do ticket_integrations — criação de tickets no Jira e Azure DevOps
via REST API real (endpoints e formatos pesquisados na documentação oficial,
2026-08-27 -- ver docstring do módulo).

Mesmo padrão de test_github_service.py: simulação (credenciais ausentes),
sucesso, erro HTTP e exceção de rede, sem acionar rede real (requests
mockado)."""

from unittest.mock import patch

from backend.src.services import ticket_integrations


def _fake_response(status_code: int, json_data: dict, text: str = "") -> object:
    return type(
        "FakeResponse",
        (),
        {"status_code": status_code, "json": staticmethod(lambda: json_data), "text": text},
    )


class TestCreateJiraIssue:
    def test_simulates_when_credentials_missing(self, monkeypatch):
        for var in ("JIRA_BASE_URL", "JIRA_EMAIL", "JIRA_API_TOKEN", "JIRA_PROJECT_KEY"):
            monkeypatch.delenv(var, raising=False)

        result = ticket_integrations.create_jira_issue(summary="[A11Y] bug", description="descricao")

        assert result["status"] == "simulated"
        assert result["provider"] == "jira"
        assert "MOCK-1" in result["issue_key"]

    def test_creates_on_http_201(self):
        fake = _fake_response(201, {"key": "PROJ-42"})
        with patch("backend.src.services.ticket_integrations.requests.post", return_value=fake) as mock_post:
            result = ticket_integrations.create_jira_issue(
                summary="[A11Y] bug",
                description="descricao",
                severity="critical",
                base_url="https://acme.atlassian.net",
                email="a@acme.com",
                api_token="tok",
                project_key="PROJ",
            )

        assert result["status"] == "created"
        assert result["issue_key"] == "PROJ-42"
        assert result["issue_url"] == "https://acme.atlassian.net/browse/PROJ-42"
        assert mock_post.call_args.args[0] == "https://acme.atlassian.net/rest/api/2/issue"
        assert mock_post.call_args.kwargs["auth"] == ("a@acme.com", "tok")
        sent_payload = mock_post.call_args.kwargs["json"]
        assert sent_payload["fields"]["priority"]["name"] == "Highest"
        assert sent_payload["fields"]["project"]["key"] == "PROJ"

    def test_maps_severity_to_jira_priority(self):
        fake = _fake_response(201, {"key": "PROJ-1"})
        for severity, expected_priority in (
            ("critical", "Highest"), ("high", "High"), ("medium", "Medium"), ("low", "Low"),
        ):
            with patch("backend.src.services.ticket_integrations.requests.post", return_value=fake) as mock_post:
                ticket_integrations.create_jira_issue(
                    summary="s", description="d", severity=severity,
                    base_url="https://acme.atlassian.net", email="a@acme.com", api_token="tok", project_key="PROJ",
                )
            assert mock_post.call_args.kwargs["json"]["fields"]["priority"]["name"] == expected_priority

    def test_returns_error_on_non_201(self):
        fake = _fake_response(400, {}, text="Field 'project' is required")
        with patch("backend.src.services.ticket_integrations.requests.post", return_value=fake):
            result = ticket_integrations.create_jira_issue(
                summary="s", description="d",
                base_url="https://acme.atlassian.net", email="a@acme.com", api_token="tok", project_key="PROJ",
            )

        assert result["status"] == "error"
        assert result["status_code"] == 400
        assert "project" in result["error"]

    def test_returns_error_on_connection_exception(self):
        with patch(
            "backend.src.services.ticket_integrations.requests.post",
            side_effect=ConnectionError("network down"),
        ):
            result = ticket_integrations.create_jira_issue(
                summary="s", description="d",
                base_url="https://acme.atlassian.net", email="a@acme.com", api_token="tok", project_key="PROJ",
            )

        assert result["status"] == "error"
        assert "network down" in result["error"]

    def test_uses_env_vars_when_params_omitted(self, monkeypatch):
        monkeypatch.setenv("JIRA_BASE_URL", "https://env.atlassian.net")
        monkeypatch.setenv("JIRA_EMAIL", "env@acme.com")
        monkeypatch.setenv("JIRA_API_TOKEN", "envtoken")
        monkeypatch.setenv("JIRA_PROJECT_KEY", "ENV")

        fake = _fake_response(201, {"key": "ENV-1"})
        with patch("backend.src.services.ticket_integrations.requests.post", return_value=fake) as mock_post:
            result = ticket_integrations.create_jira_issue(summary="s", description="d")

        assert result["status"] == "created"
        assert mock_post.call_args.args[0] == "https://env.atlassian.net/rest/api/2/issue"


class TestCreateAzureDevOpsWorkItem:
    def test_simulates_when_credentials_missing(self, monkeypatch):
        for var in ("AZURE_DEVOPS_ORG", "AZURE_DEVOPS_PROJECT", "AZURE_DEVOPS_PAT"):
            monkeypatch.delenv(var, raising=False)

        result = ticket_integrations.create_azure_devops_work_item(title="[A11Y] bug", description="descricao")

        assert result["status"] == "simulated"
        assert result["provider"] == "azure_devops"

    def test_creates_on_http_200(self):
        fake = _fake_response(200, {"id": 123})
        with patch("backend.src.services.ticket_integrations.requests.post", return_value=fake) as mock_post:
            result = ticket_integrations.create_azure_devops_work_item(
                title="[A11Y] bug", description="descricao", severity="high",
                organization="acme", project="proj", personal_access_token="pat",
            )

        assert result["status"] == "created"
        assert result["work_item_id"] == 123
        assert result["work_item_url"] == "https://dev.azure.com/acme/proj/_workitems/edit/123"
        assert mock_post.call_args.args[0] == "https://dev.azure.com/acme/proj/_apis/wit/workitems/$Bug?api-version=7.1"
        assert mock_post.call_args.kwargs["auth"] == ("", "pat")
        assert mock_post.call_args.kwargs["headers"]["Content-Type"] == "application/json-patch+json"
        patch_doc = mock_post.call_args.kwargs["json"]
        titles = {op["path"]: op["value"] for op in patch_doc}
        assert titles["/fields/System.Title"] == "[A11Y] bug"
        assert titles["/fields/Microsoft.VSTS.Common.Severity"] == "2 - High"

    def test_only_sets_severity_field_for_bug_type(self):
        fake = _fake_response(200, {"id": 1})
        with patch("backend.src.services.ticket_integrations.requests.post", return_value=fake) as mock_post:
            ticket_integrations.create_azure_devops_work_item(
                title="t", description="d", organization="acme", project="proj",
                personal_access_token="pat", work_item_type="Task",
            )
        patch_doc = mock_post.call_args.kwargs["json"]
        paths = [op["path"] for op in patch_doc]
        assert "/fields/Microsoft.VSTS.Common.Severity" not in paths

    def test_returns_error_on_non_2xx(self):
        fake = _fake_response(401, {}, text="Unauthorized")
        with patch("backend.src.services.ticket_integrations.requests.post", return_value=fake):
            result = ticket_integrations.create_azure_devops_work_item(
                title="t", description="d", organization="acme", project="proj", personal_access_token="bad",
            )

        assert result["status"] == "error"
        assert result["status_code"] == 401

    def test_returns_error_on_connection_exception(self):
        with patch(
            "backend.src.services.ticket_integrations.requests.post",
            side_effect=ConnectionError("network down"),
        ):
            result = ticket_integrations.create_azure_devops_work_item(
                title="t", description="d", organization="acme", project="proj", personal_access_token="pat",
            )

        assert result["status"] == "error"
        assert "network down" in result["error"]

    def test_uses_env_vars_when_params_omitted(self, monkeypatch):
        monkeypatch.setenv("AZURE_DEVOPS_ORG", "envorg")
        monkeypatch.setenv("AZURE_DEVOPS_PROJECT", "envproj")
        monkeypatch.setenv("AZURE_DEVOPS_PAT", "envpat")

        fake = _fake_response(200, {"id": 9})
        with patch("backend.src.services.ticket_integrations.requests.post", return_value=fake) as mock_post:
            result = ticket_integrations.create_azure_devops_work_item(title="t", description="d")

        assert result["status"] == "created"
        assert "envorg/envproj" in mock_post.call_args.args[0]
