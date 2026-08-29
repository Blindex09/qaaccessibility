import json
from unittest.mock import AsyncMock, patch

import pytest

from backend.src.agents.visual_a11y.visual_a11y import run_visual_a11y


@pytest.mark.asyncio
class TestVisualA11yAgent:
    async def test_visual_a11y_on_success(self):
        mock_issues = [
            {
                "id": "visual-a11y-1",
                "guideline": "WCAG 2.2",
                "criterion": "1.4.3 Contrast Minimum",
                "severity": "high",
                "level": "AA",
                "element": ".banner-text",
                "description": "Texto branco sobre fundo amarelo claro sem contraste.",
                "description_technical": "Contrast ratio below 4.5:1 on background banner.",
                "why_simple": "Usuários de baixa visão não conseguem ler o banner.",
                "why_technical": "Visual barrier due to contrast failure.",
                "suggestion": "Escurecer a cor de fundo do banner.",
                "suggestion_technical": "Change background-color to #0b1120.",
                "wcag_url": "https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum"
            }
        ]

        with patch(
            "backend.src.agents.visual_a11y.visual_a11y.call_llm",
            new=AsyncMock(return_value=json.dumps(mock_issues)),
        ):
            result = await run_visual_a11y("<html></html>", "base64_string")

        assert result.success is True
        assert result.agent == "visual_a11y"
        assert len(result.data["issues"]) == 1
        assert result.data["issues"][0]["id"] == "visual-a11y-1"

    async def test_visual_a11y_empty_screenshot(self):
        result = await run_visual_a11y("<html></html>", "")
        assert result.success is True
        assert result.data["issues"] == []

    async def test_visual_a11y_failure_on_invalid_json(self):
        with patch(
            "backend.src.agents.visual_a11y.visual_a11y.call_llm",
            new=AsyncMock(return_value="not a json array"),
        ):
            result = await run_visual_a11y("<html></html>", "base64_string")

        assert result.success is False
        assert "issues" not in result.data
        assert result.error is not None

    async def test_visual_a11y_failure_on_llm_exception(self):
        with patch(
            "backend.src.agents.visual_a11y.visual_a11y.call_llm",
            new=AsyncMock(side_effect=Exception("Vision API timeout")),
        ):
            result = await run_visual_a11y("<html></html>", "base64_string")

        assert result.success is False
        assert "issues" not in result.data
        assert "Vision API timeout" in result.error
