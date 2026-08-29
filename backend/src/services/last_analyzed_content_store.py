"""Cache do HTML/conteúdo da última página analisada por URL, isolado por sessão.

Achado real (teste E2E de chat completo, 2026-08-10): `analyze_page()` busca e
renderiza a página, mas devolve só um RESUMO compacto pro modelo (score,
contagens, top issues) -- nunca o HTML bruto, para não estourar o contexto da
conversa (ver `_summarize_issues` em chat_tools.py). Isso deixava "corrija
isso" sem chão depois de uma análise por URL: `fix_and_zip_files` exige que o
próprio modelo passe `files: [{path, content}]` explicitamente, e o modelo
nunca recebeu o HTML de volta para poder repassar -- na prática, pedido de
correção após análise por URL fazia o modelo reanalisar a página do zero (~15
min extras) em vez de corrigir.

Este store guarda o HTML já buscado (mesmo fetch que `analyze_page` fez) para
`fix_and_zip_files` usar como fallback quando o modelo não fornece `files`.
Mesmo padrão de sessão de `last_analysis_store.py`/`last_fix_store.py`.
"""

import logging

from backend.src.services.session_context import resolve_session

logger = logging.getLogger(__name__)

_sessions: dict[str, tuple[str, str]] = {}  # session -> (html, url)


def set_last_analyzed_content(html: str, url: str, session_id: str | None = None) -> None:
    """Guarda o HTML e a URL da página analisada nesta sessão."""
    if not html:
        return
    session = resolve_session(session_id)
    _sessions[session] = (html, url)
    logger.info(
        "[LastAnalyzedContentStore] Cache atualizado (%d chars, sessão %s): %s",
        len(html), session, url or "(sem URL)",
    )


def get_last_analyzed_content(session_id: str | None = None) -> tuple[str, str]:
    """Retorna (html, url) da última página analisada por URL nesta sessão, ou ("", "")."""
    return _sessions.get(resolve_session(session_id), ("", ""))
