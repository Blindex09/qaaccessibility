"""Testes do cache de HTML da última página analisada por URL, isolado por sessão.

Ver comentário em last_analyzed_content_store.py: sem este cache, "corrija isso"
depois de uma análise por URL fazia o modelo reanalisar a página do zero em vez
de corrigir, porque `analyze_page` nunca devolvia o HTML bruto de volta pro
modelo (só um resumo compacto).
"""
import pytest

from backend.src.services import last_analyzed_content_store, session_context


@pytest.fixture(autouse=True)
def clean_state():
    last_analyzed_content_store._sessions.clear()
    yield
    last_analyzed_content_store._sessions.clear()


class TestSessionIsolation:
    def test_two_sessions_do_not_clobber_each_other(self):
        last_analyzed_content_store.set_last_analyzed_content("<p>a</p>", "https://a.com", session_id="conversa-a")
        last_analyzed_content_store.set_last_analyzed_content("<p>b</p>", "https://b.com", session_id="conversa-b")

        assert last_analyzed_content_store.get_last_analyzed_content(session_id="conversa-a") == ("<p>a</p>", "https://a.com")
        assert last_analyzed_content_store.get_last_analyzed_content(session_id="conversa-b") == ("<p>b</p>", "https://b.com")

    def test_unset_session_returns_empty_not_another_sessions_data(self):
        last_analyzed_content_store.set_last_analyzed_content("<p>a</p>", "https://a.com", session_id="conversa-a")
        assert last_analyzed_content_store.get_last_analyzed_content(session_id="conversa-nova") == ("", "")

    def test_current_session_comes_from_shared_context(self):
        token = session_context.set_current_session("conversa-ctx")
        try:
            last_analyzed_content_store.set_last_analyzed_content("<p>via-contexto</p>", "https://c.com")
            assert last_analyzed_content_store.get_last_analyzed_content() == ("<p>via-contexto</p>", "https://c.com")
            assert last_analyzed_content_store.get_last_analyzed_content(session_id="outra") == ("", "")
        finally:
            session_context.reset_current_session(token)


class TestEmptyHtmlIsIgnored:
    def test_setting_empty_html_does_not_overwrite_existing_cache(self):
        last_analyzed_content_store.set_last_analyzed_content("<p>a</p>", "https://a.com", session_id="c1")
        last_analyzed_content_store.set_last_analyzed_content("", "https://b.com", session_id="c1")
        assert last_analyzed_content_store.get_last_analyzed_content(session_id="c1") == ("<p>a</p>", "https://a.com")


class TestDefaultSession:
    def test_no_session_set_uses_default(self):
        last_analyzed_content_store.set_last_analyzed_content("<p>sem-sessao</p>", "https://x.com")
        assert last_analyzed_content_store.get_last_analyzed_content() == ("<p>sem-sessao</p>", "https://x.com")
