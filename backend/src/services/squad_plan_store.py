"""Quadro persistente da squad, isolado por sessão/conversa.

Por que existe: sem persistência, cada turno do chat criava um plano novo do
zero e os estados nunca sobreviviam à mensagem em que nasceram -- o "quadro"
era um retrato descartável, e nenhuma squad real replaneja a sprint a cada
frase dita. Aqui o plano é criado uma vez por conversa, avança de estado ao
longo dos turnos e sobrevive a reinício do backend.

Segue o mesmo padrão de `last_analysis_store.py`: cache em memória por sessão,
espelhado em disco, com a sessão corrente vindo de `session_context.py`.
"""

import hashlib
import json
import logging
import os
import re
import tempfile
from typing import Any

from backend.src.services.session_context import (
    DEFAULT_SESSION_ID,
    resolve_session,
)

logger = logging.getLogger(__name__)

__all__ = [
    "get_plan_filepath",
    "save_squad_plan",
    "load_squad_plan",
    "clear_squad_plan",
]

_sessions: dict[str, dict[str, Any]] = {}

_SAFE_SESSION_CHARS = re.compile(r"[^A-Za-z0-9_-]")


def _session_slug(session_id: str) -> str:
    if session_id == DEFAULT_SESSION_ID:
        return DEFAULT_SESSION_ID
    safe = _SAFE_SESSION_CHARS.sub("", session_id)[:40]
    digest = hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:12]
    return f"{safe}-{digest}" if safe else digest


def get_plan_filepath(session_id: str | None = None) -> str:
    slug = _session_slug(resolve_session(session_id))
    return os.path.join(tempfile.gettempdir(), f"qa_accessibility_squad_plan_{slug}.json")


def save_squad_plan(plan: dict[str, Any], session_id: str | None = None) -> None:
    session = resolve_session(session_id)
    _sessions[session] = plan
    try:
        with open(get_plan_filepath(session), "w", encoding="utf-8") as f:
            json.dump(plan, f, ensure_ascii=False, indent=2)
    except OSError as exc:
        # Perder o quadro em disco degrada para "replaneja no proximo turno",
        # nunca derruba a conversa.
        logger.error("[SquadPlanStore] Falha ao salvar o quadro (sessao %s): %s", session, exc)


def load_squad_plan(session_id: str | None = None) -> dict[str, Any] | None:
    session = resolve_session(session_id)
    if session in _sessions:
        return _sessions[session]
    path = get_plan_filepath(session)
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            plan = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        logger.error("[SquadPlanStore] Falha ao carregar o quadro (sessao %s): %s", session, exc)
        return None
    if not isinstance(plan, dict):
        return None
    _sessions[session] = plan
    return plan


def clear_squad_plan(session_id: str | None = None) -> None:
    """Encerra o ciclo da squad. Chamado quando uma auditoria NOVA começa --
    contexto de trabalho novo, quadro novo (mesma regra do portão de qualidade
    'não misturar sessões')."""
    session = resolve_session(session_id)
    _sessions.pop(session, None)
    path = get_plan_filepath(session)
    try:
        if os.path.exists(path):
            os.remove(path)
    except OSError as exc:
        logger.error("[SquadPlanStore] Falha ao limpar o quadro (sessao %s): %s", session, exc)
