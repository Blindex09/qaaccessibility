"""
agent_hooks.py
Sistema de hooks plugáveis do harness (AIAgent/call_llm) -- pontos de
extensão do ciclo de vida que código externo pode registrar/desregistrar em
runtime, sem alterar a assinatura do AIAgent nem os call sites existentes.

Por que isso é diferente do que já existia: `tool_start_callback`,
`tool_complete_callback` etc. em `run_agent.py::AIAgent.__init__` são
estratégias FIXAS -- um único callback por evento, passado uma vez na
construção, usadas pelo streaming de progresso do chat (`chat_progress.py`).
Não dá pra registrar um segundo observador sem editar o construtor e todo
call site. Hooks aqui são um REGISTRO: N hooks por evento, adicionados ou
removidos a qualquer momento, e disparados automaticamente por QUALQUER
chamada real (`llm_client.call_llm`, `run_agent.py::AIAgent` tool loop) --
o próprio harness os aciona a partir do seu ciclo de vida, não de um
parâmetro que cada chamador precisa lembrar de passar.

Padrão 2026 (harness engineering): "anytime an agent makes a mistake, you
engineer a solution so it never happens again" -- hooks são o ponto de
extensão que permite isso sem tocar no núcleo do harness: telemetria custom,
auditoria de segurança, product tracking, guardrails de terceiros, tudo pode
se registrar aqui.

Garantia central: um hook NUNCA pode quebrar o loop do agente. Toda chamada
de hook é isolada em try/except -- uma exceção num hook vira um log de aviso,
nunca propaga pro chamador real.
"""

import logging
import threading
import uuid
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

# Eventos suportados -- cada um documenta a assinatura exata que os hooks
# registrados recebem quando disparados.
PRE_TOOL_CALL = "pre_tool_call"  # (tool_id, name, args) -> None
POST_TOOL_CALL = "post_tool_call"  # (tool_id, name, args, result) -> None
PRE_LLM_CALL = "pre_llm_call"  # (provider, model, task_id, agent_label) -> None
POST_LLM_CALL = "post_llm_call"  # (provider, model, task_id, agent_label, success, duration_ms) -> None
ON_ERROR = "on_error"  # (provider, model, task_id, agent_label, error) -> None

_KNOWN_EVENTS = frozenset({PRE_TOOL_CALL, POST_TOOL_CALL, PRE_LLM_CALL, POST_LLM_CALL, ON_ERROR})

_lock = threading.Lock()
_hooks: dict[str, dict[str, Callable[..., Any]]] = {event: {} for event in _KNOWN_EVENTS}


def register_hook(event: str, fn: Callable[..., Any]) -> str:
    """Registra um hook para `event`. Devolve um token -- passe para
    `unregister_hook` para remover. Levanta ValueError para evento desconhecido
    (falha explícita em vez de silenciosamente nunca disparar)."""
    if event not in _KNOWN_EVENTS:
        raise ValueError(f"Evento de hook desconhecido: {event!r}. Válidos: {sorted(_KNOWN_EVENTS)}")
    token = uuid.uuid4().hex
    with _lock:
        _hooks[event][token] = fn
    return token


def unregister_hook(event: str, token: str) -> None:
    """Remove um hook previamente registrado. No-op se já removido/inexistente."""
    with _lock:
        _hooks.get(event, {}).pop(token, None)


def fire(event: str, *args: Any, **kwargs: Any) -> None:
    """Dispara todos os hooks registrados para `event`, na ordem de registro.

    Isola cada hook em try/except -- uma falha de um observador nunca deve
    impedir os demais de rodar nem propagar pro loop real do agente. Erros
    vão para o log, não para o chamador.
    """
    with _lock:
        callbacks = list(_hooks.get(event, {}).values())
    for fn in callbacks:
        try:
            fn(*args, **kwargs)
        except Exception:
            logger.exception("[AgentHooks] Hook para evento '%s' falhou", event)


def clear_all_hooks() -> None:
    """Remove todos os hooks de todos os eventos. Uso principal: isolamento entre testes."""
    with _lock:
        for event in _hooks:
            _hooks[event].clear()


def registered_count(event: str) -> int:
    with _lock:
        return len(_hooks.get(event, {}))
