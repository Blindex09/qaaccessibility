import json
from unittest.mock import AsyncMock, patch

import pytest

from backend.src.agents.forms_a11y.forms_a11y import run_forms_a11y

from .conftest_agents import (
    HTML_CLEAN,
    assert_agent_contract,
    assert_issues_valid,
    make_issue,
)

HTML_WITH_FORMS_ISSUES = """
<html>
  <body>
    <form>
      <input type="text" placeholder="Nome completo">
      <input type="email" placeholder="seu@email.com">
      <input type="text" id="phone" placeholder="Telefone" required>
      <div class="radio-group">
        <input type="radio" name="gender" value="m"> Masculino
        <input type="radio" name="gender" value="f"> Feminino
      </div>
      <input type="text" id="cpf" class="invalid" value="123">
      <span class="error">CPF inválido</span>
      <button type="submit">Enviar</button>
    </form>
  </body>
</html>
""".strip()

FORMS_ISSUE = make_issue(
    {
        "id": "forms-1",
        "guideline": "WCAG 2.2",
        "criterion": "1.3.1 Info and Relationships",
        "severity": "critical",
        "element": "input[type=text][placeholder='Nome completo']",
        "description": "placeholder used as sole label, disappears on input",
        "suggestion": "Add a <label for='name'>Nome completo</label> element",
    }
)


@pytest.mark.asyncio
class TestFormsA11yAgent:
    async def test_code_does_not_judge_findings_by_keyword(self):
        """Regra 2: o codigo nao descarta achado do modelo lendo palavras da descricao (isso e julgamento).

        O que o HTML estatico nao prova (botao de envio ausente, marcador visual de obrigatorio quando ja ha
        required) e dito ao modelo no prompt; quem julga o achado e a IA, e o revisor. O harness so repassa.
        """
        from backend.src.shared.models import AccessibilityIssue

        findings = [
            AccessibilityIssue.model_validate(
                make_issue({"id": "forms-submit", "criterion": "3.3.2 Labels or Instructions", "description": "The form has no submit button."})
            ),
        ]
        with patch("backend.src.agents.forms_a11y.forms_a11y.call_llm_structured", new=AsyncMock(return_value=findings)):
            result = await run_forms_a11y('<form><input id="e" required></form>')

        assert result.success is True
        assert [i["id"] for i in result.data["issues"]] == ["forms-submit"]

    def test_prompt_tells_the_model_what_static_html_cannot_prove(self):
        from backend.src.agents.forms_a11y.forms_a11y import SYSTEM_PROMPT

        assert "Do NOT report a missing submit button from static HTML alone" in SYSTEM_PROMPT
        assert "Do NOT report a missing visual required marker" in SYSTEM_PROMPT

    async def test_contract_on_success(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value=json.dumps([FORMS_ISSUE])),
        ):
            result = await run_forms_a11y(HTML_WITH_FORMS_ISSUES)
        assert_agent_contract(result, "forms_a11y")
        assert_issues_valid(result.data["issues"])

    async def test_forms_issue_has_forms_id_prefix(self):
        """Issues do forms_a11y devem ter id prefixado com forms-."""
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value=json.dumps([FORMS_ISSUE])),
        ):
            result = await run_forms_a11y(HTML_WITH_FORMS_ISSUES)
        for issue in result.data.get("issues", []):
            assert issue["id"].startswith("forms-"), f"ID deve começar com forms-: {issue['id']}"

    async def test_empty_html_returns_success(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value="[]"),
        ):
            result = await run_forms_a11y("")
        assert result.success is True
        assert result.data["issues"] == []

    async def test_clean_html_no_issues(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value="[]"),
        ):
            result = await run_forms_a11y(HTML_CLEAN)
        assert result.success is True
        assert len(result.data["issues"]) == 0

    async def test_failure_on_invalid_json(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value="not json"),
        ):
            result = await run_forms_a11y(HTML_WITH_FORMS_ISSUES)
        assert result.success is False
        assert result.error is not None

    async def test_failure_on_llm_exception(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(side_effect=Exception("LLM timeout")),
        ):
            result = await run_forms_a11y(HTML_WITH_FORMS_ISSUES)
        assert result.success is False
        assert "LLM timeout" in result.error
