"""
Camada 3/9 -- Trajectory Evals (real).

Enquanto Agent Evals (camada 2) avalia UM agente isolado, esta camada avalia
a TRAJETÓRIA do orquestrador multi-agente: quais sub-agentes foram
selecionados (roteamento condicional por evidência estrutural do HTML, ver
`_conditional_agent_reasons`), se todos completaram com sucesso contra o
provider real, e se o passo final de deduplicação produziu um resultado
coerente -- sem depender de mockar cada sub-agente.

Escopo de custo: 1 único `orchestrate()` real (a chamada mais cara da suite,
~15-20 sub-chamadas de LLM em paralelo) é compartilhado por todos os testes
deste módulo via fixture de módulo.
"""
import pytest

from backend.src.agents.orchestrator.orchestrator import orchestrate
from backend.src.shared.models import AccessibilityIssue, AgentResult, TaskType

pytestmark = pytest.mark.real_llm

# HTML com superfície de formulário (aciona forms_a11y) e CSS embutido (aciona
# css_analyzer), mas sem JS/ARIA-live, mobile ou widgets -- mantém a
# trajetória previsível e o custo/tempo do run real controlado.
_HTML_MIXED_SURFACE = """
<html lang="en">
<head><style>.btn { outline: none; color: #999; }</style></head>
<body>
  <form>
    <input type="text" name="email">
    <button class="btn" type="submit">Enviar</button>
  </form>
  <img src="banner.png">
</body>
</html>
"""


@pytest.fixture(scope="module")
async def real_orchestrate_result() -> AgentResult:
    return await orchestrate(_HTML_MIXED_SURFACE, TaskType.ANALYZE)


@pytest.mark.asyncio
async def test_trajectory_completes_successfully(real_orchestrate_result: AgentResult) -> None:
    assert real_orchestrate_result.success is True, real_orchestrate_result.error
    assert real_orchestrate_result.agent == "orchestrator"


@pytest.mark.asyncio
async def test_trajectory_ran_core_agents(real_orchestrate_result: AgentResult) -> None:
    """Core agents rodam sempre, independente de conteúdo -- trajetória base."""
    metrics = real_orchestrate_result.data["agent_metrics"]
    ran_agents = {m["agent"] for m in metrics}

    core_expected = {"perceiver", "operability", "understandability", "robustness"}
    missing = core_expected - ran_agents
    assert not missing, f"agentes core ausentes da trajetória real: {missing} (rodaram: {ran_agents})"


@pytest.mark.asyncio
async def test_trajectory_triggered_conditional_agents_by_structure(
    real_orchestrate_result: AgentResult,
) -> None:
    """forms_a11y e css_analyzer devem ter sido roteados: o HTML tem <form>/<input> e <style>."""
    metrics = real_orchestrate_result.data["agent_metrics"]
    ran_agents = {m["agent"] for m in metrics}

    assert "forms_a11y" in ran_agents, "trajetória não roteou forms_a11y apesar de <form>/<input> no HTML"
    assert "css_analyzer" in ran_agents, "trajetória não roteou css_analyzer apesar de <style> no HTML"


@pytest.mark.asyncio
async def test_trajectory_no_agent_hangs_or_fails_silently(real_orchestrate_result: AgentResult) -> None:
    """Cada passo da trajetória reporta sucesso/falha explícito -- sem estado indefinido."""
    metrics = real_orchestrate_result.data["agent_metrics"]
    assert len(metrics) >= 4, f"trajetória suspeita: só {len(metrics)} agentes reportaram métricas"
    for m in metrics:
        assert isinstance(m["success"], bool)
        assert m["duration_ms"] >= 0


@pytest.mark.asyncio
async def test_trajectory_final_state_deduplicates_issues(real_orchestrate_result: AgentResult) -> None:
    """Passo final (Observe do ReAct) não deve deixar o mesmo (criterion, element) duplicado."""
    issues = [AccessibilityIssue.model_validate(i) for i in real_orchestrate_result.data["issues"]]
    seen = set()
    duplicates = []
    for issue in issues:
        key = (issue.criterion, issue.element)
        if key in seen:
            duplicates.append(key)
        seen.add(key)

    assert not duplicates, f"trajetória real deixou issues duplicados após dedup: {duplicates}"
