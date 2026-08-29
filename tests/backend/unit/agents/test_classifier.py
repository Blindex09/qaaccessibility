import json
from unittest.mock import AsyncMock, patch

import pytest

from backend.src.agents.classifier.classifier import run_classifier


@pytest.mark.asyncio
class TestClassifierAgent:
    async def test_classifier_on_success(self):
        with patch(
            "backend.src.agents.classifier.classifier.call_llm",
            new=AsyncMock(return_value=json.dumps(["react", "tailwind"])),
        ):
            result = await run_classifier("<html></html>")
        assert result.success is True
        assert result.agent == "classifier"
        assert set(result.data["technologies"]) == {"react", "tailwind"}

    async def test_classifier_detects_svelte(self):
        with patch(
            "backend.src.agents.classifier.classifier.call_llm",
            new=AsyncMock(return_value=json.dumps(["svelte"])),
        ):
            result = await run_classifier("<html data-svelte-h='1'></html>")
        assert result.success is True
        assert result.data["technologies"] == ["svelte"]

    async def test_classifier_filters_invalid_techs(self):
        # Deve filtrar tecnologias desconhecidas
        with patch(
            "backend.src.agents.classifier.classifier.call_llm",
            new=AsyncMock(return_value=json.dumps(["react", "jquery", "tailwind", "cobol"])),
        ):
            result = await run_classifier("<html></html>")
        assert result.success is True
        assert set(result.data["technologies"]) == {"react", "tailwind"}

    async def test_classifier_empty_html(self):
        result = await run_classifier("")
        assert result.success is True
        assert result.data["technologies"] == []

    async def test_classifier_failure_on_invalid_json(self):
        with patch(
            "backend.src.agents.classifier.classifier.call_llm",
            new=AsyncMock(return_value="not a json array"),
        ):
            result = await run_classifier("<html></html>")
        assert result.success is False
        assert result.data["technologies"] == []
        assert result.error is not None

    async def test_classifier_failure_on_llm_exception(self):
        with patch(
            "backend.src.agents.classifier.classifier.call_llm",
            new=AsyncMock(side_effect=Exception("API connection error")),
        ):
            result = await run_classifier("<html></html>")
        assert result.success is False
        assert result.data["technologies"] == []
        assert "API connection error" in result.error
