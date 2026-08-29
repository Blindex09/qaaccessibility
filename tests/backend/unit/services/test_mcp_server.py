"""Testes do servidor MCP (FastMCP) — QA-Accessibility-Tools.

Cobrem as 6 ferramentas expostas via stdio, validando contratos e
tratamento de erro, sem acionar rede real (Playwright/orchestrator mockados).
"""

import json
from unittest.mock import AsyncMock, patch

import pytest

from backend.src.services import mcp_server


# --------------------------------------------------------------------------- #
# get_rendered_page
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_get_rendered_page_returns_html_on_success():
    expected_html = "<html><body>rendered</body></html>"
    with patch(
        "backend.src.services.mcp_server.fetch_rendered_html_screenshot_and_focus_states",
        new=AsyncMock(return_value=(expected_html, None, None)),
    ):
        result = await mcp_server.get_rendered_page("https://example.com")
    assert result == expected_html


@pytest.mark.asyncio
async def test_get_rendered_page_returns_error_message_on_failure():
    with patch(
        "backend.src.services.mcp_server.fetch_rendered_html_screenshot_and_focus_states",
        new=AsyncMock(side_effect=RuntimeError("boom")),
    ):
        result = await mcp_server.get_rendered_page("https://example.com")
    assert "Erro ao carregar" in result
    assert "boom" in result


# --------------------------------------------------------------------------- #
# run_axe_audit
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_run_axe_audit_returns_json_array_on_success():
    from backend.src.shared.models import AccessibilityIssue, Guideline, Severity

    issues = [
        AccessibilityIssue(
            id="a1",
            guideline=Guideline.WCAG_2_2,
            criterion="1.1.1 Non-text Content",
            severity=Severity.CRITICAL,
            element="img",
            description="sem alt",
            suggestion="add alt",
        )
    ]
    with patch(
        "backend.src.services.mcp_server.verify_html_with_axe",
        new=AsyncMock(return_value=issues),
    ):
        result = await mcp_server.run_axe_audit("<html></html>")
    parsed = json.loads(result)
    assert isinstance(parsed, list)
    assert parsed[0]["id"] == "a1"


@pytest.mark.asyncio
async def test_run_axe_audit_returns_error_message_on_failure():
    with patch(
        "backend.src.services.mcp_server.verify_html_with_axe",
        new=AsyncMock(side_effect=RuntimeError("axe fail")),
    ):
        result = await mcp_server.run_axe_audit("<html></html>")
    assert "Erro ao executar a auditoria Axe" in result
    assert "axe fail" in result


# --------------------------------------------------------------------------- #
# export_xlsx
# --------------------------------------------------------------------------- #
def test_export_xlsx_returns_base64_on_success():
    issues = [
        {
            "id": "i1",
            "criterion": "1.4.3 Contrast Minimum",
            "severity": "critical",
            "element": "p",
            "description": "baixo contraste",
            "suggestion": "escurecer",
        }
    ]
    with patch("backend.src.services.mcp_server.export_issues_xlsx") as mock_export:
        mock_export.return_value = b"\x50\x4b\x05\x06"  # assinatura ZIP/xlsx
        result = mcp_server.export_xlsx(json.dumps(issues))
    assert isinstance(result, str)
    # base64 decodifica de volta para os bytes origais
    import base64

    assert base64.b64decode(result) == b"\x50\x4b\x05\x06"


def test_export_xlsx_returns_error_message_on_invalid_json():
    result = mcp_server.export_xlsx("not-json")
    assert "Erro ao exportar planilha XLSX" in result


# --------------------------------------------------------------------------- #
# analyze_page_full
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_analyze_page_full_requires_url_or_html():
    result = await mcp_server.analyze_page_full(url="", html="")
    parsed = json.loads(result)
    assert "error" in parsed


@pytest.mark.asyncio
async def test_analyze_page_full_with_html_returns_score_and_issues():
    from backend.src.shared.models import AgentResult

    fake_result = AgentResult(
        agent="orchestrator",
        success=True,
        data={
            "issues": [
                {"severity": "critical", "criterion": "1.1.1", "element": "img"},
                {"severity": "high", "criterion": "2.4.4", "element": "a"},
            ]
        },
    )
    with patch(
        "backend.src.services.mcp_server.fetch_rendered_html_screenshot_and_focus_states",
        new=AsyncMock(),
    ), patch(
        "backend.src.agents.orchestrator.orchestrator.orchestrate",
        new=AsyncMock(return_value=fake_result),
    ), patch(
        "backend.src.routes.analyze._extract_semantic_html",
        return_value="<html>semantic</html>",
    ):
        result = await mcp_server.analyze_page_full(url="", html="<html></html>")
    parsed = json.loads(result)
    assert parsed["total_issues"] == 2
    assert parsed["issues_by_severity"]["critical"] == 1
    assert parsed["issues_by_severity"]["high"] == 1
    # 100 - (20*1 + 10*1) = 70
    assert parsed["score"] == 70


@pytest.mark.asyncio
async def test_analyze_page_full_fetches_html_when_only_url_given():
    from backend.src.shared.models import AgentResult

    fake_result = AgentResult(agent="orchestrator", success=True, data={"issues": []})
    mock_fetch = AsyncMock(return_value=("<html>fetched</html>", None, None))
    with patch(
        "backend.src.services.mcp_server.fetch_rendered_html_screenshot_and_focus_states",
        new=mock_fetch,
    ), patch(
        "backend.src.agents.orchestrator.orchestrator.orchestrate",
        new=AsyncMock(return_value=fake_result),
    ), patch(
        "backend.src.routes.analyze._extract_semantic_html",
        return_value="<html>fetched</html>",
    ):
        result = await mcp_server.analyze_page_full(url="https://example.com", html="")
    parsed = json.loads(result)
    assert parsed["url"] == "https://example.com"
    mock_fetch.assert_awaited_once_with("https://example.com")


@pytest.mark.asyncio
async def test_analyze_page_full_reports_error_on_unexpected_exception():
    with patch(
        "backend.src.routes.analyze._extract_semantic_html",
        side_effect=RuntimeError("parser exploded"),
    ):
        result = await mcp_server.analyze_page_full(url="", html="<html></html>")
    parsed = json.loads(result)
    assert "error" in parsed
    assert "parser exploded" in parsed["error"]


@pytest.mark.asyncio
async def test_analyze_page_full_reports_error_when_orchestrator_fails():
    from backend.src.shared.models import AgentResult

    fake_result = AgentResult(
        agent="orchestrator",
        success=False,
        data={},
        error="pipeline down",
    )
    with patch(
        "backend.src.agents.orchestrator.orchestrator.orchestrate",
        new=AsyncMock(return_value=fake_result),
    ), patch(
        "backend.src.routes.analyze._extract_semantic_html",
        return_value="<html></html>",
    ):
        result = await mcp_server.analyze_page_full(url="", html="<html></html>")
    parsed = json.loads(result)
    assert parsed["error"] == "pipeline down"


# --------------------------------------------------------------------------- #
# analyze_site_full
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_analyze_site_full_returns_result_on_success():
    fake = {"pages_audited": 3, "aggregate_score": 80, "total_issues": 5}
    with patch(
        "backend.src.services.chat_tools._run_site_crawl_and_analyze",
        new=AsyncMock(return_value=fake),
    ):
        result = await mcp_server.analyze_site_full("https://example.com", max_pages=20)
    parsed = json.loads(result)
    assert parsed["pages_audited"] == 3
    assert parsed["total_issues"] == 5


@pytest.mark.asyncio
async def test_analyze_site_full_clamps_max_pages_and_reports_error_on_failure():
    with patch(
        "backend.src.services.chat_tools._run_site_crawl_and_analyze",
        new=AsyncMock(side_effect=RuntimeError("crawl fail")),
    ):
        result = await mcp_server.analyze_site_full("https://example.com", max_pages=999)
    parsed = json.loads(result)
    assert "error" in parsed
    assert "crawl fail" in parsed["error"]


# --------------------------------------------------------------------------- #
# describe_repository (Repository Intelligence)
# --------------------------------------------------------------------------- #
def test_describe_repository_returns_valid_repo_map_json():
    result = mcp_server.describe_repository()
    parsed = json.loads(result)
    assert "agents" in parsed
    assert len(parsed["agents"]) > 0
    assert all("entry_points" in a for a in parsed["agents"])


def test_describe_repository_returns_error_json_when_file_missing():
    with patch("backend.src.services.mcp_server.Path.read_text", side_effect=OSError("no such file")):
        result = mcp_server.describe_repository()
    parsed = json.loads(result)
    assert "error" in parsed


# --------------------------------------------------------------------------- #
# Registro das tools no FastMCP
# --------------------------------------------------------------------------- #
def test_mcp_server_registers_six_tools():
    # O decorator @mcp.tool() registra cada função no servidor FastMCP.
    # Validamos que as 6 ferramentas esperadas estão presentes no catálogo.
    tool_names = set(mcp_server.mcp._tool_manager._tools.keys())  # type: ignore[attr-defined]
    expected = {
        "get_rendered_page",
        "run_axe_audit",
        "export_xlsx",
        "analyze_page_full",
        "analyze_site_full",
        "describe_repository",
    }
    assert expected.issubset(tool_names)
