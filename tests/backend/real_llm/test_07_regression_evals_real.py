"""
Camada 7/9 -- Regression Evals (real).

Compara o resultado de uma execução real de HOJE contra um baseline gravado
(`baseline_snapshot.json`, capturado contra o Ollama Cloud tier alto). Ao
contrário de Agent Evals (camada 2, que valida contra uma expectativa
WCAG fixa), esta camada detecta DRIFT: o modelo por trás do provider mudou de
versão, o prompt do agente foi editado, ou o roteamento do model_router
passou a resolver outro modelo -- qualquer coisa que faça o comportamento
real divergir do que foi validado e registrado como "conhecido bom".

Regenerar o baseline (script em docs/real_llm_testing.md) é uma decisão
consciente do time, não algo que o teste faz sozinho.
"""
import json
from pathlib import Path

import pytest

from backend.src.agents.forms_a11y.forms_a11y import run_forms_a11y
from backend.src.agents.perceiver.perceiver import run_perceiver
from backend.src.agents.robustness.robustness import run_robustness
from backend.src.agents.screen_reader.screen_reader import run_screen_reader
from tests.backend.unit.test_prompt_regression import GOLDEN_CASES

pytestmark = pytest.mark.real_llm

_BASELINE_PATH = Path(__file__).parent / "baseline_snapshot.json"
_AGENT_BY_CASE_ID = {
    "GC001": run_perceiver,
    "GC002": run_robustness,
    "GC003": run_forms_a11y,
    "GC005": run_screen_reader,
}


@pytest.fixture(scope="module")
def baseline() -> dict:
    return json.loads(_BASELINE_PATH.read_text(encoding="utf-8"))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    [c for c in GOLDEN_CASES if c["id"] in _AGENT_BY_CASE_ID],
    ids=lambda c: c["id"],
)
async def test_no_regression_vs_recorded_baseline(case: dict, baseline: dict, alto_model_id: str) -> None:
    baseline_case = baseline["cases"].get(case["id"])
    assert baseline_case is not None, f"{case['id']} não está no baseline -- rode o script de captura primeiro"

    from tests.backend.real_llm.conftest import run_agent_with_retry

    agent_fn = _AGENT_BY_CASE_ID[case["id"]]
    result = await run_agent_with_retry(agent_fn, case["html"])
    assert result.success, f"[{case['id']}] agente falhou contra {alto_model_id}: {result.error}"

    issues_today = result.data.get("issues", [])
    baseline_had_issues = baseline_case["issue_count"] > 0

    if baseline_had_issues:
        assert issues_today, (
            f"[{case['id']}] REGRESSÃO: baseline detectava {baseline_case['issue_count']} "
            f"issue(s) ({baseline_case['criteria']}), execução real de hoje ({alto_model_id}) "
            f"não detectou nenhum. Modelo do baseline: {baseline['model']}."
        )


@pytest.mark.asyncio
async def test_baseline_model_matches_or_flags_drift(baseline: dict, alto_model_id: str) -> None:
    """Não falha o build -- só documenta quando o 'alto' resolvido mudou desde o baseline
    (dado que resolve_alto_model é dinâmico por design, isso é esperado e não é bug)."""
    if baseline["model"] != alto_model_id:
        pytest.skip(
            f"modelo alto mudou desde o baseline: {baseline['model']} -> {alto_model_id} "
            "(esperado com roteamento dinamico; considere recapturar o baseline)"
        )
