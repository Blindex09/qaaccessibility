"""Histórico de mensagens do chat, persistido por sessão/conversa.

Antes deste módulo, o histórico de conversa vivia SÓ no estado React do
frontend (`useChat.ts`), nunca no backend -- recarregar a página apagava a
conversa inteira, e não existia como listar conversas anteriores. O backend
usava o `history` que o cliente reenviava a cada turno só para montar o
prompt daquele turno (`stream_chat`), e descartava.

Este store grava cada mensagem (usuário e assistente) conforme o turno
acontece, isolado por `conversation_id` (mesma sessão corrente de
`session_context.py`, compartilhada com `last_analysis_store` etc.), e
espelha em disco -- mesmo padrão de `last_analysis_store.py` -- para
sobreviver a um restart do processo. Um índice separado (`_index_path`)
mantém metadados leves (última atualização, prévia da primeira mensagem,
contagem) para listar conversas sem carregar o histórico completo de cada uma.
"""

import hashlib
import json
import logging
import os
import re
import tempfile
import time
from typing import Any

from backend.src.services.session_context import DEFAULT_SESSION_ID, resolve_session

logger = logging.getLogger(__name__)

_MAX_MESSAGES_PER_SESSION = 500  # limite defensivo -- evita um arquivo crescer sem fim
_SAFE_SESSION_CHARS = re.compile(r"[^A-Za-z0-9_-]")

# Histórico em memória por sessão, espelhado em disco.
_sessions: dict[str, list[dict[str, Any]]] = {}


def _session_slug(session_id: str) -> str:
    if session_id == DEFAULT_SESSION_ID:
        return DEFAULT_SESSION_ID
    safe = _SAFE_SESSION_CHARS.sub("", session_id)[:40]
    digest = hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:12]
    return f"{safe}-{digest}" if safe else digest


def _history_filepath(session_id: str) -> str:
    return os.path.join(tempfile.gettempdir(), f"qa_accessibility_chat_history_{_session_slug(session_id)}.json")


def _index_filepath() -> str:
    return os.path.join(tempfile.gettempdir(), "qa_accessibility_chat_index.json")


def _load_history_from_disk(session_id: str) -> list[dict[str, Any]]:
    path = _history_filepath(session_id)
    if not os.path.exists(path):
        return []
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return list(data.get("messages", []))
    except (OSError, json.JSONDecodeError) as exc:
        logger.error("[ChatHistoryStore] Falha ao carregar histórico do disco (sessão %s): %s", session_id, exc)
        return []


def _save_history_to_disk(session_id: str, messages: list[dict[str, Any]]) -> None:
    try:
        with open(_history_filepath(session_id), "w", encoding="utf-8") as f:
            json.dump({"conversation_id": session_id, "messages": messages}, f, ensure_ascii=False, indent=2)
    except OSError as exc:
        logger.error("[ChatHistoryStore] Falha ao salvar histórico no disco (sessão %s): %s", session_id, exc)


def _load_index() -> dict[str, dict[str, Any]]:
    path = _index_filepath()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return dict(json.load(f))
    except (OSError, json.JSONDecodeError) as exc:
        logger.error("[ChatHistoryStore] Falha ao carregar índice de conversas: %s", exc)
        return {}


def _save_index(index: dict[str, dict[str, Any]]) -> None:
    try:
        with open(_index_filepath(), "w", encoding="utf-8") as f:
            json.dump(index, f, ensure_ascii=False, indent=2)
    except OSError as exc:
        logger.error("[ChatHistoryStore] Falha ao salvar índice de conversas: %s", exc)


def _update_index(session_id: str, messages: list[dict[str, Any]]) -> None:
    if session_id == DEFAULT_SESSION_ID:
        return  # sessão default (fora do chat, ex.: rotas /analyze) não entra na lista de conversas
    index = _load_index()
    first_user_msg = next((m["content"] for m in messages if m.get("role") == "user"), "")
    index[session_id] = {
        "conversation_id": session_id,
        "title": first_user_msg[:80],
        "message_count": len(messages),
        "last_updated": time.time(),
    }
    _save_index(index)


def append_message(role: str, content: str, session_id: str | None = None) -> None:
    """Grava uma mensagem no histórico da sessão corrente, persistindo em disco.

    Chamado por `chat_runtime.stream_chat` para a mensagem do usuário no
    início do turno e para a resposta final do assistente no fim -- nunca
    para tokens intermediários do streaming.
    """
    if not content or not content.strip():
        return
    session = resolve_session(session_id)
    if session not in _sessions:
        _sessions[session] = _load_history_from_disk(session)

    _sessions[session].append({"role": role, "content": content, "timestamp": time.time()})
    if len(_sessions[session]) > _MAX_MESSAGES_PER_SESSION:
        _sessions[session] = _sessions[session][-_MAX_MESSAGES_PER_SESSION:]

    _save_history_to_disk(session, _sessions[session])
    _update_index(session, _sessions[session])


def get_history(session_id: str | None = None) -> list[dict[str, Any]]:
    """Retorna o histórico completo da sessão (lista de {role, content, timestamp})."""
    session = resolve_session(session_id)
    if session not in _sessions:
        _sessions[session] = _load_history_from_disk(session)
    return list(_sessions[session])


def list_conversations(limit: int = 20) -> list[dict[str, Any]]:
    """Lista conversas conhecidas (com pelo menos uma mensagem de usuário),
    mais recentes primeiro. Não inclui a sessão default (fora do chat)."""
    index = _load_index()
    conversations = sorted(index.values(), key=lambda c: c.get("last_updated", 0), reverse=True)
    return conversations[:limit]


def clear_history(session_id: str | None = None) -> None:
    """Descarta o histórico da sessão (memória, disco e índice)."""
    session = resolve_session(session_id)
    _sessions.pop(session, None)
    try:
        path = _history_filepath(session)
        if os.path.exists(path):
            os.remove(path)
    except OSError as exc:
        logger.error("[ChatHistoryStore] Falha ao remover histórico em disco (sessão %s): %s", session, exc)
    index = _load_index()
    if session in index:
        del index[session]
        _save_index(index)
