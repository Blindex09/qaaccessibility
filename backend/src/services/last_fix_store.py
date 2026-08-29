"""Cache das páginas HTML corrigidas na última chamada de fix, isolado por
sessão/conversa -- usado pelo chat tool `open_live_preview` para não exigir
que o modelo reenvie o HTML inteiro só para abrir a visualização ao vivo
(routes/preview.py).

Achado real: este store era um dicionário global até esta revisão -- ao
contrário de `last_analysis_store`/`fix_checkpoint_store`, não isolava por
`conversation_id`. Duas conversas simultâneas corrigindo páginas diferentes
sobrescreviam a pré-visualização uma da outra. Agora usa a mesma sessão
corrente de `session_context.py`.

Em memória apenas (não precisa sobreviver a um restart do processo).
"""

import logging
from typing import Any

from backend.src.services.session_context import resolve_session

logger = logging.getLogger(__name__)

# Cache em memória por sessão das páginas HTML corrigidas.
_sessions: dict[str, list[dict[str, Any]]] = {}


def set_last_fix(pages: list[dict[str, Any]], session_id: str | None = None) -> None:
    """Atualiza o cache da sessão com as páginas HTML corrigidas.

    Cada item: {"title": str, "original_html": str, "fixed_html": str}.
    """
    session = resolve_session(session_id)
    _sessions[session] = [dict(p) for p in pages if p.get("fixed_html")]
    logger.info(
        "[LastFixStore] Cache atualizado com %d pagina(s) HTML corrigida(s) (sessão %s).",
        len(_sessions[session]),
        session,
    )


def get_last_fix(session_id: str | None = None) -> list[dict[str, Any]]:
    """Retorna as páginas HTML corrigidas da última chamada de fix da sessão (pode ser vazio)."""
    return _sessions.get(resolve_session(session_id), [])
