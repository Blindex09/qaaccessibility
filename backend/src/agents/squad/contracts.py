"""Contratos pequenos e serializáveis para o fluxo da squad."""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from .roles import SquadRole


class TaskStatus(StrEnum):
    BACKLOG = "backlog"
    READY = "ready"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    REVIEW = "review"
    DONE = "done"


@dataclass
class SquadTask:
    id: str
    title: str
    role: SquadRole
    status: TaskStatus = TaskStatus.BACKLOG
    depends_on: list[str] = field(default_factory=list)
    acceptance_criteria: list[str] = field(default_factory=list)
    artifacts: list[str] = field(default_factory=list)
    specialist_agents: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RoleDecision:
    """O que um papel da squad ENTREGA ao terminar seu turno.

    Este é o contrato que torna a squad real em vez de decorativa: cada papel
    produz uma decisão concreta, e `handoff` é literalmente o que o próximo
    papel recebe como entrada. Sem isso, "papel" seria só um rótulo numa
    tarefa -- que era exatamente o estado anterior desta camada.

    - `decisions`: o que ficou decidido, em frases curtas e verificáveis.
    - `blockers`: o que impede avançar. Blocker não-vazio move a tarefa para
      BLOCKED; quem resolve é o Scrum Master (ou o usuário, quando é aprovação).
    - `handoff`: pares chave→valor que o próximo papel consome. É a entrega,
      não um resumo para humano ler.
    """

    role: SquadRole
    summary: str = ""
    decisions: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    handoff: dict[str, Any] = field(default_factory=dict)
    succeeded: bool = True
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": self.role.value,
            "summary": self.summary,
            "decisions": list(self.decisions),
            "blockers": list(self.blockers),
            "handoff": dict(self.handoff),
            "succeeded": self.succeeded,
            "error": self.error,
        }


@dataclass
class SquadPlan:
    objective: str
    domain: str = "digital_accessibility"
    tasks: list[SquadTask] = field(default_factory=list)
    quality_gates: list[str] = field(default_factory=list)
    decisions: list[RoleDecision] = field(default_factory=list)

    def task(self, task_id: str) -> SquadTask:
        for candidate in self.tasks:
            if candidate.id == task_id:
                return candidate
        raise KeyError(f"tarefa desconhecida no plano da squad: {task_id}")

    def dependencies_met(self, task: SquadTask) -> bool:
        """Portão real: uma tarefa só pode começar quando TODAS as suas
        dependências estão DONE. É o que impede documentação/entrega de
        fechar sem QA ter rodado."""
        return all(self.task(dep).status is TaskStatus.DONE for dep in task.depends_on)

    def to_dict(self) -> dict[str, Any]:
        return {
            "objective": self.objective,
            "domain": self.domain,
            "tasks": [
                {
                    **task.__dict__,
                    "role": task.role.value,
                    "status": task.status.value,
                }
                for task in self.tasks
            ],
            "quality_gates": list(self.quality_gates),
            "decisions": [decision.to_dict() for decision in self.decisions],
        }
