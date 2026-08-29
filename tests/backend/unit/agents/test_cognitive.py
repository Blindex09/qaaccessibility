import json
from unittest.mock import AsyncMock, patch

import pytest

from backend.src.agents.cognitive.cognitive import run_cognitive

from .conftest_agents import (
    HTML_CLEAN,
    assert_agent_contract,
    assert_issues_valid,
    make_issue,
)

HTML_WITH_COGNITIVE_ISSUES = """
<html>
  <body>
    <form>
      <label>Nome</label>
      <input type="text" required>
      <input type="text" id="cpf" placeholder="000.000.000-00">
      <img src="captcha.png" alt="Digite o texto da imagem">
      <button type="submit">Enviar</button>
    </form>
    <div class="carousel" data-autoplay="true" data-interval="3000">
      <div class="slide">Slide 1</div>
      <div class="slide">Slide 2</div>
    </div>
  </body>
</html>
""".strip()

COGNITIVE_ISSUE = make_issue(
    {
        "id": "cognitive-1",
        "guideline": "WCAG 2.2",
        "criterion": "3.3.8 Accessible Authentication (Minimum)",
        "severity": "critical",
        "element": "img[src='captcha.png']",
        "description": "CAPTCHA without accessible alternative blocks users with cognitive disabilities",
        "suggestion": "Provide an audio CAPTCHA alternative or remove CAPTCHA in favor of honeypot",
    }
)


@pytest.mark.asyncio
class TestCognitiveAgent:
    async def test_contract_on_success(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value=json.dumps([COGNITIVE_ISSUE])),
        ):
            result = await run_cognitive(HTML_WITH_COGNITIVE_ISSUES)
        assert_agent_contract(result, "cognitive")
        assert_issues_valid(result.data["issues"])

    async def test_cognitive_issue_has_cognitive_id_prefix(self):
        """Issues do cognitive devem ter id prefixado com cognitive-."""
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value=json.dumps([COGNITIVE_ISSUE])),
        ):
            result = await run_cognitive(HTML_WITH_COGNITIVE_ISSUES)
        for issue in result.data.get("issues", []):
            assert issue["id"].startswith("cognitive-"), f"ID deve começar com cognitive-: {issue['id']}"

    async def test_empty_html_returns_success(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value="[]"),
        ):
            result = await run_cognitive("")
        assert result.success is True
        assert result.data["issues"] == []

    async def test_clean_html_no_issues(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value="[]"),
        ):
            result = await run_cognitive(HTML_CLEAN)
        assert result.success is True
        assert len(result.data["issues"]) == 0

    async def test_failure_on_invalid_json(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value="not json"),
        ):
            result = await run_cognitive(HTML_WITH_COGNITIVE_ISSUES)
        assert result.success is False
        assert result.error is not None

    async def test_failure_on_llm_exception(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(side_effect=Exception("rate limit")),
        ):
            result = await run_cognitive(HTML_WITH_COGNITIVE_ISSUES)
        assert result.success is False
        assert "rate limit" in result.error
