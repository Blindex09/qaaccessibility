"""Conversa corrente de exportação via header X-QA-Conversation-Id.

A costura (2026-10-01): o frontend linka o PDF/XLSX direto da conversa, mas
o GET /export/last_* não recebia o conversation_id e sempre lia a sessão
"default" — devolvendo 400 para conversas com análise real no cache. Cada
rota de exportação resolve a sessão por este único ponto (zero duplicação).
"""

from contextlib import asynccontextmanager, contextmanager

from backend.src.services.session_context import (
    reset_current_session,
    set_current_session,
)

HEADER = "X-QA-Conversation-Id"
QUERY_PARAM = "conversation_id"


class HeadersOrParams:
    """Aceita headers de Request (get com case-insensitive) e um dict de
    query params; usado por rotas que pedem o id de conversa do frontend."""

    def __init__(self, headers, params: dict | None = None):
        self._headers = headers
        self._params = params or {}

    def get(self, name: str, default: str | None = None) -> str | None:
        header_value = self._headers.get(name)
        if header_value:
            return header_value
        return self._params.get(QUERY_PARAM) or default


def _conversation_id_from(source) -> str:
    """Lê o id de conversa do header estruturado (ou query param); nunca
    infere do texto da conversa nem do caminho da URL."""
    return (source.get(HEADER) or "").strip()


@contextmanager
def export_session(request_headers, query_params: dict | None = None):
    """Escopo da conversa corrente para uma requisição de exportação: se o
    frontend mandar o id da conversa no header (ou query param, para links
    diretos <a href>), os stores por sessão (last_analysis,
    last_analyzed_content, last_fix, checkpoints) leem os dados dessa
    conversa; sem nenhum dos dois, comportamento antigo (default)."""
    conversation_id = _conversation_id_from(HeadersOrParams(request_headers, query_params))
    if not conversation_id:
        yield
        return
    token = set_current_session(conversation_id)
    try:
        yield
    finally:
        reset_current_session(token)


@asynccontextmanager
async def export_session_async(request_headers, query_params: dict | None = None):
    with export_session(request_headers, query_params):
        yield
