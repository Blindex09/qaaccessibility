"""
session_context.py
Fonte única do "conversation_id corrente" para todos os stores por sessão do
chat (last_analysis_store, fix_checkpoint_store, last_fix_store,
chat_history_store). Viaja por ContextVar (propaga por `asyncio.to_thread`,
como o sink de progresso em chat_progress.py) -- as tools não precisam
receber o id por parâmetro.

Antes de existir este módulo, `last_analysis_store.py` e
`fix_checkpoint_store.py` cada um definia seu PRÓPRIO ContextVar idêntico e
`chat_runtime.py` tinha que setar os dois em paralelo, sempre com o mesmo
valor -- duplicação real (regra do projeto: "zero duplicação de fluxos,
rotas, helpers"). `last_fix_store.py` nunca teve um ContextVar próprio,
por isso ficava global (não isolado por sessão) -- dois usuários corrigindo
páginas diferentes ao mesmo tempo sobrescreviam a pré-visualização um do
outro. Todos os stores por sessão agora leem deste único módulo.
"""

import contextlib
import contextvars

DEFAULT_SESSION_ID = "default"

_current_session: contextvars.ContextVar[str] = contextvars.ContextVar(
    "conversation_session", default=DEFAULT_SESSION_ID
)


def set_current_session(session_id: str | None) -> contextvars.Token:
    """Define a sessão corrente do turno de chat. Devolve o token para reset."""
    return _current_session.set(session_id or DEFAULT_SESSION_ID)


def reset_current_session(token: contextvars.Token) -> None:
    """Idempotente: resetar o mesmo token duas vezes (ex.: cleanup duplicado
    num finally aninhado) nunca deve derrubar o request -- só a primeira
    chamada tem efeito, as demais são no-op."""
    with contextlib.suppress(ValueError, LookupError, RuntimeError):
        _current_session.reset(token)


def resolve_session(session_id: str | None = None) -> str:
    """Override explícito (`session_id`) tem prioridade; senão lê o ContextVar corrente."""
    return session_id or _current_session.get()
