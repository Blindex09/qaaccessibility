"""
Camada 6/9 -- Accessibility Evals (real).

Diferente de Agent Evals (camada 2, um agente x um golden case), esta camada
mede a qualidade de acessibilidade do PRODUTO como um todo: dado um HTML com
múltiplos issues conhecidos de guidelines diferentes, o pipeline restrito
(`only_agents`) precisa atingir um recall mínimo -- e, num HTML limpo, uma
taxa baixa de falso positivo (precisão). É a camada mais próxima do que um
auditor humano WCAG mediria: "quantos problemas reais o produto encontrou?".
"""
import pytest

from backend.src.agents.orchestrator.orchestrator import orchestrate
from backend.src.shared.models import AccessibilityIssue, TaskType

pytestmark = pytest.mark.real_llm

# Corpus com 4 issues conhecidos, cobrindo agentes/guidelines distintos --
# só os agentes relevantes são selecionados (only_agents) para controlar
# custo, mas a página tem múltiplos problemas simultâneos, como uma página
# real teria.
_MULTI_ISSUE_HTML = """
<html>
<body>
  <img src="hero.png">
  <button><svg></svg></button>
  <form><input type="text" name="email"></form>
  <a href="/pricing" style="color:#aaa">Saiba mais</a>
</body>
</html>
"""

_RELEVANT_AGENTS = ["perceiver", "robustness", "forms_a11y"]


@pytest.fixture(scope="module")
async def accessibility_eval_result():
    return await orchestrate(
        _MULTI_ISSUE_HTML, TaskType.ANALYZE, only_agents=_RELEVANT_AGENTS
    )


@pytest.mark.asyncio
async def test_accessibility_eval_pipeline_succeeds(accessibility_eval_result) -> None:
    assert accessibility_eval_result.success is True, accessibility_eval_result.error


@pytest.mark.asyncio
async def test_accessibility_eval_recall_meets_minimum_threshold(accessibility_eval_result) -> None:
    """Espera-se recall >= 50% (2 de 4 famílias de guideline) no mínimo -- limiar deliberadamente
    conservador: mede regressão grosseira de qualidade, não exige detecção perfeita de um LLM real."""
    issues = [AccessibilityIssue.model_validate(i) for i in accessibility_eval_result.data["issues"]]
    criteria_found = {i.criterion.split(" ")[0] for i in issues}

    expected_families = ["1.1.1", "4.1.2", "1.3", "2.4"]  # img alt, name/role/value, label, link text
    hits = [
        fam for fam in expected_families
        if any(c.startswith(fam) for c in criteria_found)
    ]
    recall = len(hits) / len(expected_families)

    assert recall >= 0.5, (
        f"recall real do produto ({accessibility_eval_result.data.get('agent_metrics')}) "
        f"= {recall:.0%}, abaixo do limiar mínimo. Criteria detectados: {criteria_found}"
    )


@pytest.mark.asyncio
async def test_accessibility_eval_clean_page_has_low_false_positive_rate() -> None:
    """Página 100% conforme -- precisão real: não deve gerar issues fantasmas."""
    # Achado real (2026-08-10): a fixture original tinha 3 imperfeições reais
    # que o produto (Ollama Cloud, via a API nativa do Ollama) apontou
    # corretamente ao longo de reruns -- não eram falsos positivos:
    # (1) lang="en" com todo conteúdo visível em português (mismatch WCAG 3.1.2);
    # (2) required + aria-required="true" juntos (redundante, ARIA in HTML);
    # (3) <button>Fechar</button> sem contexto do que fecha (WCAG 2.4.6).
    # A fixture "limpa" nunca foi de fato limpa -- corrigida para as 3.
    clean_html = (
        '<html lang="pt"><body>'
        '<img src="hero.png" alt="Time da empresa em reunião">'
        '<button aria-label="Fechar aviso de cookies">Fechar</button>'
        '<form><label for="email">E-mail</label>'
        '<input id="email" type="email" name="email" autocomplete="email" required>'
        "</form>"
        '<a href="/pricing">Ver planos e preços</a>'
        "</body></html>"
    )
    result = await orchestrate(clean_html, TaskType.ANALYZE, only_agents=_RELEVANT_AGENTS)

    assert result.success is True
    issues = result.data["issues"]
    assert len(issues) <= 1, (
        f"produto (Ollama Cloud real) gerou {len(issues)} issue(s) numa página limpa -- "
        f"taxa de falso positivo alta demais: {issues}"
    )
