"""Testes do cache da última análise, isolado por sessão/conversa.

Bug real de auditoria: o store guardava tudo em dois globais de módulo
(`_last_issues`/`_last_url`) e num único arquivo fixo em %TEMP%. Dois usuários
(ou duas conversas) simultâneos sobrescreviam os dados um do outro em silêncio, e
esse cache alimenta `generate_vpat`, `generate_test_suite` e `fix_and_zip_files`
-- ou seja, uma conversa podia gerar o VPAT dos issues de outra.
"""

import os

import pytest

from backend.src.services import last_analysis_store as store


@pytest.fixture(autouse=True)
def clean_sessions(tmp_path, monkeypatch):
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
    store._sessions.clear()
    yield
    store._sessions.clear()


def _issue(issue_id: str) -> dict[str, str]:
    return {"id": issue_id, "criterion": "1.1.1", "severity": "high", "element": "img"}


class TestSessionIsolation:
    def test_two_sessions_keep_independent_analyses(self):
        store.set_last_analysis([_issue("a-1")], "https://a.example", session_id="conversa-a")
        store.set_last_analysis([_issue("b-1")], "https://b.example", session_id="conversa-b")

        issues_a, url_a = store.get_last_analysis(session_id="conversa-a")
        issues_b, url_b = store.get_last_analysis(session_id="conversa-b")

        assert [i["id"] for i in issues_a] == ["a-1"]
        assert url_a == "https://a.example"
        assert [i["id"] for i in issues_b] == ["b-1"]
        assert url_b == "https://b.example"

    def test_each_session_has_its_own_cache_file(self):
        assert store.get_cache_filepath("conversa-a") != store.get_cache_filepath("conversa-b")

    def test_disk_reload_does_not_leak_between_sessions(self):
        store.set_last_analysis([_issue("a-1")], "https://a.example", session_id="conversa-a")
        store._sessions.clear()  # força releitura do disco

        issues_b, url_b = store.get_last_analysis(session_id="conversa-b")
        assert issues_b == []
        assert url_b == ""

        issues_a, _ = store.get_last_analysis(session_id="conversa-a")
        assert [i["id"] for i in issues_a] == ["a-1"]

    def test_append_only_touches_the_target_session(self):
        store.set_last_analysis([_issue("a-1")], "https://a.example", session_id="conversa-a")
        store.set_last_analysis([_issue("b-1")], "https://b.example", session_id="conversa-b")
        store.set_last_analysis([_issue("b-2")], "https://b2.example", append=True, session_id="conversa-b")

        assert [i["id"] for i in store.get_last_analysis(session_id="conversa-a")[0]] == ["a-1"]
        assert [i["id"] for i in store.get_last_analysis(session_id="conversa-b")[0]] == ["b-1", "b-2"]


class TestCurrentSessionContext:
    def test_context_var_selects_the_session_for_tools(self):
        token = store.set_current_session("conversa-a")
        try:
            store.set_last_analysis([_issue("a-1")], "https://a.example")
            assert [i["id"] for i in store.get_last_analysis()[0]] == ["a-1"]
        finally:
            store.reset_current_session(token)

        # Fora do contexto vale a sessão default, que não vê os dados da conversa.
        assert store.get_last_analysis()[0] == []

    def test_session_id_is_sanitized_into_the_filename(self):
        """O id vem do cliente, então não pode virar travessia de diretório."""
        filename = os.path.basename(store.get_cache_filepath("../../etc/passwd"))
        assert filename.startswith("qa_accessibility_last_analysis_")
        assert ".." not in filename
        assert "/" not in filename and "\\" not in filename
