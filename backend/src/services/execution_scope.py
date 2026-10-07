"""A single stall window, inherited by routing, repairs and workers.

Regra 8 (CLAUDE.md): nenhum relógio fixo encerra trabalho que continua
avançando. Por isso o `deadline` deste módulo NÃO é um teto de duração total: é
o instante em que a execução seria considerada TRAVADA se nada novo acontecesse.
Todo progresso real (evento publicado, token recebido, ferramenta concluída,
nova rodada do modelo, especialista concluído) desliza esse instante para
frente (`note_progress`). Uma tarefa grande leva o tempo que precisar enquanto
avança; só a falta de progresso por toda a janela (`patience`) a encerra, com
entrega parcial honesta.

A janela é adaptada pela complexidade que a IA declarou (`adapt`) e pelo que a
fase em andamento precisa (`extend_patience`); nunca é uma conta sobre o
tamanho do trabalho. Retries nunca reiniciam o que já foi provado.
ContextVars isolate simultaneous turns and propagate through asyncio.to_thread.

User gates (approval cards, agent questions) PAUSE the clock while they wait:
the deadline is shifted forward by the exact time the user takes, so a slow
click never consumes work budget. The next real task pays full price again.
"""

import asyncio
import contextvars
import functools
import threading
import time
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import ParamSpec, TypeVar

from backend.src.services import chat_progress


class TokenBudgetReachedError(Exception):
    """O limite de tokens que a PESSOA configurou foi atingido (regra 8).

    Não é timeout nem travamento: é a escolha dela. O trabalho pára no próximo limite de
    chamada, nada é refeito por cima e o que já foi apurado é entregue como parcial.
    """

    def __init__(self, used: int, limit: int) -> None:
        self.used = used
        self.limit = limit
        super().__init__(
            f"O limite de {limit} tokens que você configurou para esta resposta foi atingido (usei {used})."
        )


@dataclass
class ExecutionBudget:
    started_at: float
    deadline: float
    unit_seconds: float
    # While a user gate blocks the run, wall-clock time must not consume the
    # budget: `paused_since` marks when the current pause began and
    # `paused_total` accumulates every finished pause. `deadline` stays as the
    # theoretical end (started_at + allowance); comparisons subtract the
    # accumulated pause so the deadline effectively slides forward. Retries
    # never reset it and model complexity still moves the theoretical end --
    # only user waiting (no machine work) extends it.
    paused_since: float | None = None
    paused_total: float = 0.0
    # Janela de silêncio tolerada: quanto tempo sem NENHUM progresso significa
    # "travado". Começa igual à folga inicial e só cresce.
    patience: float = 0.0
    # Chamadas ao provedor em andamento. Uma chamada lenta não é um travamento: enquanto
    # houver uma em curso a janela não esgota (regra 8: mais paciência sobre a MESMA
    # chamada, nunca uma nova por cima). Quem encerra uma conexão pendurada é a camada
    # HTTP ou o cancelamento da pessoa.
    inflight: int = 0
    # Orçamento de custo configurado pela pessoa, em tokens (None = sem limite). É o único
    # teto de trabalho que existe: escolha dela, nunca um número embutido no código.
    token_limit: int | None = None
    tokens_used: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self.patience <= 0:
            self.patience = max(1.0, self.deadline - self.started_at)

    def _paused_now(self) -> float:
        return self.paused_total + (time.monotonic() - self.paused_since if self.paused_since is not None else 0.0)

    def effective_deadline(self) -> float:
        if self.inflight > 0:
            self.note_progress()  # esperar o provedor responder é espera legítima
        return self.deadline + self._paused_now()

    def add_tokens(self, count: int) -> None:
        with self._lock:
            self.tokens_used += max(0, int(count))

    @property
    def token_budget_reached(self) -> bool:
        return bool(self.token_limit) and self.tokens_used >= int(self.token_limit or 0)

    def begin_call(self) -> None:
        with self._lock:
            self.inflight += 1

    def end_call(self) -> None:
        with self._lock:
            self.inflight = max(0, self.inflight - 1)
        self.note_progress()  # a chamada terminou: a janela recomeça daqui

    def note_progress(self) -> None:
        """Registra progresso real: a janela de silêncio recomeça a partir de agora.

        Nunca encurta o prazo já calculado e é ignorado enquanto um portão do
        usuário está aberto (espera humana não é progresso de máquina).
        """
        if self.paused_since is not None:
            return
        self.deadline = max(self.deadline, time.monotonic() - self.paused_total + self.patience)

    def extend_patience(self, seconds: float) -> None:
        """A fase em andamento precisa de uma janela maior. Nunca encolhe."""
        self.patience = max(self.patience, float(seconds))
        self.note_progress()

    def adapt(self, complexity: str) -> None:
        # Contract enum, not a semantic classifier or a keyword heuristic.
        multiplier = {"low": 2, "medium": 4, "high": 8}[complexity]
        # A complexidade que a IA declarou define quanto silêncio é normal para
        # esta tarefa. Uma chamada auxiliar simples (complexidade baixa) nunca
        # reduz a janela já reservada para trabalho maior em andamento.
        self.extend_patience(self.unit_seconds * multiplier)

    def pause(self) -> None:
        """Abre a pausa (portão do usuário esperando). Nunca acumula pausa dupla."""
        if self.paused_since is None:
            self.paused_since = time.monotonic()

    def resume(self) -> None:
        """Fecha a pausa: o tempo que o humano levou deixa de consumir orçamento."""
        if self.paused_since is not None:
            self.paused_total += time.monotonic() - self.paused_since
            self.paused_since = None


_budget: contextvars.ContextVar[ExecutionBudget | None] = contextvars.ContextVar("execution_budget", default=None)
_P = ParamSpec("_P")
_R = TypeVar("_R")


def budgeted(function: Callable[_P, Awaitable[_R]]) -> Callable[_P, Awaitable[_R]]:
    """Every entry point adopts its caller's budget, including structured retries."""
    @functools.wraps(function)
    async def wrapped(*args: _P.args, **kwargs: _P.kwargs) -> _R:
        from backend.src.config.settings import get_settings

        with execution_scope(get_settings().agent_timeout_seconds):
            return await run_until_stalled(function(*args, **kwargs))

    return wrapped


def current_budget() -> ExecutionBudget | None:
    return _budget.get()


def add_tokens(count: int) -> None:
    """Soma os tokens de uma chamada ao orçamento do turno atual, se houver um."""
    budget = _budget.get()
    if budget is not None:
        budget.add_tokens(count)


def note_progress() -> None:
    """Sinaliza progresso real ao orçamento do turno atual, se houver um."""
    budget = _budget.get()
    if budget is not None:
        budget.note_progress()


async def run_until_stalled(awaitable: Awaitable[_R]) -> _R:
    """Espera o trabalho enquanto a execução avança; só desiste se ela travar.

    Substitui `asyncio.wait_for(..., timeout=<segundos fixos>)`. A cada volta o
    tempo até o travamento é reavaliado, porque o progresso (de qualquer parte
    do turno) desliza a janela para frente. Cancelamento do usuário continua
    sendo checado de forma determinística. Não há prazo legado: sem orçamento
    (não acontece nos caminhos do produto, que sempre abrem um) só o
    cancelamento encerra a espera.
    """
    if current_budget() is None:
        return await awaitable
    task = asyncio.ensure_future(awaitable)
    try:
        while True:
            check_execution()
            done, _pending = await asyncio.wait({task}, timeout=min(remaining_seconds(), 1.0))
            if done:
                return task.result()
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


def check_execution() -> None:
    if chat_progress.is_cancelled():
        raise InterruptedError("Execução interrompida pelo usuário.")
    budget = current_budget()
    if budget is not None and budget.token_budget_reached:
        raise TokenBudgetReachedError(budget.tokens_used, int(budget.token_limit or 0))
    if budget and time.monotonic() >= budget.effective_deadline():
        raise TimeoutError("A execução parou de avançar e foi encerrada; os resultados disponíveis são parciais.")


def remaining_seconds(limit: float | None = None) -> float:
    check_execution()
    budget = current_budget()
    remaining = max(0.001, budget.effective_deadline() - time.monotonic()) if budget else float("inf")
    return min(remaining, limit) if limit is not None else remaining


@contextmanager
def pause_for_user_gate() -> Iterator[None]:
    """Pausa o orçamento do turno enquanto um portão do usuário está aberto.

    Cartões de aprovação e perguntas do agente bloqueiam a thread worker sem
    fazer trabalho de máquina: esse tempo é do humano. O deadline com que o
    código compara (`effective_deadline`) desconta a pausa, então nem o turno
    expira enquanto o usuário pensa, nem o trabalho volta a pagar pela espera
    depois que ele clica. Cancelamento continua ativo durante a pausa (o
    `check_execution` dentro de `remaining_seconds` segue consultando).
    """
    budget = current_budget()
    if budget is None:
        yield  # Sem orçamento (rota non-chat): a pausa é no-op.
        return
    budget.pause()
    try:
        yield
    finally:
        budget.resume()


@contextmanager
def execution_scope(seconds: float, token_limit: int | None = None) -> Iterator[ExecutionBudget]:
    inherited = current_budget()
    if inherited is not None:
        check_execution()
        yield inherited
        return
    started = time.monotonic()
    budget = ExecutionBudget(
        started, started + max(1.0, seconds) * 2, max(1.0, seconds), token_limit=token_limit or None
    )
    token = _budget.set(budget)
    try:
        yield budget
    finally:
        _budget.reset(token)
