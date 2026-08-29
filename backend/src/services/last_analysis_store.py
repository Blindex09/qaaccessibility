"""Cache da última análise de acessibilidade, isolado por sessão/conversa.

Cada conversa do chat (conversation_id) tem o seu próprio slot em memória e o
seu próprio arquivo de cache em disco. Sem isso, dois usuários simultâneos
sobrescreviam os issues um do outro, e `generate_vpat`/`generate_test_suite`/
`fix_and_zip_files` liam a análise da conversa errada.

A sessão corrente vem de `session_context.py` (fonte única, compartilhada com
fix_checkpoint_store/last_fix_store/chat_history_store), então as tools não
precisam receber o id por parâmetro. Fora do chat (rotas /analyze) vale a
sessão default.
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
    reset_current_session,
    resolve_session,
    set_current_session,
)

logger = logging.getLogger(__name__)

__all__ = [
    "DEFAULT_SESSION_ID",
    "set_current_session",
    "reset_current_session",
    "get_cache_filepath",
    "set_last_analysis",
    "get_last_analysis",
]

# Cache em memória por sessão, espelhado em disco para persistência.
_sessions: dict[str, tuple[list[dict[str, Any]], str]] = {}

_SAFE_SESSION_CHARS = re.compile(r"[^A-Za-z0-9_-]")


def _resolve_session(session_id: str | None) -> str:
    return resolve_session(session_id)


def _session_slug(session_id: str) -> str:
    """Nome de arquivo estável e seguro para a sessão (ids vêm do cliente)."""
    if session_id == DEFAULT_SESSION_ID:
        return DEFAULT_SESSION_ID
    safe = _SAFE_SESSION_CHARS.sub("", session_id)[:40]
    digest = hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:12]
    return f"{safe}-{digest}" if safe else digest


def get_cache_filepath(session_id: str | None = None) -> str:
    """Caminho do arquivo de cache da sessão (usado também no prompt do chat)."""
    slug = _session_slug(_resolve_session(session_id))
    return os.path.join(tempfile.gettempdir(), f"qa_accessibility_last_analysis_{slug}.json")


def _save_cache_to_disk(session: str) -> None:
    issues, url = _sessions.get(session, ([], ""))
    try:
        with open(get_cache_filepath(session), "w", encoding="utf-8") as f:
            json.dump({"url": url, "issues": issues}, f, ensure_ascii=False, indent=2)
    except OSError as e:
        logger.error("[LastAnalysisStore] Falha ao salvar cache no disco (sessão %s): %s", session, e)


def _load_cache_from_disk(session: str) -> None:
    path = get_cache_filepath(session)
    if not os.path.exists(path):
        return
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        _sessions[session] = (list(data.get("issues", [])), str(data.get("url", "")))
    except (OSError, json.JSONDecodeError) as e:
        logger.error("[LastAnalysisStore] Falha ao carregar cache do disco (sessão %s): %s", session, e)


def set_last_analysis(
    issues: list[dict[str, Any]],
    url: str,
    append: bool = False,
    session_id: str | None = None,
) -> None:
    """Atualiza o cache da sessão com os últimos issues e a URL auditada, persistindo em disco."""
    session = _resolve_session(session_id)

    # Se estiver vazio na memória, tenta carregar o que estiver no disco primeiro
    if not _sessions.get(session, ([], ""))[0]:
        _load_cache_from_disk(session)
    last_issues, last_url = _sessions.get(session, ([], ""))

    # Garante que todos os issues têm o campo url preenchido se não tiverem
    for issue in issues:
        if not issue.get("url"):
            issue["url"] = url

    if append:
        # Filtra duplicados baseados no id e element
        existing_keys = {(i.get("id"), i.get("element")) for i in last_issues}
        added_count = 0
        for issue in issues:
            key = (issue.get("id"), issue.get("element"))
            if key not in existing_keys:
                last_issues.append(dict(issue))
                existing_keys.add(key)
                added_count += 1

        # Concatena a URL/Origem se for diferente
        if url and url not in last_url:
            last_url = f"{last_url}, {url}" if last_url else url
        logger.info(
            "[LastAnalysisStore] Cache incrementado com %d de %d issues para URL: %s (Total: %d, sessão: %s)",
            added_count, len(issues), url, len(last_issues), session,
        )
    else:
        last_issues = [dict(i) for i in issues]
        last_url = url
        logger.info(
            "[LastAnalysisStore] Cache atualizado com %d issues para URL: %s (sessão: %s)",
            len(issues), url, session,
        )

    _sessions[session] = (last_issues, last_url)
    _save_cache_to_disk(session)


def get_last_analysis(session_id: str | None = None) -> tuple[list[dict[str, Any]], str]:
    """Retorna os issues e a URL do último cache da sessão (carregando do disco se necessário)."""
    session = _resolve_session(session_id)
    if not _sessions.get(session, ([], ""))[0]:
        _load_cache_from_disk(session)
    return _sessions.get(session, ([], ""))
