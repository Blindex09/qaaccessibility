"""A single execution deadline, inherited by routing, repairs and workers.

Only model-supplied complexity changes the allowance. Retries never reset it.
ContextVars isolate simultaneous turns and propagate through asyncio.to_thread.

User gates (approval cards, agent questions) PAUSE the clock while they wait:
the deadline is shifted forward by the exact time the user takes, so a slow
click never consumes work budget. The next real task pays full price again.
"""

import contextvars
import functools
import time
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import ParamSpec, TypeVar

from backend.src.services import chat_progress


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

    def _paused_now(self) -> float:
        return self.paused_total + (time.monotonic() - self.paused_since if self.paused_since is not None else 0.0)

    def effective_deadline(self) -> float:
        return self.deadline + self._paused_now()

    def adapt(self, complexity: str) -> None:
        # Contract enum, not a semantic classifier or a keyword heuristic.
        multiplier = {"low": 2, "medium": 4, "high": 8}[complexity]
        # Complexidade declarada move o fim teórico a partir do início
        # original (a pausa do humano não é consumo de trabalho). Pausas já
        # acumuladas continuam valendo: o deadline real segue descontando-as.
        # Uma chamada auxiliar simples não reduz a reserva já calculada para
        # as ondas da auditoria em andamento.
        self.deadline = max(self.deadline, self.started_at + self.unit_seconds * multiplier)

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
        import asyncio

        from backend.src.config.settings import get_settings

        with execution_scope(get_settings().agent_timeout_seconds):
            return await asyncio.wait_for(function(*args, **kwargs), timeout=remaining_seconds())

    return wrapped


def current_budget() -> ExecutionBudget | None:
    return _budget.get()


def check_execution() -> None:
    if chat_progress.is_cancelled():
        raise InterruptedError("Execução interrompida pelo usuário.")
    budget = current_budget()
    if budget and time.monotonic() >= budget.effective_deadline():
        raise TimeoutError("O orçamento desta execução terminou; os resultados disponíveis são parciais.")


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
def execution_scope(seconds: float) -> Iterator[ExecutionBudget]:
    inherited = current_budget()
    if inherited is not None:
        check_execution()
        yield inherited
        return
    started = time.monotonic()
    budget = ExecutionBudget(started, started + max(1.0, seconds) * 2, max(1.0, seconds))
    token = _budget.set(budget)
    try:
        yield budget
    finally:
        _budget.reset(token)
