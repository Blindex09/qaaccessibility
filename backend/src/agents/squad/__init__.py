"""Coordenação de squad virtual especializada em acessibilidade digital."""

from .contracts import SquadPlan, SquadTask
from .coordinator import build_squad_plan
from .roles import SquadRole

__all__ = ["SquadPlan", "SquadRole", "SquadTask", "build_squad_plan"]
