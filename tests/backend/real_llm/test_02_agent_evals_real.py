"""
Camada 2/9 -- Agent Evals (real).

Reusa o golden dataset de tests/backend/unit/test_prompt_regression.py (fonte
única -- "zero duplicação" do README) mas roda contra o Ollama Cloud real em
vez de mockar a resposta do LLM. Mede taxa de detecção (recall) por golden
case: o agente correto precisa sinalizar o criterion WCAG esperado.

Diferença para Component Tests (camada 1): aqui o critério de sucesso é
comportamental (detectou o issue certo?), não estrutural (o schema é válido?).
"""
import pytest

from backend.src.agents.forms_a11y.forms_a11y import run_forms_a11y
from backend.src.agents.perceiver.perceiver import run_perceiver
from backend.src.agents.robustness.robustness import run_robustness
from backend.src.agents.screen_reader.screen_reader import run_screen_reader
from backend.src.shared.models import AccessibilityIssue
from tests.backend.unit.test_prompt_regression import GOLDEN_CASES

pytestmark = pytest.mark.real_llm

# Roteamento por especialidade real do agente (ver README "Estrutura do
# projeto"), não pelo prefixo numérico bruto do criterion -- 1.3.1 (labels)
# é forms_a11y, 4.1.2 (nome acessível) é robustness, heading skip é
# screen_reader, mesmo os três estando "dentro" da faixa WCAG 1.x/4.x.
_AGENT_BY_CASE_ID = {
    "GC001": run_perceiver,       # img sem alt -- 1.1.1, perceptível puro
    "GC002": run_robustness,      # button sem nome acessível -- 4.1.2 name/role/value
    "GC003": run_forms_a11y,      # input sem label -- especialidade de formulários
    "GC004": run_perceiver,       # link só com img sem alt -- 2.4.4, mas também 1.1.1
    "GC005": run_screen_reader,   # heading skip h1->h3 -- ordem de headings
}

# Família de guideline aceitável por case: modelos reais fortes às vezes
# escolhem um criterion irmão igualmente válido dentro da mesma família
# (ex.: 1.3.5 em vez de 1.3.1 para um input sem label nem autocomplete) --
# uma suite real precisa tolerar isso; string matching exato é bom para
# mocks determinísticos, não para julgar um LLM de verdade.
_ACCEPTABLE_FAMILY = {
    "GC001": ["1.1.1"],
    "GC002": ["4.1.2"],
    "GC003": ["1.3.1", "1.3.5", "3.3.2", "4.1.2"],
    "GC004": ["2.4.4", "1.1.1", "2.4.9"],
    "GC005": ["1.3.1", "2.4.6", "2.4.10"],
}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    [c for c in GOLDEN_CASES if c["id"] in _AGENT_BY_CASE_ID],
    ids=lambda c: c["id"],
)
async def test_golden_case_detected_by_real_agent(case: dict, alto_model_id: str) -> None:
    from tests.backend.real_llm.conftest import run_agent_with_retry

    agent_fn = _AGENT_BY_CASE_ID[case["id"]]
    result = await run_agent_with_retry(agent_fn, case["html"])

    assert result.success, f"[{case['id']}] agente falhou contra {alto_model_id}: {result.error}"
    issues = [AccessibilityIssue.model_validate(i) for i in result.data.get("issues", [])]

    acceptable = _ACCEPTABLE_FAMILY[case["id"]]
    matched = [i for i in issues if any(a in i.criterion for a in acceptable)]

    assert matched, (
        f"[{case['id']}] '{case['description']}': modelo real ({alto_model_id}) não "
        f"detectou nenhum criterion aceitável {acceptable}. "
        f"Issues retornados: {[i.criterion for i in issues]}"
    )
