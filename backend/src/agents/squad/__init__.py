"""Squad de acessibilidade: papéis reais, quadro com estado e portões que bloqueiam."""

from .contracts import RoleDecision, SquadPlan, SquadTask, TaskStatus
from .coordinator import SquadCoordinator, build_squad_plan
from .roles import SquadRole

__all__ = [
    "RoleDecision",
    "SquadCoordinator",
    "SquadPlan",
    "SquadRole",
    "SquadTask",
    "TaskStatus",
    "build_squad_plan",
]
