"""Canal de progresso, clarify, cancelamento e steer para o chat agentico.

Quatro mecanismos, todos para levar o que acontece DENTRO da execucao (orchestrator,
subagentes, perguntas do agente, botão "parar", correção do usuário) ate o stream SSE do chat:

1. Sink de progresso (ContextVar): o `chat_runtime` registra uma funcao que
   empurra eventos na fila do stream. O `orchestrator` (que roda alguns niveis
   abaixo, inclusive em thread de worker via ``asyncio.to_thread`` +
   ``asyncio.run``) chama :func:`emit`. ContextVar propaga pelo ``to_thread`` e
   pelo ``asyncio.run``, entao o evento chega na fila do loop principal. Fora do
   chat (rotas /analyze) não ha sink registrado -> :func:`emit` e no-op.

2. Registro de clarify: quando o agente pergunta algo (tool ``clarify``), o
   callback bloqueia numa ``threading.Event`` ate o usuário responder via
   ``POST /chat/clarify``. Espelha o padrão ``_block``/``_pending`` de bloqueio síncrono.

3. Registro de cancelamento: `stream_chat` cria um token no início do turno e
   entrega ao cliente via evento ``stream_id``. ``POST /chat/cancel`` seta um
   ``asyncio.Event`` associado. `stream_chat` espera na fila E nesse evento
   simultaneamente (``asyncio.wait``) -- os dois vivem no mesmo loop de evento,
   então não precisa de ``threading.Event`` como o clarify (que e sinalizado
   de dentro da thread worker do agente). Best-effort por natureza: para de
   entregar eventos ao cliente e cancela a task assim que possível, mas não
   aborta uma chamada HTTP síncrona do provider já em andamento na thread.

4. Registro de steer: o usuário pode enviar uma correção/redirecionamento
   enquanto o turno ainda está rodando via ``POST /chat/steer``. Fica pendente
   até o loop de tool-calling do `AIAgent` consultar entre iterações
   (`steer_check` em ``run_agent.py``) e injetar como nova mensagem de
   usuário -- nada do que já foi produzido é descartado. Best-effort pela
   mesma razão do cancelamento: não interrompe uma chamada de LLM/ferramenta
   já em andamento, só o próximo ponto de checagem.
"""

import asyncio
import contextlib
import contextvars
import threading
import uuid
from collections.abc import Callable
from typing import Any

# Funcao que recebe um evento (dict) e o entrega ao stream do chat. None fora do chat.
_sink: contextvars.ContextVar[Callable[[dict[str, Any]], None] | None] = contextvars.ContextVar(
    "chat_progress_sink", default=None
)
_cancel_check: contextvars.ContextVar[Callable[[], bool] | None] = contextvars.ContextVar(
    "chat_progress_cancel_check", default=None
)


def set_sink(fn: Callable[[dict[str, Any]], None]) -> contextvars.Token:
    """Registra o sink de progresso para o turno atual. Devolve o token de reset."""
    return _sink.set(fn)


def reset_sink(token: contextvars.Token) -> None:
    with contextlib.suppress(ValueError, LookupError):
        _sink.reset(token)


def set_cancel_check(fn: Callable[[], bool] | None) -> contextvars.Token:
    """Vincula o cancelamento do turno ao trabalho interno do agente."""
    return _cancel_check.set(fn)


def reset_cancel_check(token: contextvars.Token) -> None:
    with contextlib.suppress(ValueError, LookupError):
        _cancel_check.reset(token)


def is_cancelled() -> bool:
    """Consulta o cancelamento sem acoplar o orquestrador ao transporte SSE."""
    fn = _cancel_check.get()
    try:
        return bool(fn and fn())
    except Exception:
        return False


def emit(event: dict[str, Any]) -> None:
    """Empurra um evento de progresso ao chat, se houver sink. No-op caso contrario."""
    fn = _sink.get()
    if fn is None:
        return
    # O progresso nunca pode derrubar a análise.
    with contextlib.suppress(Exception):
        fn(event)


def emit_tool_progress(tool_call_id: str | None, name: str, message: str) -> None:
    """Emite um evento intermediário de andamento de ferramenta (tool_progress).

    O frontend acumula essas mensagens em `toolCall.logs` e mostra enquanto a
    ferramenta está `running`. Não deve ser usado como live region: o leitor de
    tela lê os logs quando o usuário navega até o card, sem anunciar
    automaticamente cada mensagem."""
    emit(
        {
            "type": "tool_progress",
            "tool_call_id": tool_call_id,
            "name": name,
            "message": message,
        }
    )


# ── Clarify: perguntas interativas do agente ──────────────────────────────
_pending: dict[str, threading.Event] = {}
_answers: dict[str, str] = {}


def new_clarify() -> tuple[str, threading.Event]:
    """Cria um request_id + Event para uma pergunta pendente."""
    rid = uuid.uuid4().hex
    ev = threading.Event()
    _pending[rid] = ev
    return rid, ev


def wait_clarify(rid: str, ev: threading.Event, timeout: float = 300.0) -> str:
    """Bloqueia ate o usuário responder (ou timeout). Retorna a resposta ("" se não veio)."""
    ev.wait(timeout=timeout)
    _pending.pop(rid, None)
    return _answers.pop(rid, "")


def answer_clarify(rid: str, answer: str) -> bool:
    """Entrega a resposta do usuário e desbloqueia o agente. False se o id não existe."""
    ev = _pending.get(rid)
    if ev is None:
        return False
    _answers[rid] = answer
    ev.set()
    return True


# ── Cancelamento: interromper um turno de chat em andamento ──────────────
_cancel_events: dict[str, asyncio.Event] = {}


def new_cancel_token() -> str:
    """Cria um token de cancelamento para o turno atual. Deve ser limpo com
    :func:`clear_cancel_token` quando o turno terminar (sucesso, erro ou cancelamento)."""
    token = uuid.uuid4().hex
    _cancel_events[token] = asyncio.Event()
    return token


def cancel_event(token: str) -> asyncio.Event | None:
    """Devolve o `asyncio.Event` do token, ou None se já foi limpo/não existe."""
    return _cancel_events.get(token)


def request_cancel(token: str) -> bool:
    """Sinaliza cancelamento. False se o token não existe (turno já terminou)."""
    ev = _cancel_events.get(token)
    if ev is None:
        return False
    ev.set()
    return True


def clear_cancel_token(token: str) -> None:
    _cancel_events.pop(token, None)
    _pending_steer.pop(token, None)


# ── Steer: redirecionar um turno em andamento sem perder progresso ───────
# Canal simetrico ao cancelamento acima, mas em vez de parar o turno, entrega
# uma correcao/redirecionamento para ser injetada como proxima mensagem de
# usuario no loop de tool-calling do AIAgent (ver run_agent.py::steer_check).
# Best-effort pela mesma razao do cancelamento: so e consultado ENTRE
# iteracoes, nunca aborta uma chamada de LLM/ferramenta ja em andamento.
_pending_steer: dict[str, str] = {}


def request_steer(token: str, message: str) -> bool:
    """Registra uma correcao para o turno identificado por `token`. Sera
    entregue (uma unica vez) na proxima checagem entre iteracoes. False se o
    token nao existe (turno ja terminou/nao existe)."""
    if token not in _cancel_events:
        return False
    _pending_steer[token] = message
    return True


def pop_pending_steer(token: str) -> str | None:
    """Consome a correcao pendente para este turno, se houver. Chamado pelo
    AIAgent a cada iteracao do loop de tool-calling."""
    return _pending_steer.pop(token, None)
