"""
Camada 10 -- Planning Eval (real, NOVA).

Valida `self_healing.node_plan` contra o Ollama Cloud real: dado um conjunto
de issues reais, o modelo decide ordem/agrupamento de correção -- nunca uma
lista de prioridade fixa. Fecha o gap "Planning: parcial" identificado na
auditoria de vocabulário 2026 (agentes eram todos single-shot reativos, sem
nenhum passo de planejamento explícito antes de agir).
"""
import pytest

from backend.src.services.self_healing import _plan_to_instruction, node_plan
from backend.src.shared.models import AccessibilityIssue, Guideline, Severity

pytestmark = pytest.mark.real_llm


def _issue(id_: str, criterion: str, element: str, severity: Severity = Severity.HIGH) -> AccessibilityIssue:
    return AccessibilityIssue(
        id=id_,
        guideline=Guideline.WCAG_2_2,
        criterion=criterion,
        severity=severity,
        element=element,
        description=f"Violation of {criterion}",
        suggestion="Fix it",
    )


@pytest.mark.asyncio
async def test_planner_produces_a_real_ordered_plan(alto_model_id: str) -> None:
    """3 issues reais, um dos quais (heading skip) tipicamente cascade sobre
    outro (landmark) -- o plano real deve agrupar/ordenar de forma coerente,
    não devolver silenciosamente um plano vazio."""
    issues = [
        _issue("i-1", "1.3.1 Info and Relationships", "<h3>Section</h3> (skip from h1)", Severity.MEDIUM),
        _issue("i-2", "2.4.1 Bypass Blocks", "<body> (no landmark regions)", Severity.MEDIUM),
        _issue("i-3", "1.1.1 Non-text Content", '<img src="hero.png">', Severity.CRITICAL),
    ]

    plan = await node_plan(issues)

    assert plan.get("strategy"), f"planner real ({alto_model_id}) devolveu plano vazio para issues reais"
    assert plan.get("ordered_groups"), "planner real não agrupou nenhum issue"

    all_planned_ids = {i for group in plan["ordered_groups"] for i in group.get("issue_ids", [])}
    assert all_planned_ids, "nenhum issue_id real apareceu no plano"
    # Pelo menos os IDs reais devem aparecer -- não IDs inventados.
    assert all_planned_ids.issubset({"i-1", "i-2", "i-3"}), (
        f"planner alucinou issue_ids que não existem: {all_planned_ids - {'i-1', 'i-2', 'i-3'}}"
    )


@pytest.mark.asyncio
async def test_planner_output_converts_to_usable_fixer_instruction(alto_model_id: str) -> None:
    issues = [
        _issue("i-1", "4.1.2 Name, Role, Value", "<button><svg></svg></button>"),
        _issue("i-2", "1.1.1 Non-text Content", '<img src="logo.png">'),
    ]

    plan = await node_plan(issues)
    instruction = _plan_to_instruction(plan)

    assert instruction, f"plano real ({alto_model_id}) não gerou instrução utilizável para o fixer"
    assert "i-1" in instruction or "i-2" in instruction


@pytest.mark.asyncio
async def test_planner_does_not_invent_a_fixed_priority_regardless_of_input() -> None:
    """Regressão contra 'plano fixo disfarçado': duas listas de issues bem
    diferentes devem gerar estratégias diferentes -- se o texto vier idêntico
    nas duas vezes, o "planejamento" na prática seria só um template estático."""
    issues_a = [_issue("a-1", "1.1.1 Non-text Content", "<img>")]
    issues_b = [
        _issue("b-1", "2.1.1 Keyboard", "<div onclick='x()'>"),
        _issue("b-2", "4.1.2 Name, Role, Value", "<div role='button'>"),
        _issue("b-3", "1.4.3 Contrast Minimum", "<p style='color:#ccc'>"),
    ]

    plan_a = await node_plan(issues_a)
    plan_b = await node_plan(issues_b)

    assert plan_a.get("strategy") != plan_b.get("strategy"), (
        "planner real devolveu a MESMA estratégia para dois conjuntos de issues "
        "completamente diferentes -- indício de prompt não sendo lido de verdade"
    )
