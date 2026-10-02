"""A single execution deadline, inherited by routing, repairs and workers.

Only model-supplied complexity changes the allowance. Retries never reset it.
ContextVars isolate simultaneous turns and propagate through asyncio.to_thread.
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

    def adapt(self, complexity: str) -> None:
        # Contract enum, not a semantic classifier or a keyword heuristic.
        multiplier = {"low": 2, "medium": 4, "high": 8}[complexity]
        self.deadline = self.started_at + self.unit_seconds * multiplier


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
    if budget and time.monotonic() >= budget.deadline:
        raise TimeoutError("O orçamento desta execução terminou; os resultados disponíveis são parciais.")


def remaining_seconds(limit: float | None = None) -> float:
    check_execution()
    budget = current_budget()
    remaining = max(0.001, budget.deadline - time.monotonic()) if budget else float("inf")
    return min(remaining, limit) if limit is not None else remaining


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
