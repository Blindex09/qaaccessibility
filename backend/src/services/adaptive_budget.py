"""Orçamento único e adaptativo para uma execução de análise.

O modelo decide a complexidade semântica. Este módulo só transforma fatos já
decididos/observáveis em um deadline agregado: quantidade de especialistas,
concorrência permitida, timeout operacional e tradeoff classificado.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class AdaptiveExecutionBudget:
    """Deadline único compartilhado por uma fase da execução."""

    started_at: float
    deadline: float
    selected_agents: int
    parallelism: int
    tradeoff: int

    @property
    def remaining_seconds(self) -> float:
        return max(0.0, self.deadline - time.monotonic())

    @property
    def expired(self) -> bool:
        return self.remaining_seconds <= 0.0


def create_analysis_budget(
    *,
    selected_agents: int,
    parallelism: int,
    per_agent_timeout: float,
    tradeoff: int,
) -> AdaptiveExecutionBudget:
    """Cria um deadline proporcional às ondas e à qualidade solicitada.

    Não classifica intenção, não escolhe agentes e não usa tamanho/keywords do
    HTML. Também não cria um contador paralelo de rodadas: as fases da análise
    compartilham este mesmo deadline.
    """
    safe_parallelism = max(1, int(parallelism))
    safe_agents = max(0, int(selected_agents))
    safe_timeout = max(1.0, float(per_agent_timeout))
    safe_tradeoff = max(0, min(10, int(tradeoff)))
    waves = max(1, math.ceil(safe_agents / safe_parallelism))
    quality_slack = 1.0 + ((10 - safe_tradeoff) / 10.0) * 0.25
    deadline_seconds = (waves * safe_timeout * quality_slack) + safe_timeout
    started_at = time.monotonic()
    from backend.src.services.execution_scope import current_budget

    parent = current_budget()
    deadline = started_at + deadline_seconds
    if parent:
        deadline = min(deadline, parent.deadline)
    return AdaptiveExecutionBudget(
        started_at=started_at,
        deadline=deadline,
        selected_agents=safe_agents,
        parallelism=safe_parallelism,
        tradeoff=safe_tradeoff,
    )
