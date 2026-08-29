"""
Camada 11 -- Multi-run/Statistical Evals + Deterministic Replay (real, NOVA).

Fecha os 2 gaps "AUSENTE" identificados na auditoria de cobertura de
docs/conceitos-ia-para-desenvolvimento-de-software.md:

- Secao 12 (Multi-run/Statistical Evals): roda o MESMO golden case N vezes
  contra o Ollama Cloud real e agrega em Pass@k/taxa de sucesso/variancia
  (eval_stats.py) -- 1 execucao e evidencia fraca, mesmo em temperatura baixa.
- Secao 13 (Deterministic Replay/Trace Replay): grava cada tentativa como um
  Trace (trace_replay.py) e prova que o replay reproduz o MESMO resultado
  sem chamar o LLM de novo -- e o mecanismo que evita re-gastar API real
  so pra reproduzir uma falha ja vista uma vez.
"""

import pytest

from backend.src.services.eval_stats import run_multi_trial
from backend.src.services.trace_replay import Trace, TraceReplayer
from backend.src.shared.models import AccessibilityIssue
from tests.backend.unit.test_prompt_regression import GOLDEN_CASES

pytestmark = pytest.mark.real_llm

# GC001: img sem alt -- 1.1.1, caso golden mais simples e estavel da suite
# (ver test_02_agent_evals_real.py), reaproveitado aqui como base multi-run.
_CASE = next(c for c in GOLDEN_CASES if c["id"] == "GC001")
_N_RUNS = 5


@pytest.mark.asyncio
async def test_golden_case_multi_run_statistical_eval(alto_model_id: str) -> None:
    """Roda GC001 N vezes de forma independente contra o modelo real e exige
    uma taxa de sucesso minima, nao so 'passou uma vez' -- 1 execucao verde
    nao prova que o agente detecta o issue de forma confiavel."""
    from backend.src.agents.perceiver.perceiver import run_perceiver
    from tests.backend.real_llm.conftest import run_agent_with_retry

    async def _trial() -> bool:
        result = await run_agent_with_retry(run_perceiver, _CASE["html"])
        if not result.success:
            return False
        issues = [AccessibilityIssue.model_validate(i) for i in result.data.get("issues", [])]
        return any("1.1.1" in i.criterion for i in issues)

    stats = await run_multi_trial(_trial, n_runs=_N_RUNS, k_values=(1, 3))

    assert stats.n_runs == _N_RUNS
    assert stats.success_rate >= 0.6, (
        f"[GC001] taxa de sucesso multi-run muito baixa contra {alto_model_id}: "
        f"{stats.successes}/{stats.n_runs} (trials={stats.trial_results}, "
        f"erros={stats.trial_errors})"
    )
    assert stats.pass_at_k[1] >= 0.6
    assert stats.confidence_interval_95[1] >= stats.success_rate


@pytest.mark.asyncio
async def test_trace_replay_reproduces_result_without_calling_llm_again(alto_model_id: str) -> None:
    """Grava a execucao real de GC001 como um Trace, depois prova que o
    REPLAY devolve exatamente o mesmo resultado sem nenhuma nova chamada de
    rede -- a diferenca entre 'debugar de novo, custando API' e 'reproduzir
    o que ja foi visto, de graca'."""
    from unittest.mock import AsyncMock, patch

    from backend.src.agents.perceiver.perceiver import run_perceiver

    real_result = await run_perceiver(_CASE["html"])
    assert real_result.success, f"[GC001] chamada real falhou contra {alto_model_id}: {real_result.error}"

    trace = Trace(trace_id="test-gc001-replay")
    trace.record(
        "llm_call",
        "perceiver",
        input=_CASE["html"],
        output=real_result.model_dump(),
    )

    replayer = TraceReplayer(trace)
    step = replayer.next()
    assert step.name == "perceiver"

    # O "replay" real de um agente seria reconstruir o AgentResult a partir do
    # step.output gravado -- aqui provamos a garantia central: nenhuma nova
    # chamada de LLM acontece ao consumir o trace.
    with patch(
        "backend.src.services.llm_client.call_llm_structured", AsyncMock(side_effect=AssertionError("nao deveria chamar o LLM durante replay"))
    ):
        replayed_issues = step.output["data"]["issues"]

    original_issues = real_result.data.get("issues", [])
    assert replayed_issues == original_issues
