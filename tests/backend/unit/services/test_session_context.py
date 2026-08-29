"""Testes do módulo compartilhado de sessão corrente do chat (session_context.py).

Fonte única para last_analysis_store, fix_checkpoint_store, last_fix_store e
chat_history_store -- antes cada um definia seu próprio ContextVar idêntico.
"""
from backend.src.services import session_context


class TestResolveSession:
    def test_no_context_set_returns_default(self):
        assert session_context.resolve_session() == session_context.DEFAULT_SESSION_ID

    def test_explicit_override_wins_over_context(self):
        token = session_context.set_current_session("from-context")
        try:
            assert session_context.resolve_session("explicit") == "explicit"
        finally:
            session_context.reset_current_session(token)

    def test_context_value_used_when_no_override(self):
        token = session_context.set_current_session("conversa-x")
        try:
            assert session_context.resolve_session() == "conversa-x"
            assert session_context.resolve_session(None) == "conversa-x"
        finally:
            session_context.reset_current_session(token)

    def test_empty_string_id_falls_back_to_default(self):
        assert session_context.resolve_session("") == session_context.DEFAULT_SESSION_ID


class TestSetAndReset:
    def test_reset_restores_previous_value(self):
        outer_token = session_context.set_current_session("outer")
        try:
            inner_token = session_context.set_current_session("inner")
            assert session_context.resolve_session() == "inner"
            session_context.reset_current_session(inner_token)
            assert session_context.resolve_session() == "outer"
        finally:
            session_context.reset_current_session(outer_token)

    def test_reset_with_stale_token_does_not_raise(self):
        token = session_context.set_current_session("x")
        session_context.reset_current_session(token)
        session_context.reset_current_session(token)  # segundo reset do mesmo token -- não deve levantar
