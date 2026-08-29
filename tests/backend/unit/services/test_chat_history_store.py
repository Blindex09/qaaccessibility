"""Testes do histórico de mensagens do chat, persistido por sessão/conversa.

Feature real: antes deste store, o histórico só existia em memória do React
no navegador -- recarregar a página apagava a conversa inteira e não havia
como listar conversas anteriores.
"""
import json
import os

import pytest

from backend.src.services import chat_history_store


@pytest.fixture(autouse=True)
def clean_state(tmp_path, monkeypatch):
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
    chat_history_store._sessions.clear()
    yield
    chat_history_store._sessions.clear()


class TestAppendAndGet:
    def test_append_then_get_returns_messages_in_order(self):
        chat_history_store.append_message("user", "oi", session_id="c1")
        chat_history_store.append_message("assistant", "olá! como posso ajudar?", session_id="c1")

        history = chat_history_store.get_history(session_id="c1")

        assert [m["role"] for m in history] == ["user", "assistant"]
        assert history[0]["content"] == "oi"
        assert history[1]["content"] == "olá! como posso ajudar?"

    def test_each_message_has_a_timestamp(self):
        chat_history_store.append_message("user", "oi", session_id="c1")
        history = chat_history_store.get_history(session_id="c1")
        assert history[0]["timestamp"] > 0

    def test_empty_or_blank_content_is_not_recorded(self):
        chat_history_store.append_message("user", "", session_id="c1")
        chat_history_store.append_message("user", "   ", session_id="c1")
        assert chat_history_store.get_history(session_id="c1") == []

    def test_unknown_session_returns_empty_history(self):
        assert chat_history_store.get_history(session_id="nunca-existiu") == []


class TestSessionIsolation:
    def test_two_conversations_do_not_mix(self):
        chat_history_store.append_message("user", "pergunta da conversa A", session_id="conv-a")
        chat_history_store.append_message("user", "pergunta da conversa B", session_id="conv-b")

        history_a = chat_history_store.get_history(session_id="conv-a")
        history_b = chat_history_store.get_history(session_id="conv-b")

        assert [m["content"] for m in history_a] == ["pergunta da conversa A"]
        assert [m["content"] for m in history_b] == ["pergunta da conversa B"]


class TestPersistenceAcrossRestart:
    def test_history_survives_store_reload(self, tmp_path, monkeypatch):
        monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
        chat_history_store.append_message("user", "mensagem antes do restart", session_id="c1")

        # Simula reinício do processo: apaga só o estado em memória, mantém o disco.
        chat_history_store._sessions.clear()

        history = chat_history_store.get_history(session_id="c1")
        assert [m["content"] for m in history] == ["mensagem antes do restart"]

    def test_history_file_is_written_to_disk(self, tmp_path, monkeypatch):
        monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
        chat_history_store.append_message("user", "grava no disco", session_id="minha-conversa")

        path = chat_history_store._history_filepath("minha-conversa")
        assert os.path.exists(path)
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        assert data["conversation_id"] == "minha-conversa"
        assert data["messages"][0]["content"] == "grava no disco"


class TestListConversations:
    def test_lists_conversations_most_recent_first(self):
        chat_history_store.append_message("user", "primeira conversa", session_id="c1")
        chat_history_store.append_message("user", "segunda conversa", session_id="c2")

        conversations = chat_history_store.list_conversations()

        ids = [c["conversation_id"] for c in conversations]
        assert ids[0] == "c2"
        assert ids[1] == "c1"

    def test_conversation_title_is_a_preview_of_first_user_message(self):
        chat_history_store.append_message("user", "como corrijo esse botão sem nome acessível?", session_id="c1")
        chat_history_store.append_message("assistant", "resposta longa aqui...", session_id="c1")

        conversations = chat_history_store.list_conversations()
        c1 = next(c for c in conversations if c["conversation_id"] == "c1")
        assert c1["title"] == "como corrijo esse botão sem nome acessível?"
        assert c1["message_count"] == 2

    def test_default_session_is_excluded_from_the_list(self):
        chat_history_store.append_message("user", "fora do chat", session_id=None)
        conversations = chat_history_store.list_conversations()
        assert conversations == []

    def test_limit_caps_the_number_of_results(self):
        for i in range(5):
            chat_history_store.append_message("user", f"conversa {i}", session_id=f"c{i}")
        assert len(chat_history_store.list_conversations(limit=2)) == 2


class TestClearHistory:
    def test_clear_removes_memory_disk_and_index(self, tmp_path, monkeypatch):
        monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
        chat_history_store.append_message("user", "para apagar", session_id="c1")
        path = chat_history_store._history_filepath("c1")
        assert os.path.exists(path)

        chat_history_store.clear_history(session_id="c1")

        assert chat_history_store.get_history(session_id="c1") == []
        assert not os.path.exists(path)
        assert chat_history_store.list_conversations() == []
