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
class SquadPlan:
    objective: str
    domain: str = "digital_accessibility"
    tasks: list[SquadTask] = field(default_factory=list)
    quality_gates: list[str] = field(default_factory=list)

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
        }
