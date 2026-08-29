"""
eval_stats.py
Utilitarios estatisticos para avaliacao multi-run de agentes de IA (Pass@k,
taxa de sucesso, variancia amostral, intervalo de confianca) -- ver
docs/conceitos-ia-para-desenvolvimento-de-software.md, secao 12: "1 execucao
= evidencia fraca. 20/20 execucoes = confianca muito maior."

Diferente de um teste tradicional (roda 1 vez, passou ou falhou), um agente de
IA e input X -> talvez A, talvez B, talvez C, mesmo em temperatura 0. Este
modulo roda uma tentativa de eval N vezes de forma independente e agrega em
estatisticas honestas sobre a incerteza, em vez de tratar 1 execucao como
prova definitiva.
"""

import logging
import math
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class MultiRunEvalResult:
    trial_results: list[bool]
    n_runs: int
    successes: int
    success_rate: float
    variance: float
    pass_at_k: dict[int, float]
    confidence_interval_95: tuple[float, float]
    trial_errors: list[str] = field(default_factory=list)

    @property
    def is_flaky(self) -> bool:
        """Flakiness: falha intermitente sem mudanca de input -- nem sempre
        passa, nem sempre falha. Um resultado 100% ou 0% consistente nao e
        flaky (e um sucesso ou falha estavel); qualquer mistura e."""
        return 0 < self.successes < self.n_runs


def success_rate(results: list[bool]) -> float:
    """Percentual de execucoes corretas na amostra."""
    if not results:
        return 0.0
    return sum(1 for r in results if r) / len(results)


def sample_variance(results: list[bool]) -> float:
    """Variancia amostral (correcao de Bessel, n-1) da taxa de sucesso binaria.
    Quanto mais proxima de 0, mais consistente o comportamento entre execucoes
    identicas; valores altos sinalizam variabilidade real do modelo."""
    n = len(results)
    if n < 2:
        return 0.0
    p = success_rate(results)
    return sum(((1.0 if r else 0.0) - p) ** 2 for r in results) / (n - 1)


def pass_at_k(results: list[bool], k: int) -> float:
    """Pass@k: probabilidade de acertar pelo menos 1 vez ao amostrar k
    tentativas sem reposicao das n execucoes observadas -- estimador
    nao-enviesado padrao (HumanEval/Codex). k e limitado a n."""
    n = len(results)
    if n == 0 or k <= 0:
        return 0.0
    k = min(k, n)
    c = sum(1 for r in results if r)
    if n - c < k:
        return 1.0
    prob_all_sampled_fail = 1.0
    for i in range(k):
        prob_all_sampled_fail *= (n - c - i) / (n - i)
    return 1.0 - prob_all_sampled_fail


def confidence_interval_95(results: list[bool]) -> tuple[float, float]:
    """Intervalo de confianca de 95% (aproximacao normal/Wald) sobre a taxa de
    sucesso -- amostras pequenas geram intervalos largos de proposito, pra
    nunca disfarcar incerteza real como precisao falsa."""
    n = len(results)
    if n == 0:
        return (0.0, 0.0)
    p = success_rate(results)
    if n == 1:
        return (0.0, 1.0)
    margin = 1.96 * math.sqrt((p * (1 - p)) / n)
    return (max(0.0, p - margin), min(1.0, p + margin))


async def run_multi_trial(
    trial_fn: Callable[[], Awaitable[bool]],
    n_runs: int = 5,
    k_values: tuple[int, ...] = (1,),
) -> MultiRunEvalResult:
    """Roda `trial_fn` (uma tentativa de eval que retorna True/False de
    sucesso) `n_runs` vezes de forma independente e agrega em estatisticas.

    Excecao de UMA tentativa conta como falha daquela tentativa apenas --
    nunca derruba as outras (mesma disciplina de graceful degradation do
    orchestrator, aplicada a avaliacao)."""
    trial_results: list[bool] = []
    trial_errors: list[str] = []
    for i in range(n_runs):
        try:
            ok = await trial_fn()
            trial_results.append(bool(ok))
        except Exception as exc:
            trial_results.append(False)
            trial_errors.append(f"trial {i}: {exc}")
            logger.warning(
                "[MultiRunEval] Tentativa %d/%d levantou excecao: %s", i + 1, n_runs, exc
            )

    successes = sum(1 for r in trial_results if r)
    result = MultiRunEvalResult(
        trial_results=trial_results,
        n_runs=n_runs,
        successes=successes,
        success_rate=success_rate(trial_results),
        variance=sample_variance(trial_results),
        pass_at_k={k: pass_at_k(trial_results, k) for k in k_values},
        confidence_interval_95=confidence_interval_95(trial_results),
        trial_errors=trial_errors,
    )
    if result.is_flaky:
        logger.warning(
            "[MultiRunEval] Resultado flaky: %d/%d sucessos (taxa=%.0f%%) -- "
            "comportamento nao-determinístico detectado entre execucoes identicas.",
            successes, n_runs, result.success_rate * 100,
        )
    return result
