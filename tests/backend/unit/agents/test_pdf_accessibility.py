import json
from unittest.mock import AsyncMock, patch

import pytest

from backend.src.agents.pdf_accessibility.pdf_accessibility import run_pdf_accessibility

from .conftest_agents import assert_agent_contract, assert_issues_valid, make_issue

PDF_SUMMARY_UNTAGGED = """
Documento PDF, 12 páginas. Tag tree: AUSENTE (documento não taggeado).
Idioma do documento: não definido. Título nos metadados: ausente.
Página 3: imagem sem texto alternativo.
""".strip()

PDF_ISSUE = make_issue(
    {
        "id": "pdf-1",
        "guideline": "WCAG 2.2",
        "criterion": "1.3.1 Info and Relationships",
        "severity": "critical",
        "element": "document (no tag tree)",
        "description": "PDF sem tags de acessibilidade",
        "suggestion": "Adicionar tags reais ao PDF",
    }
)


@pytest.mark.asyncio
class TestPdfAccessibilityAgent:
    async def test_contract_on_success(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value=json.dumps([PDF_ISSUE])),
        ):
            result = await run_pdf_accessibility(PDF_SUMMARY_UNTAGGED)
        assert_agent_contract(result, "pdf_accessibility")
        assert_issues_valid(result.data["issues"])

    async def test_pdf_issue_has_pdf_id_prefix(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value=json.dumps([PDF_ISSUE])),
        ):
            result = await run_pdf_accessibility(PDF_SUMMARY_UNTAGGED)
        for issue in result.data.get("issues", []):
            assert issue["id"].startswith("pdf-"), f"ID deve começar com pdf-: {issue['id']}"

    async def test_empty_summary_returns_success(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value="[]"),
        ):
            result = await run_pdf_accessibility("")
        assert result.success is True
        assert result.data["issues"] == []

    async def test_failure_on_invalid_json(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value="not json"),
        ):
            result = await run_pdf_accessibility(PDF_SUMMARY_UNTAGGED)
        assert result.success is False
        assert result.error is not None

    async def test_failure_on_llm_exception(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(side_effect=Exception("LLM timeout")),
        ):
            result = await run_pdf_accessibility(PDF_SUMMARY_UNTAGGED)
        assert result.success is False
        assert "LLM timeout" in result.error
