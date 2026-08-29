from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import patch


async def _fake_stream(
    message: str,
    history: Any,
    provider: Any = None,
    model: Any = None,
    conversation_id: Any = None,
) -> AsyncIterator[dict[str, Any]]:
    yield {"type": "thinking", "text": "analisando"}
    yield {"type": "token", "text": "Ola"}
    yield {"type": "done", "final": "Ola"}


class TestChatStreamRoute:
    def test_sse_content_type_and_events(self, client):
        with patch("backend.src.routes.chat.stream_chat", new=_fake_stream):
            resp = client.post("/chat/stream", json={"message": "audita https://x.com"})
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]
        body = resp.text
        assert "data:" in body
        assert '"type": "token"' in body
        assert '"type": "done"' in body

    def test_validation_error_without_message(self, client):
        resp = client.post("/chat/stream", json={})
        assert resp.status_code == 422


class TestChatClarifyRoute:
    def test_clarify_delivers_to_pending_question(self, client):
        from backend.src.services import chat_progress

        rid, _ev = chat_progress.new_clarify()
        resp = client.post("/chat/clarify", json={"request_id": rid, "answer": "sim"})
        assert resp.status_code == 200
        assert resp.json() == {"delivered": True}
        # a resposta ficou registrada para o turno em espera
        assert chat_progress._answers.get(rid) == "sim"

    def test_clarify_unknown_id_not_delivered(self, client):
        resp = client.post("/chat/clarify", json={"request_id": "naoexiste", "answer": "x"})
        assert resp.status_code == 200
        assert resp.json() == {"delivered": False}


class TestChatHistoryRoutes:
    def test_get_history_returns_persisted_messages(self, client, tmp_path, monkeypatch):
        monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
        from backend.src.services import chat_history_store
        chat_history_store.append_message("user", "oi", session_id="conv-teste")
        chat_history_store.append_message("assistant", "olá!", session_id="conv-teste")

        resp = client.get("/chat/history/conv-teste")

        assert resp.status_code == 200
        body = resp.json()
        assert body["conversation_id"] == "conv-teste"
        assert [m["role"] for m in body["messages"]] == ["user", "assistant"]

    def test_get_history_for_unknown_conversation_is_empty_not_404(self, client):
        resp = client.get("/chat/history/nunca-existiu")
        assert resp.status_code == 200
        assert resp.json()["messages"] == []

    def test_list_conversations_returns_recent_first(self, client, tmp_path, monkeypatch):
        monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
        from backend.src.services import chat_history_store
        chat_history_store.append_message("user", "primeira", session_id="conv-a")
        chat_history_store.append_message("user", "segunda", session_id="conv-b")

        resp = client.get("/chat/conversations")

        assert resp.status_code == 200
        ids = [c["conversation_id"] for c in resp.json()["conversations"]]
        assert ids[0] == "conv-b"

    def test_delete_history_clears_the_conversation(self, client, tmp_path, monkeypatch):
        monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
        from backend.src.services import chat_history_store
        chat_history_store.append_message("user", "para apagar", session_id="conv-del")

        resp = client.delete("/chat/history/conv-del")

        assert resp.status_code == 200
        assert resp.json() == {"cleared": True}
        assert chat_history_store.get_history(session_id="conv-del") == []
