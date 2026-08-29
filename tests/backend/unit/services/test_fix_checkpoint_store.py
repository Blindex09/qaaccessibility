"""Testes do checkpoint de remediação (undo) isolado por sessão/conversa.

Feature real: `fix_and_zip_files` sobrescrevia o cache da última análise e as
páginas de preview sem guardar nada do estado anterior -- corrigiu, perdeu, sem
caminho de volta. Agora um checkpoint é tirado ANTES da correção e a tool
`undo_last_fix` o repõe. O store segue o mesmo padrão por sessão do
`last_analysis_store` (ver test_last_analysis_store.py): um global aqui faria uma
conversa desfazer a correção de outra.
"""

import json

import pytest

from backend.src.services import fix_checkpoint_store as store
from backend.src.services import last_analysis_store, last_fix_store, session_context
from backend.src.services.chat_tools import A11Y_CHAT_TOOLSET, register_chat_tools, undo_last_fix
from tools.registry import registry


@pytest.fixture(autouse=True)
def clean_state(tmp_path, monkeypatch):
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
    store._checkpoints.clear()
    last_analysis_store._sessions.clear()
    last_fix_store._sessions.clear()
    yield
    store._checkpoints.clear()
    last_analysis_store._sessions.clear()
    last_fix_store._sessions.clear()


def _issue(issue_id: str) -> dict[str, str]:
    return {"id": issue_id, "criterion": "1.1.1", "severity": "high", "element": "img"}


def _page(title: str) -> dict[str, str]:
    return {"title": title, "original_html": "<p>antes</p>", "fixed_html": "<p>depois</p>"}


class TestCheckpointRoundTrip:
    def test_checkpoint_captures_the_state_before_the_fix(self):
        last_analysis_store.set_last_analysis([_issue("antes-1")], "https://antes.example", session_id="c1")
        last_fix_store.set_last_fix([_page("home antiga")], session_id="c1")

        checkpoint = store.create_checkpoint("correção de teste", session_id="c1")

        assert [i["id"] for i in checkpoint.issues] == ["antes-1"]
        assert checkpoint.url == "https://antes.example"
        assert [p["title"] for p in checkpoint.fix_pages] == ["home antiga"]

    def test_restore_puts_back_exactly_the_pre_fix_state(self):
        last_analysis_store.set_last_analysis([_issue("antes-1")], "https://antes.example", session_id="c1")
        last_fix_store.set_last_fix([_page("home antiga")], session_id="c1")
        store.create_checkpoint("correção de teste", session_id="c1")

        # A correção sobrescreve os dois caches...
        last_analysis_store.set_last_analysis([_issue("depois-1")], "Projeto ZIP corrigido", session_id="c1")
        last_fix_store.set_last_fix([_page("home corrigida")], session_id="c1")

        restored = store.restore_checkpoint(session_id="c1")

        assert restored is not None
        issues, url = last_analysis_store.get_last_analysis(session_id="c1")
        assert [i["id"] for i in issues] == ["antes-1"]
        assert url == "https://antes.example"
        assert [p["title"] for p in last_fix_store.get_last_fix(session_id="c1")] == ["home antiga"]

    def test_snapshot_is_a_copy_so_later_mutation_does_not_corrupt_it(self):
        """`get_last_fix` devolve a lista interna do store: sem cópia, mexer nas
        páginas depois da correção reescreveria o próprio checkpoint."""
        last_fix_store.set_last_fix([_page("home antiga")], session_id="c1")
        store.create_checkpoint("correção", session_id="c1")

        live_pages = last_fix_store.get_last_fix(session_id="c1")
        live_pages[0]["title"] = "mutado"
        live_pages[0]["fixed_html"] = "<p>outra coisa</p>"

        checkpoint = store.get_checkpoint(session_id="c1")
        assert [p["title"] for p in checkpoint.fix_pages] == ["home antiga"]
        assert checkpoint.fix_pages[0]["fixed_html"] == "<p>depois</p>"

    def test_undo_is_single_level_and_consumes_the_checkpoint(self):
        last_analysis_store.set_last_analysis([_issue("antes-1")], "https://antes.example", session_id="c1")
        store.create_checkpoint("correção", session_id="c1")

        assert store.restore_checkpoint(session_id="c1") is not None
        assert store.restore_checkpoint(session_id="c1") is None

    def test_restore_without_checkpoint_returns_none(self):
        assert store.restore_checkpoint(session_id="nunca-corrigiu") is None


class TestSessionIsolation:
    """Espelha os testes de isolamento do last_analysis_store."""

    def test_two_sessions_keep_independent_checkpoints(self):
        last_analysis_store.set_last_analysis([_issue("a-1")], "https://a.example", session_id="conversa-a")
        store.create_checkpoint("fix A", session_id="conversa-a")
        last_analysis_store.set_last_analysis([_issue("b-1")], "https://b.example", session_id="conversa-b")
        store.create_checkpoint("fix B", session_id="conversa-b")

        assert [i["id"] for i in store.get_checkpoint(session_id="conversa-a").issues] == ["a-1"]
        assert [i["id"] for i in store.get_checkpoint(session_id="conversa-b").issues] == ["b-1"]

    def test_undo_in_one_session_does_not_touch_the_other(self):
        last_analysis_store.set_last_analysis([_issue("a-antes")], "https://a.example", session_id="conversa-a")
        store.create_checkpoint("fix A", session_id="conversa-a")
        last_analysis_store.set_last_analysis([_issue("a-depois")], "corrigido", session_id="conversa-a")
        last_analysis_store.set_last_analysis([_issue("b-1")], "https://b.example", session_id="conversa-b")

        store.restore_checkpoint(session_id="conversa-a")

        issues_a, _ = last_analysis_store.get_last_analysis(session_id="conversa-a")
        issues_b, url_b = last_analysis_store.get_last_analysis(session_id="conversa-b")
        assert [i["id"] for i in issues_a] == ["a-antes"]
        assert [i["id"] for i in issues_b] == ["b-1"]
        assert url_b == "https://b.example"

    def test_current_session_comes_from_the_contextvar(self):
        last_analysis_store.set_last_analysis([_issue("ctx-1")], "https://ctx.example", session_id="conversa-ctx")
        token = session_context.set_current_session("conversa-ctx")
        try:
            store.create_checkpoint("fix via contextvar")
            assert store.get_checkpoint(session_id="conversa-ctx") is not None
            assert store.get_checkpoint(session_id="outra") is None
        finally:
            session_context.reset_current_session(token)


class TestUndoTool:
    def test_undo_tool_is_registered_and_gated_by_approval(self):
        register_chat_tools()
        assert "undo_last_fix" in registry.get_tool_names_for_toolset(A11Y_CHAT_TOOLSET)
        assert registry.tools["undo_last_fix"]["requires_approval"] is True

    def test_undo_tool_restores_the_pre_fix_state(self):
        token = session_context.set_current_session("conversa-tool")
        try:
            last_analysis_store.set_last_analysis([_issue("antes-1")], "https://antes.example")
            last_fix_store.set_last_fix([_page("home antiga")])
            store.create_checkpoint("correção de 2 arquivo(s)")
            last_analysis_store.set_last_analysis([_issue("depois-1")], "Projeto ZIP corrigido")
            last_fix_store.set_last_fix([_page("home corrigida")])

            payload = json.loads(undo_last_fix({"pre_exec_msg": "desfazendo"}))

            assert payload["restored"] is True
            assert payload["issues_restored"] == 1
            issues, url = last_analysis_store.get_last_analysis()
            assert [i["id"] for i in issues] == ["antes-1"]
            assert url == "https://antes.example"
            assert [p["title"] for p in last_fix_store.get_last_fix()] == ["home antiga"]
        finally:
            session_context.reset_current_session(token)

    def test_undo_tool_without_checkpoint_returns_a_clear_error(self):
        payload = json.loads(undo_last_fix({"pre_exec_msg": "desfazendo"}))
        assert "error" in payload
        assert "desfazer" in payload["error"]


class TestCheckpointIsCreatedBeforeTheFix:
    def test_fix_and_zip_files_checkpoints_the_state_before_running(self, monkeypatch):
        """O checkpoint tem de existir ANTES da correção mexer nos caches."""
        from backend.src.services import chat_tools

        token = session_context.set_current_session("conversa-fix")
        try:
            last_analysis_store.set_last_analysis([_issue("antes-1")], "https://antes.example")
            seen: dict = {}

            async def fake_run(files, custom_instruction, existing_issues=None):
                # No momento em que a correção roda, o checkpoint já tem de estar lá.
                checkpoint = store.get_checkpoint(session_id="conversa-fix")
                seen["issues_at_fix_time"] = [i["id"] for i in checkpoint.issues] if checkpoint else None
                last_analysis_store.set_last_analysis([_issue("depois-1")], "Projeto ZIP corrigido")
                return {"download_url": "u", "zip_filename": "z.zip", "changes_summary": [], "total_files": 1}

            monkeypatch.setattr(chat_tools, "_run_fixes_and_generate_zip", fake_run)

            chat_tools.fix_and_zip_files({"files": [{"path": "a.html", "content": "<p>x</p>"}]})

            assert seen["issues_at_fix_time"] == ["antes-1"]
            # E o undo volta ao estado anterior de verdade.
            json.loads(undo_last_fix({"pre_exec_msg": "desfaz"}))
            issues, _ = last_analysis_store.get_last_analysis()
            assert [i["id"] for i in issues] == ["antes-1"]
        finally:
            session_context.reset_current_session(token)
