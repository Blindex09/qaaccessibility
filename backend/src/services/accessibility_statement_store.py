"""Cache, isolado por sessão/conversa, dos dados de organização/contato que o
usuário informou para a Declaração de Acessibilidade -- usado para persistir
essas informações entre a chamada de `generate_accessibility_statement` (POST
com os argumentos) e o GET de export do PDF (sem corpo, mesmo padrão de
`last_fix_store.py`/`last_analysis_store.py`).

Em memória apenas: são só metadados de rotulagem, não precisam sobreviver a
um restart do processo.
"""

import logging
from typing import Any

from backend.src.services.session_context import resolve_session

logger = logging.getLogger(__name__)

_sessions: dict[str, dict[str, Any]] = {}


def set_accessibility_statement_options(options: dict[str, Any], session_id: str | None = None) -> None:
    session = resolve_session(session_id)
    _sessions[session] = dict(options)
    logger.info("[AccessibilityStatementStore] Opções atualizadas para a sessão %s.", session)


def get_accessibility_statement_options(session_id: str | None = None) -> dict[str, Any]:
    return dict(_sessions.get(resolve_session(session_id), {}))
