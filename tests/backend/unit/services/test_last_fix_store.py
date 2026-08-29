"""Testes do cache de páginas HTML corrigidas, isolado por sessão/conversa.

Achado real corrigido nesta suíte: este store era um dicionário GLOBAL até
esta revisão -- ao contrário de last_analysis_store/fix_checkpoint_store,
não isolava por conversation_id. Duas conversas simultâneas corrigindo
páginas diferentes sobrescreviam a pré-visualização uma da outra.
"""
import pytest

from backend.src.services import last_fix_store, session_context


@pytest.fixture(autouse=True)
def clean_state():
    last_fix_store._sessions.clear()
    yield
    last_fix_store._sessions.clear()


def _page(title: str) -> dict[str, str]:
    return {"title": title, "original_html": "<p>antes</p>", "fixed_html": "<p>depois</p>"}


class TestSessionIsolation:
    def test_two_sessions_do_not_clobber_each_other(self):
        last_fix_store.set_last_fix([_page("site-a")], session_id="conversa-a")
        last_fix_store.set_last_fix([_page("site-b")], session_id="conversa-b")

        assert [p["title"] for p in last_fix_store.get_last_fix(session_id="conversa-a")] == ["site-a"]
        assert [p["title"] for p in last_fix_store.get_last_fix(session_id="conversa-b")] == ["site-b"]

    def test_unset_session_returns_empty_not_another_sessions_data(self):
        last_fix_store.set_last_fix([_page("site-a")], session_id="conversa-a")
        assert last_fix_store.get_last_fix(session_id="conversa-nova") == []

    def test_current_session_comes_from_shared_context(self):
        """last_fix_store lê a mesma sessão corrente que last_analysis_store e
        fix_checkpoint_store (session_context.py) -- setar uma vez basta."""
        token = session_context.set_current_session("conversa-ctx")
        try:
            last_fix_store.set_last_fix([_page("via-contexto")])
            assert [p["title"] for p in last_fix_store.get_last_fix()] == ["via-contexto"]
            assert [p["title"] for p in last_fix_store.get_last_fix(session_id="outra")] == []
        finally:
            session_context.reset_current_session(token)


class TestFiltersPagesWithoutFixedHtml:
    def test_pages_without_fixed_html_are_dropped(self):
        pages = [_page("com-fix"), {"title": "sem-fix", "original_html": "<p>x</p>"}]
        last_fix_store.set_last_fix(pages, session_id="c1")
        assert [p["title"] for p in last_fix_store.get_last_fix(session_id="c1")] == ["com-fix"]


class TestDefaultSession:
    def test_no_session_set_uses_default(self):
        last_fix_store.set_last_fix([_page("sem-sessao")])
        assert [p["title"] for p in last_fix_store.get_last_fix()] == ["sem-sessao"]
