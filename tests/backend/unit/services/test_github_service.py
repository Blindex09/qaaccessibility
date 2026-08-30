"""Testes do github_service — criação de Issues no GitHub via REST API.

Valida os três caminhos: credenciais ausentes (erro explícito, sem URL
inventada), sucesso (HTTP 201) e erro (HTTP não-201), sem acionar rede real.
"""

from unittest.mock import patch

from backend.src.services import github_service


def test_create_github_issue_never_fabricates_a_url_when_credentials_missing(monkeypatch):
    """Regressao: antes esta funcao devolvia status="simulated" JUNTO de
    issue_url="https://github.com/owner/repo/issues/mock-1" -- uma URL com cara
    de real, no mesmo campo do caminho de sucesso. O modelo lia isso e
    respondia "criei a issue: <link>" a quem tinha aprovado a acao e nao
    recebeu issue nenhuma."""
    for var in ("GITHUB_OWNER", "GITHUB_REPO", "GITHUB_TOKEN"):
        monkeypatch.delenv(var, raising=False)

    result = github_service.create_github_issue(title="[A11Y] teste", body="corpo")

    assert result["status"] == "error"
    assert "issue_url" not in result, "nenhuma URL pode ser inventada quando nada foi criado"
    assert set(result["missing_config"]) == {"GITHUB_OWNER", "GITHUB_REPO", "GITHUB_TOKEN"}
    assert "GITHUB_TOKEN" in result["error"]

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
