"""Regressão da costura conversa -> exportação (2026-10-01).

Antes do `export_session.py`, o GET /export/last_* sempre lia a sessão
"default": o chat grava o cache na sessão da conversa
(`last_analysis_store`), mas o link de download da UI não transmitia o id
da conversa — o usuário recebia 400 "Nenhuma auditoria recente encontrada
no cache" com análise real no cache. A costura é fechada por header
(`X-QA-Conversation-Id`) ou query param (`?conversation_id=`).
"""

from fastapi.testclient import TestClient

from backend.src.services import last_analysis_store, session_context


def _issue(texto: str) -> dict:
    return {
        "id": texto,
        "criterion": "1.1.1",
        "severity": "high",
        "type": "error",
        "element": "<img>",
        "description": texto,
        "url": "https://exemplo.teste",
    }


def _headers(conversation_id: str) -> dict:
    return {"X-QA-Conversation-Id": conversation_id}


def test_last_xlsx_reads_conversation_cache_via_header(monkeypatch):
    from backend.src.main import app

    session = "conv-export-1"
    issues = [_issue("img sem alt")]
    last_analysis_store.set_last_analysis(issues, "https://exemplo.teste", session_id=session)

    client = TestClient(app)
    monkeypatch.setattr(
        "backend.src.routes.export_xlsx.export_issues_xlsx", lambda _i: b"xlsx-bytes"
    )
    resp = client.get("/export/last_xlsx", headers=_headers(session))
    assert resp.status_code == 200
    assert resp.content == b"xlsx-bytes"


def test_last_xlsx_without_header_keeps_legacy_default(monkeypatch):
    from backend.src.main import app

    last_analysis_store.set_last_analysis(
        [_issue("apenas default")], "https://exemplo.teste", session_id="default"
    )
    client = TestClient(app)
    monkeypatch.setattr(
        "backend.src.routes.export_xlsx.export_issues_xlsx", lambda _i: b"default-bytes"
    )
    resp = client.get("/export/last_xlsx")
    assert resp.status_code == 200


def test_conversation_id_via_query_param(monkeypatch):
    from backend.src.main import app

    session = "conv-export-2"
    last_analysis_store.set_last_analysis(
        [_issue("item do checklist")], "https://exemplo.teste", session_id=session
    )
    client = TestClient(app)
    monkeypatch.setattr(
        "backend.src.routes.export_xlsx.export_issues_xlsx", lambda _i: b"xlsx-bytes"
    )
    resp = client.get("/export/last_xlsx", params={"conversation_id": session})
    assert resp.status_code == 200

    # Sem nem header nem param, a conversa isolada NÃO polui a sessão default.
    resp2 = client.get("/export/last_xlsx", params={"conversation_id": "outra-conversa"})
    assert resp2.status_code == 400


def test_export_scope_never_leaks_between_requests(monkeypatch):
    """O escopo da conversa é request-scoped: durante o GET a sessão é a da
    conversa; terminado o request, o ContextVar volta ao default (uma tool do
    chat nunca herda a conversa de um GET de exportação)."""
    from backend.src.main import app


    session = "conv-export-3"
    last_analysis_store.set_last_analysis(
        [_issue("item isolado")], "https://exemplo.teste", session_id=session
    )
    client = TestClient(app)
    monkeypatch.setattr(
        "backend.src.routes.export_xlsx.export_issues_xlsx", lambda _i: b"scoped-bytes"
    )
    resp = client.get("/export/last_xlsx", headers=_headers(session))
    assert resp.status_code == 200
    assert resp.content == b"scoped-bytes"
    assert session_context.resolve_session() == "default"
