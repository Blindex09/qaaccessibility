"""
Camada 4/9 -- E2E Environment Tests (real).

Diferente da camada 3 (chama `orchestrate()` diretamente em processo), esta
camada sobe a aplicação FastAPI real (`backend.src.main.app`) via TestClient
e bate no endpoint HTTP público `POST /analyze/file` -- valida upload
multipart, roteamento HTTP, serialização de resposta (`response_model`) e o
pipeline completo (incluindo classificador + core + condicionais) contra o
Ollama Cloud real, exatamente como o frontend faria.
"""
import io

import pytest
from fastapi.testclient import TestClient

from backend.src.main import app

pytestmark = pytest.mark.real_llm

_HTML_FILE = b"""<html lang="en">
<body>
  <img src="hero.png">
  <a href="/contact">Contact</a>
</body>
</html>"""


@pytest.fixture(scope="module")
def e2e_client() -> TestClient:
    return TestClient(app)


@pytest.fixture(scope="module")
def e2e_analyze_response(e2e_client: TestClient) -> dict:
    files = {"file": ("page.html", io.BytesIO(_HTML_FILE), "text/html")}
    response = e2e_client.post("/analyze/file", files=files)
    return {"status_code": response.status_code, "body": response.json()}


def test_e2e_analyze_file_returns_200(e2e_analyze_response: dict) -> None:
    assert e2e_analyze_response["status_code"] == 200, e2e_analyze_response["body"]


def test_e2e_analyze_file_response_matches_agent_result_contract(e2e_analyze_response: dict) -> None:
    body = e2e_analyze_response["body"]
    assert body["agent"] == "orchestrator"
    assert body["success"] is True
    assert "issues" in body["data"]
    assert "agent_metrics" in body["data"]


def test_e2e_analyze_file_detects_real_issue_end_to_end(e2e_analyze_response: dict) -> None:
    issues = e2e_analyze_response["body"]["data"]["issues"]
    assert len(issues) >= 1, "pipeline real via HTTP não detectou nenhum issue no HTML com img sem alt"
    criteria = {i["criterion"] for i in issues}
    assert any("1.1.1" in c for c in criteria), (
        f"nenhum issue 1.1.1 (img sem alt) no resultado E2E real. Criteria: {criteria}"
    )


def test_e2e_analyze_file_rejects_oversized_upload(e2e_client: TestClient) -> None:
    """Guard de ambiente real: limite de 60 KB por arquivo é aplicado antes de qualquer chamada LLM."""
    oversized = b"<html>" + b"a" * 70_000 + b"</html>"
    files = {"file": ("big.html", io.BytesIO(oversized), "text/html")}
    response = e2e_client.post("/analyze/file", files=files)
    assert response.status_code == 413
