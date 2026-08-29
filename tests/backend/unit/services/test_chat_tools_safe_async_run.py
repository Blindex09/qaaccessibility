"""Testes de regressao para _safe_async_run em chat_tools.py.

Bug real corrigido: _safe_async_run, quando detectava um event loop ja rodando,
criava uma thread worker e executava `asyncio.run` nela. ContextVars nao
propagam automaticamente para threads de `concurrent.futures.ThreadPoolExecutor`,
entao a sessao corrente (session_context) se perdia. Isso fazia com que
fix_and_zip_files salvasse as paginas de preview no slot 'default' da
last_fix_store, e a ferramenta open_live_preview, rodando na thread/sessao
correta, nao encontrasse nenhuma pagina de preview.
"""

import asyncio

from backend.src.services import session_context
from backend.src.services.chat_tools import _safe_async_run
from backend.src.services.last_fix_store import get_last_fix, set_last_fix


async def _store_and_return_session() -> str:
    """Corrotina que le a sessao corrente e escreve no last_fix_store."""
    session = session_context.resolve_session()
    set_last_fix([{"title": "p", "original_html": "<html>", "fixed_html": "<html>"}])
    return session


class TestSafeAsyncRunSessionPropagation:
    def test_propagates_session_to_thread_worker_when_loop_is_running(self):
        """Quando chamado dentro de um loop async, a sessao deve chegar a thread worker."""
        session_id = "conversa-worker-test"
        token = session_context.set_current_session(session_id)
        try:
            async def _runner():
                return _safe_async_run(_store_and_return_session())

            result = asyncio.run(_runner())
            assert result == session_id
            assert get_last_fix(session_id) != []
        finally:
            session_context.reset_current_session(token)

    def test_uses_session_directly_when_no_loop_running(self):
        """Quando nao ha loop rodando, _safe_async_run executa diretamente."""
        session_id = "conversa-sync-test"
        token = session_context.set_current_session(session_id)
        try:
            result = _safe_async_run(_store_and_return_session())
            assert result == session_id
            assert get_last_fix(session_id) != []
        finally:
            session_context.reset_current_session(token)

    def test_default_session_when_no_context_set(self):
        """Sem sessao explicita, resolve para default e ainda funciona."""
        result = _safe_async_run(_store_and_return_session())
        assert result == session_context.DEFAULT_SESSION_ID
