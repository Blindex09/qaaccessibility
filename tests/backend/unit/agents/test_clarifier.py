import json
from unittest.mock import AsyncMock, patch

import pytest

from backend.src.agents.clarifier.clarifier import run_clarifier


@pytest.mark.asyncio
class TestClarifierAgent:
    async def test_empty_message_returns_needs_clarification_without_calling_llm(self):
        mock_llm = AsyncMock()
        with patch("backend.src.agents.clarifier.clarifier.call_llm", new=mock_llm):
            result = await run_clarifier("   ")
        assert result.success is True
        assert result.data["intent"] == "needs_clarification"
        assert result.data["needs_clarification"] is True
        mock_llm.assert_not_called()

    async def test_analyze_url_intent_classified(self):
        payload = json.dumps(
            {
                "intent": "analyze_url",
                "needs_clarification": False,
                "question": "",
                "explanation": "Usuario pediu analise de uma URL especifica.",
            }
        )
        with patch("backend.src.agents.clarifier.clarifier.call_llm", new=AsyncMock(return_value=payload)):
            result = await run_clarifier("analise https://example.com por favor")
        assert result.success is True
        assert result.data["intent"] == "analyze_url"
        assert result.data["needs_clarification"] is False

    async def test_ambiguous_message_generates_clarification_question(self):
        payload = json.dumps(
            {
                "intent": "needs_clarification",
                "needs_clarification": True,
                "question": "Qual URL ou arquivo você gostaria que eu analisasse?",
                "explanation": "Pedido ambiguo, sem alvo definido.",
            }
        )
        with patch("backend.src.agents.clarifier.clarifier.call_llm", new=AsyncMock(return_value=payload)):
            result = await run_clarifier("analisa isso ai")
        assert result.data["needs_clarification"] is True
        assert result.data["question"]

    async def test_missing_keys_in_llm_response_fall_back_to_defaults(self):
        """Resposta do LLM sem needs_clarification/question/explanation nao deve quebrar."""
        with patch(
            "backend.src.agents.clarifier.clarifier.call_llm",
            new=AsyncMock(return_value=json.dumps({"intent": "chat_a11y"})),
        ):
            result = await run_clarifier("o que é WCAG?")
        assert result.success is True
        assert result.data["intent"] == "chat_a11y"
        assert result.data["needs_clarification"] is False
        assert result.data["question"] == ""

    async def test_failure_on_invalid_json(self):
        with patch(
            "backend.src.agents.clarifier.clarifier.call_llm",
            new=AsyncMock(return_value="not json"),
        ):
            result = await run_clarifier("qualquer coisa")
        assert result.success is False
        assert result.error is not None

    async def test_failure_on_llm_exception(self):
        with patch(
            "backend.src.agents.clarifier.clarifier.call_llm",
            new=AsyncMock(side_effect=Exception("provider down")),
        ):
            result = await run_clarifier("qualquer coisa")
        assert result.success is False
        assert "provider down" in result.error
