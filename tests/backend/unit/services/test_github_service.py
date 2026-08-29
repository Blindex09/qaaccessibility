"""Testes do github_service — criação de Issues no GitHub via REST API.

Valida os três caminhos: simulação (credenciais ausentes), sucesso (HTTP 201)
e erro (HTTP não-201), sem acionar rede real (requests mockado).
"""

from unittest.mock import patch

from backend.src.services import github_service


def test_create_github_issue_simulates_when_credentials_missing(monkeypatch):
    monkeypatch.delenv("GITHUB_OWNER", raising=False)
    monkeypatch.delenv("GITHUB_REPO", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    result = github_service.create_github_issue(
        title="[A11Y] WCAG 1.1.1 - Imagem sem alt",
        body="descricao da violacao",
    )

    assert result["status"] == "simulated"
    assert "mock-1" in result["issue_url"]
    assert result["title"] == "[A11Y] WCAG 1.1.1 - Imagem sem alt"


def test_create_github_issue_creates_on_http_201():
    fake_response = type(
        "FakeResponse",
        (),
        {
            "status_code": 201,
            "json": staticmethod(lambda: {"html_url": "https://github.com/o/r/issues/42", "number": 42}),
            "text": "",
        },
    )
    with patch("backend.src.services.github_service.requests.post", return_value=fake_response):
        result = github_service.create_github_issue(
            title="[A11Y] bug",
            body="body",
            repo_owner="o",
            repo_name="r",
            token="tok",
        )

    assert result["status"] == "created"
    assert result["issue_url"] == "https://github.com/o/r/issues/42"
    assert result["number"] == 42


def test_create_github_issue_returns_error_on_non_201():
    fake_response = type(
        "FakeResponse",
        (),
        {
            "status_code": 422,
            "json": staticmethod(lambda: {}),
            "text": "Validation failed",
        },
    )
    with patch("backend.src.services.github_service.requests.post", return_value=fake_response):
        result = github_service.create_github_issue(
            title="t",
            body="b",
            repo_owner="o",
            repo_name="r",
            token="tok",
        )

    assert result["status"] == "error"
    assert result["status_code"] == 422
    assert "Validation failed" in result["error"]


def test_create_github_issue_returns_error_on_connection_exception():
    with patch(
        "backend.src.services.github_service.requests.post",
        side_effect=ConnectionError("network down"),
    ):
        result = github_service.create_github_issue(
            title="t",
            body="b",
            repo_owner="o",
            repo_name="r",
            token="tok",
        )

    assert result["status"] == "error"
    assert "network down" in result["error"]


def test_create_github_issue_uses_env_vars_when_params_omitted(monkeypatch):
    monkeypatch.setenv("GITHUB_OWNER", "envowner")
    monkeypatch.setenv("GITHUB_REPO", "envrepo")
    monkeypatch.setenv("GITHUB_TOKEN", "envtoken")

    fake_response = type(
        "FakeResponse",
        (),
        {
            "status_code": 201,
            "json": staticmethod(lambda: {"html_url": "u", "number": 1}),
            "text": "",
        },
    )
    with patch("backend.src.services.github_service.requests.post", return_value=fake_response) as mock_post:
        result = github_service.create_github_issue(title="t", body="b")

    assert result["status"] == "created"
    called_url = mock_post.call_args.args[0]
    assert "envowner/envrepo" in called_url


def test_create_github_issue_sends_default_labels_when_none_provided():
    fake_response = type(
        "FakeResponse",
        (),
        {
            "status_code": 201,
            "json": staticmethod(lambda: {"html_url": "u", "number": 1}),
            "text": "",
        },
    )
    with patch("backend.src.services.github_service.requests.post", return_value=fake_response) as mock_post:
        github_service.create_github_issue(
            title="t",
            body="b",
            repo_owner="o",
            repo_name="r",
            token="tok",
        )

    sent_payload = mock_post.call_args.kwargs["json"]
    assert sent_payload["labels"] == ["accessibility", "automated-audit"]


def test_create_github_issue_sends_custom_labels_when_provided():
    fake_response = type(
        "FakeResponse",
        (),
        {
            "status_code": 201,
            "json": staticmethod(lambda: {"html_url": "u", "number": 1}),
            "text": "",
        },
    )
    with patch("backend.src.services.github_service.requests.post", return_value=fake_response) as mock_post:
        github_service.create_github_issue(
            title="t",
            body="b",
            repo_owner="o",
            repo_name="r",
            token="tok",
            labels=["wcag", "1.1.1"],
        )

    sent_payload = mock_post.call_args.kwargs["json"]
    assert sent_payload["labels"] == ["wcag", "1.1.1"]
