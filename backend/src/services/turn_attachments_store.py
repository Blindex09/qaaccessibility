"""Arquivos que o usuário anexou no turno, guardados como DADO por sessão.

Por que este store existe -- achado real (2026-08-30, execução ponta a ponta):
o usuário anexou um HTML de 68 caracteres; ao chamar `fix_and_zip_files` o
modelo passou 406 caracteres em `files`, com conteúdo que nunca esteve no
arquivo (um `<h1>Produto em Destaque</h1>`, um `alt="Camiseta azul, tamanho M"`,
uma "Loja Online"). O pipeline corrigiu a invenção: o ZIP baixado traria uma
página que o usuário nunca escreveu, e o painel antes/depois mostraria um
"antes" que não é o arquivo dele.

Já existia o guarda para o caso inverso -- `_looks_like_placeholder_file_list`,
para quando o modelo manda `"---"` em vez de omitir `files`. Faltava o guarda
para a fabricação, e ele só ficou possível quando o anexo passou a viajar
estruturado (`ChatRequest.attachments`): antes o conteúdo do usuário chegava
embutido na prosa e não havia cópia fiel com que comparar.

Mesmo padrão dos demais stores de sessão do projeto (`last_analysis_store`,
`last_analyzed_content_store`): isolado por `conversation_id`, em memória, com
o ciclo de vida do turno.
"""

import logging
from typing import Any

from backend.src.services.session_context import resolve_session

logger = logging.getLogger(__name__)

# Limite defensivo: o store guarda o que o usuário mandou neste turno, não um
# histórico. Evita segurar conteúdo grande além do necessário.
_MAX_ANEXOS = 50

_sessions: dict[str, list[dict[str, str]]] = {}


def set_turn_attachments(anexos: list[dict[str, str]] | None, session_id: str | None = None) -> None:
    """Registra os anexos do turno corrente (sobrescreve os do turno anterior)."""
    session = resolve_session(session_id)
    limpos = [
        {"name": str(a.get("name") or ""), "content": str(a.get("content") or "")}
        for a in (anexos or [])
        if str(a.get("content") or "").strip()
    ][:_MAX_ANEXOS]
    if limpos:
        _sessions[session] = limpos
        logger.info("[TurnAttachmentsStore] %d anexo(s) registrado(s) (sessão %s).", len(limpos), session)
    else:
        # Turno sem anexo NÃO apaga o do turno anterior: o usuário anexa uma vez
        # e nos turnos seguintes só conversa ("pode corrigir", "sim"). Apagar
        # aqui devolveria o guarda ao mesmo ponto cego que ele existe para cobrir.
        _sessions.setdefault(session, [])


def get_turn_attachments(session_id: str | None = None) -> list[dict[str, str]]:
    """Anexos conhecidos da sessão (lista vazia quando não houve nenhum)."""
    return list(_sessions.get(resolve_session(session_id), []))


def clear_turn_attachments(session_id: str | None = None) -> None:
    _sessions.pop(resolve_session(session_id), None)


def encontrar_anexo(path: str, anexos: list[dict[str, Any]] | None = None) -> dict[str, str] | None:
    """Anexo correspondente a um caminho de arquivo, quando dá para afirmar qual é.

    Casa pelo nome (exato ou sufixo, porque o modelo às vezes prefixa um
    diretório) e, quando existe um único anexo, aceita ele como o alvo. Devolve
    `None` quando a correspondência é ambígua -- na dúvida o guarda não age.
    """
    conhecidos = anexos if anexos is not None else get_turn_attachments()
    if not conhecidos:
        return None
    alvo = (path or "").strip().replace("\\", "/")
    for anexo in conhecidos:
        nome = (anexo.get("name") or "").strip().replace("\\", "/")
        if nome and (alvo == nome or alvo.endswith("/" + nome) or nome.endswith("/" + alvo)):
            return dict(anexo)
    if len(conhecidos) == 1:
        return dict(conhecidos[0])
    return None
