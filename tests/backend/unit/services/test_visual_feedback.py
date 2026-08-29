from unittest.mock import AsyncMock, patch

import pytest

from backend.src.services.chat_tools import _run_fixes_and_generate_zip


@pytest.mark.asyncio
@patch("backend.src.services.chat_tools._render_html_to_screenshot")
@patch("backend.src.services.chat_tools._verify_layout_visually")
@patch("backend.src.agents.fixer.fixer.run_fixer")
@patch("backend.src.agents.orchestrator.orchestrator.orchestrate")
async def test_visual_feedback_loop_success(
    mock_orchestrate,
    mock_run_fixer,
    mock_verify_layout,
    mock_render_screenshot
):
    # Setup mocks
    mock_orchestrate.return_value = AsyncMock()
    mock_orchestrate.return_value.success = True
    mock_orchestrate.return_value.data = {
        "issues": [{
            "id": "1",
            "guideline": "WCAG 2.2",
            "criterion": "1.1.1 Non-text Content",
            "severity": "critical",
            "element": "img",
            "description": "Missing alt text",
            "suggestion": "Add alt text"
        }]
    }

    first_fix_res = AsyncMock()
    first_fix_res.data = {"fixed_html": "<html><body>Fixed Content</body></html>", "changes_summary": ["Fixed img alt"]}
    mock_run_fixer.return_value = first_fix_res

    mock_render_screenshot.return_value = "fake_base64_string"
    mock_verify_layout.return_value = {"layout_ok": True, "reasons": []}

    files = [{"path": "index.html", "content": "<html><body><img src='x.png'></body></html>"}]
    res = await _run_fixes_and_generate_zip(files, None)

    assert "changes_summary" in res
    assert any("Fixed img alt" in s for s in res["changes_summary"])
    assert mock_run_fixer.call_count == 1
    assert mock_verify_layout.call_count == 1


@pytest.mark.asyncio
@patch("backend.src.services.chat_tools._render_html_to_screenshot")
@patch("backend.src.services.chat_tools._verify_layout_visually")
@patch("backend.src.agents.fixer.fixer.run_fixer")
@patch("backend.src.agents.orchestrator.orchestrator.orchestrate")
async def test_visual_feedback_loop_retry(
    mock_orchestrate,
    mock_run_fixer,
    mock_verify_layout,
    mock_render_screenshot
):
    # Setup mocks
    mock_orchestrate.return_value = AsyncMock()
    mock_orchestrate.return_value.success = True
    mock_orchestrate.return_value.data = {
        "issues": [{
            "id": "1",
            "guideline": "WCAG 2.2",
            "criterion": "1.1.1 Non-text Content",
            "severity": "critical",
            "element": "img",
            "description": "Missing alt text",
            "suggestion": "Add alt text"
        }]
    }

    first_fix_res = AsyncMock()
    first_fix_res.data = {"fixed_html": "<html><body>Broken Layout</body></html>", "changes_summary": ["Fixed img alt"]}

    second_fix_res = AsyncMock()
    second_fix_res.data = {"fixed_html": "<html><body>Corrected Layout</body></html>", "changes_summary": ["Corrected visual alignment"]}

    mock_run_fixer.side_effect = [first_fix_res, second_fix_res]
    mock_render_screenshot.return_value = "fake_base64_string"
    mock_verify_layout.return_value = {"layout_ok": False, "reasons": ["Text overlap on header"]}

    files = [{"path": "index.html", "content": "<html><body><img src='x.png'></body></html>"}]
    res = await _run_fixes_and_generate_zip(files, None)

    assert "changes_summary" in res
    changes = res["changes_summary"]
    assert any("Fixed img alt" in s for s in changes)
    assert any("Ajuste visual aplicado para corrigir quebras de design" in s for s in changes)
    assert mock_run_fixer.call_count == 2
