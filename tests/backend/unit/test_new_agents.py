import pytest

from backend.src.agents.agentic_ai_ui.agentic_ai_ui import run_agentic_ai_ui_agent
from backend.src.agents.niche_domains.niche_domains import run_niche_domains_agent
from backend.src.agents.spatial_3d_xr.spatial_3d_xr import run_spatial_3d_xr_agent
from backend.src.agents.web_components.web_components import run_web_components_agent
from backend.src.services.sarif_exporter import export_to_sarif
from backend.src.shared.models import AccessibilityIssue


@pytest.mark.asyncio
async def test_agentic_ai_ui_agent_structure():
    """Testa se o AgenticAIUIAgent lida graciosamente com HTML sem erros."""
    html_sample = "<div role='region' aria-label='Chat'><div role='log' aria-busy='true'>Streaming...</div></div>"
    result = await run_agentic_ai_ui_agent(html_sample)
    assert result.agent == "agentic_ai_ui"
    assert isinstance(result.data, dict)


@pytest.mark.asyncio
async def test_spatial_3d_xr_agent_structure():
    """Testa se o Spatial3D_XR_Agent lida graciosamente com HTML sem erros."""
    html_sample = "<canvas id='webgl-scene'></canvas>"
    result = await run_spatial_3d_xr_agent(html_sample)
    assert result.agent == "spatial_3d_xr"
    assert isinstance(result.data, dict)


@pytest.mark.asyncio
async def test_web_components_agent_structure():
    """Testa se o WebComponentsAgent lida graciosamente com HTML sem erros."""
    html_sample = "<custom-input></custom-input>"
    result = await run_web_components_agent(html_sample)
    assert result.agent == "web_components"
    assert isinstance(result.data, dict)


@pytest.mark.asyncio
async def test_niche_domains_agent_structure():
    """Testa se o NicheDomainsAgent lida graciosamente com HTML sem erros."""
    html_sample = "<form><input type='password' onpaste='return false;'></form>"
    result = await run_niche_domains_agent(html_sample)
    assert result.agent == "niche_domains"
    assert isinstance(result.data, dict)


def test_sarif_exporter():
    """Testa a geracao de relatorios no padrao SARIF 2.1.0."""
    sample_issue = AccessibilityIssue(
        id="aria-1",
        guideline="WAI-ARIA",
        criterion="4.1.2 Name, Role, Value",
        severity="high",
        level="A",
        element="<button>",
        description="Missing accessible name",
        description_technical="Button lacks inner text or aria-label",
        why_simple="Screen reader users cannot identify the button",
        why_technical="Violates WCAG 4.1.2",
        suggestion="Add an aria-label to the button",
        suggestion_technical='<button aria-label="Submit"></button>',
    )
    sarif = export_to_sarif([sample_issue], "http://example.com/test")

    assert sarif["version"] == "2.1.0"
    assert len(sarif["runs"]) == 1
    assert len(sarif["runs"][0]["results"]) == 1
    result = sarif["runs"][0]["results"][0]
    assert result["ruleId"] == "aria-1"
    assert result["level"] == "error"
