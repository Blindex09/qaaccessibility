"""Janela adaptativa de uma fase de análise (regra 8: sem relógio fixo).

O modelo decide a complexidade semântica. Este módulo só transforma fatos já
decididos/observáveis (quantidade de especialistas, concorrência, qualidade
pedida) na janela de SILÊNCIO que essa fase tolera antes de ser considerada
travada. Dentro de um turno de chat a fase compartilha o mesmo orçamento do
turno: cada especialista que termina é progresso e desliza a janela, então o
total de especialistas NÃO cria um teto de duração. Fora do chat (sem orçamento
herdado) o comportamento legado de prazo agregado é mantido.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field

from backend.src.services.execution_scope import ExecutionBudget


@dataclass
class AdaptiveExecutionBudget:
    """Visão da janela da fase: viva (herdada do turno) ou estática (legado)."""

    started_at: float
    deadline: float
    selected_agents: int
    parallelism: int
    tradeoff: int
    scope: ExecutionBudget | None = field(default=None, repr=False)

    @property
    def remaining_seconds(self) -> float:
        end = self.scope.effective_deadline() if self.scope is not None else self.deadline
        return max(0.0, end - time.monotonic())

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
    """Dimensiona a janela de silêncio da fase de análise.

    Não classifica intenção, não escolhe agentes e não usa tamanho/keywords do
    HTML. Também não cria um contador paralelo de rodadas: as fases da análise
    compartilham o mesmo orçamento do turno.
    """
    safe_parallelism = max(1, int(parallelism))
    safe_agents = max(0, int(selected_agents))
    safe_timeout = max(1.0, float(per_agent_timeout))
    safe_tradeoff = max(0, min(10, int(tradeoff)))
    quality_slack = 1.0 + ((10 - safe_tradeoff) / 10.0) * 0.25
    started_at = time.monotonic()
    from backend.src.services.execution_scope import current_budget

    parent = current_budget()
    if parent is not None:
        # Entre dois progressos (um especialista concluído, um evento) o
        # silêncio normal é o de um especialista trabalhando, não o da soma
        # de todas as ondas. Mais especialistas não aumentam o teto: cada um
        # que termina desliza a janela.
        parent.extend_patience(safe_timeout * quality_slack)
        return AdaptiveExecutionBudget(
            started_at=started_at,
            deadline=parent.effective_deadline(),
            selected_agents=safe_agents,
            parallelism=safe_parallelism,
            tradeoff=safe_tradeoff,
            scope=parent,
        )
    waves = max(1, math.ceil(safe_agents / safe_parallelism))
    deadline_seconds = (waves * safe_timeout * quality_slack) + safe_timeout
    return AdaptiveExecutionBudget(
        started_at=started_at,
        deadline=started_at + deadline_seconds,
        selected_agents=safe_agents,
        parallelism=safe_parallelism,
        tradeoff=safe_tradeoff,
    )
