"""
trace_replay.py
Captura deterministica de trace (input + contexto/metadata + output de cada
passo de uma execucao de agente) e replay a partir do trace salvo -- ver
docs/conceitos-ia-para-desenvolvimento-de-software.md, secao 13: "Guardar
tudo que compos uma execucao permite REPRODUZIR o cenario exato depois, sem
gastar de novo o custo de rodar tudo do zero (API real, tempo)."

Quando um bug aparece em producao, o replay do trace ja capturado e o
primeiro passo de debug, nao uma nova rodada cara -- este modulo grava cada
passo (chamada de LLM, chamada de tool, decisao de roteamento) com seu input
e output exatos, persiste em JSON, e permite reproduzir a sequencia depois
sem re-executar nada.
"""

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# backend/src/services/trace_replay.py -> backend/data/traces
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_TRACE_DIR = os.path.join(_BACKEND_DIR, "data", "traces")


@dataclass
class TraceStep:
    step_index: int
    kind: str  # "llm_call" | "tool_call" | "decision"
    name: str
    input: Any
    output: Any
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Trace:
    trace_id: str
    steps: list[TraceStep] = field(default_factory=list)

    def record(self, kind: str, name: str, input: Any, output: Any, **metadata: Any) -> "TraceStep":
        """Grava um passo (chamada de LLM/tool/decisao) com seu input e output
        EXATOS -- e essa fidelidade que torna o trace replayable depois."""
        step = TraceStep(
            step_index=len(self.steps),
            kind=kind,
            name=name,
            input=input,
            output=output,
            metadata=dict(metadata),
        )
        self.steps.append(step)
        return step

    def to_dict(self) -> dict[str, Any]:
        return {"trace_id": self.trace_id, "steps": [asdict(s) for s in self.steps]}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Trace":
        trace = cls(trace_id=data["trace_id"])
        trace.steps = [TraceStep(**s) for s in data.get("steps", [])]
        return trace


def save_trace(trace: Trace, directory: str = DEFAULT_TRACE_DIR) -> str:
    """Persiste o trace completo em JSON -- sanitizacao de dado sensivel e
    responsabilidade de quem grava cada `record()` (ver Golden Dataset,
    secao 14: 'sanitiza -- remove dado sensivel' antes de reter qualquer
    captura de execucao real)."""
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, f"{trace.trace_id}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(trace.to_dict(), f, ensure_ascii=False, indent=2, default=str)
    logger.info(
        "[TraceReplay] Trace '%s' salvo com %d passos em %s",
        trace.trace_id,
        len(trace.steps),
        path,
    )
    return path


def load_trace(path: str) -> Trace:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return Trace.from_dict(data)


class TraceReplayer:
    """Reproduz um trace salvo passo a passo, devolvendo o OUTPUT ja gravado
    para cada passo em vez de re-executar (chamar LLM/rede/tool de novo) --
    permite debugar uma falha real de producao sem gastar API de novo."""

    def __init__(self, trace: Trace):
        self._trace = trace
        self._cursor = 0

    @property
    def trace_id(self) -> str:
        return self._trace.trace_id

    def has_next(self) -> bool:
        return self._cursor < len(self._trace.steps)

    def next(self) -> TraceStep:
        if not self.has_next():
            raise StopIteration(
                f"Trace '{self._trace.trace_id}' esgotado -- nao ha mais passos gravados para reproduzir."
            )
        step = self._trace.steps[self._cursor]
        self._cursor += 1
        return step

    def find_by_name(self, name: str) -> TraceStep | None:
        """Busca o primeiro passo gravado com o nome dado (ex: nome do agente
        ou da tool), sem avancar o cursor sequencial."""
        for step in self._trace.steps:
            if step.name == name:
                return step
        return None

    def all_steps(self) -> list[TraceStep]:
        return list(self._trace.steps)

    def reset(self) -> None:
        self._cursor = 0
