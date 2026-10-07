"""Janela adaptativa de uma fase de análise (regra 8: sem relógio fixo).

O modelo decide a complexidade semântica. Este módulo só transforma fatos já
decididos/observáveis (quantidade de especialistas, concorrência, qualidade
pedida) na janela de SILÊNCIO que essa fase tolera antes de ser considerada
travada. A fase compartilha o orçamento do turno: cada especialista que termina
é progresso e desliza a janela, então o total de especialistas NÃO cria um teto
de duração. Fora de um turno (sem orçamento herdado) a fase usa um orçamento
próprio com a mesma semântica: a janela recomeça a cada `note_progress`.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from backend.src.services.execution_scope import ExecutionBudget


@dataclass
class AdaptiveExecutionBudget:
    """Visão da janela de silêncio da fase de análise."""

    started_at: float
    selected_agents: int
    parallelism: int
    tradeoff: int
    scope: ExecutionBudget = field(repr=False)

    @property
    def deadline(self) -> float:
        """Instante em que a fase seria considerada travada se nada avançar."""
        return self.scope.effective_deadline()

    @property
    def remaining_seconds(self) -> float:
        return max(0.0, self.deadline - time.monotonic())

    @property
    def expired(self) -> bool:
        return self.remaining_seconds <= 0.0

    def note_progress(self) -> None:
        self.scope.note_progress()


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

    # Entre dois progressos (um especialista concluído, um evento) o silêncio
    # normal é o de um especialista trabalhando, não o da soma de todas as
    # ondas. Mais especialistas não aumentam o teto: cada um que termina
    # desliza a janela.
    window = safe_timeout * quality_slack
    scope = current_budget()
    if scope is not None:
        scope.extend_patience(window)
    else:
        scope = ExecutionBudget(started_at, started_at + window, safe_timeout, patience=window)
    return AdaptiveExecutionBudget(
        started_at=started_at,
        selected_agents=safe_agents,
        parallelism=safe_parallelism,
        tradeoff=safe_tradeoff,
        scope=scope,
    )
