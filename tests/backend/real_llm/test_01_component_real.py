"""
Camada 1/9 -- Component Tests (real).

Chama um único agente isoladamente (sem orquestração) contra o Ollama Cloud
real, tier alto, e valida que o output respeita o contrato Pydantic
(AgentResult -> data["issues"] -> AccessibilityIssue) com dados de verdade,
não um mock. Isola falhas de "esse agente específico quebrou o schema" de
falhas de integração mais amplas (ver camadas 3/4).
"""
import pytest

from backend.src.agents.perceiver.perceiver import run_perceiver
from backend.src.agents.robustness.robustness import run_robustness
from backend.src.shared.models import AccessibilityIssue

pytestmark = pytest.mark.real_llm


@pytest.mark.asyncio
async def test_perceiver_real_call_returns_valid_schema(alto_model_id: str) -> None:
    html = '<html><body><img src="logo.png"></body></html>'

    result = await run_perceiver(html)

    assert result.success is True, f"perceiver falhou contra {alto_model_id}: {result.error}"
    assert result.agent == "perceiver"
    assert "issues" in result.data
    issues = [AccessibilityIssue.model_validate(i) for i in result.data["issues"]]
    assert len(issues) >= 1, "perceiver não detectou o img sem alt (real LLM call)"


@pytest.mark.asyncio
async def test_robustness_real_call_returns_valid_schema(alto_model_id: str) -> None:
    html = '<html><body><div onclick="submit()">Enviar</div></body></html>'

    result = await run_robustness(html)

    assert result.success is True, f"robustness falhou contra {alto_model_id}: {result.error}"
    issues = [AccessibilityIssue.model_validate(i) for i in result.data["issues"]]
    # Contrato: mesmo se o modelo real discordar do severity exato, o schema
    # tem que validar -- é isso que este componente testa.
    for issue in issues:
        assert issue.criterion
        assert issue.description
        assert issue.suggestion


@pytest.mark.asyncio
async def test_perceiver_clean_html_does_not_hallucinate_issues(alto_model_id: str) -> None:
    """HTML 100% acessível -- o componente não deve inventar issues (falso positivo)."""
    html = (
        '<html lang="en"><body>'
        '<img src="logo.png" alt="Acme Corporation">'
        "</body></html>"
    )

    result = await run_perceiver(html)

    assert result.success is True
    issues = result.data.get("issues", [])
    assert len(issues) == 0, (
        f"perceiver ({alto_model_id}) alucinou {len(issues)} issue(s) em HTML limpo: {issues}"
    )
