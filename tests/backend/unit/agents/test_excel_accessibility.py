import json
from unittest.mock import AsyncMock, patch

import pytest

from backend.src.agents.excel_accessibility.excel_accessibility import run_excel_accessibility

from .conftest_agents import assert_agent_contract, assert_issues_valid, make_issue

XLSX_SUMMARY_NO_HEADER = """
Planilha com 1 aba(s): Sheet1
--- Aba 'Sheet1' ---
Dimensão: A1:B50 (50 linhas x 2 colunas)
Painel congelado: nenhum
Células mescladas: nenhuma
Linha 1 parece cabeçalho de texto: False (valores: [120, 'Jan'])
""".strip()

XLSX_ISSUE = make_issue(
    {
        "id": "excel-1",
        "guideline": "WCAG 2.2",
        "criterion": "1.3.1 Info and Relationships",
        "severity": "high",
        "element": "Sheet1, linha 1",
        "description": "planilha sem cabeçalho fixo",
        "suggestion": "Congelar a linha 1 como cabeçalho",
    }
)


@pytest.mark.asyncio
class TestExcelAccessibilityAgent:
    async def test_contract_on_success(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value=json.dumps([XLSX_ISSUE])),
        ):
            result = await run_excel_accessibility(XLSX_SUMMARY_NO_HEADER)
        assert_agent_contract(result, "excel_accessibility")
        assert_issues_valid(result.data["issues"])

    async def test_excel_issue_has_excel_id_prefix(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value=json.dumps([XLSX_ISSUE])),
        ):
            result = await run_excel_accessibility(XLSX_SUMMARY_NO_HEADER)
        for issue in result.data.get("issues", []):
            assert issue["id"].startswith("excel-"), f"ID deve começar com excel-: {issue['id']}"

    async def test_empty_summary_returns_success(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value="[]"),
        ):
            result = await run_excel_accessibility("")
        assert result.success is True
        assert result.data["issues"] == []

    async def test_failure_on_invalid_json(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(return_value="not json"),
        ):
            result = await run_excel_accessibility(XLSX_SUMMARY_NO_HEADER)
        assert result.success is False
        assert result.error is not None

    async def test_failure_on_llm_exception(self):
        with patch(
            "backend.src.services.llm_client.call_llm",
            new=AsyncMock(side_effect=Exception("LLM timeout")),
        ):
            result = await run_excel_accessibility(XLSX_SUMMARY_NO_HEADER)
        assert result.success is False
        assert "LLM timeout" in result.error
