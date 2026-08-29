"""Testes do online scoring de traces (LLM-as-judge em produção).

Valida score_trace: pontua traces de produção com LLM-as-judge, no-op seguro
sem provider configurado. Padrão Braintrust/DeepEval 2026.
"""

import json
from unittest.mock import AsyncMock, patch

import pytest

from backend.src.services import telemetry


@pytest.mark.asyncio
async def test_score_trace_noop_when_no_provider():
    # Sem provider configurado -> no-op (devolve None)
    settings = type("S", (), {"llm_provider": ""})()
    with patch("backend.src.config.settings.get_settings", return_value=settings):
        result = await telemetry.score_trace("trace content", provider="")
    assert result is None


@pytest.mark.asyncio
async def test_score_trace_noop_on_empty_trace():
    settings = type("S", (), {"llm_provider": "openai"})()
    with patch("backend.src.config.settings.get_settings", return_value=settings):
        result = await telemetry.score_trace("", provider="openai")
    assert result is None


@pytest.mark.asyncio
async def test_score_trace_returns_parsed_score_on_valid_json():
    settings = type("S", (), {"llm_provider": "openai"})()
    judge_output = json.dumps({"score": 0.85, "pass": True, "reason": "Boa cobertura"})
    with patch("backend.src.config.settings.get_settings", return_value=settings), patch(
        "backend.src.services.llm_client.call_llm", new=AsyncMock(return_value=judge_output)
    ) as mock_call:
        result = await telemetry.score_trace("turno com tool calls", provider="openai")
    assert result is not None
    assert result["score"] == 0.85
    assert result["pass"] is True
    assert mock_call.await_count == 1
    # system_prompt e user_prompt passados corretamente
    args, kwargs = mock_call.call_args
    assert "juiz" in kwargs.get("system_prompt", "").lower() or "juiz" in args[0].lower()


@pytest.mark.asyncio
async def test_score_trace_falls_back_to_regex_when_json_invalid():
    settings = type("S", (), {"llm_provider": "openai"})()
    # Output sem JSON válido mas com número extraível
    judge_output = "Nota: 0.9 — bom desempenho geral do agente."
    with patch("backend.src.config.settings.get_settings", return_value=settings), patch(
        "backend.src.services.llm_client.call_llm", new=AsyncMock(return_value=judge_output)
    ):
        result = await telemetry.score_trace("trace", provider="openai")
    assert result is not None
    assert result["score"] == 0.9
    assert result["pass"] is True


@pytest.mark.asyncio
async def test_score_trace_normalizes_score_above_one():
    settings = type("S", (), {"llm_provider": "openai"})()
    # Score em escala 0-10 deve ser normalizado para 0-1
    judge_output = "Score: 8.5 de 10"
    with patch("backend.src.config.settings.get_settings", return_value=settings), patch(
        "backend.src.services.llm_client.call_llm", new=AsyncMock(return_value=judge_output)
    ):
        result = await telemetry.score_trace("trace", provider="openai")
    assert result is not None
    assert result["score"] == 0.85  # 8.5 / 10


@pytest.mark.asyncio
async def test_score_trace_returns_none_when_call_llm_returns_empty():
    settings = type("S", (), {"llm_provider": "openai"})()
    with patch("backend.src.config.settings.get_settings", return_value=settings), patch(
        "backend.src.services.llm_client.call_llm", new=AsyncMock(return_value="")
    ):
        result = await telemetry.score_trace("trace", provider="openai")
    assert result is None


@pytest.mark.asyncio
async def test_score_trace_returns_none_on_exception():
    settings = type("S", (), {"llm_provider": "openai"})()
    with patch("backend.src.config.settings.get_settings", return_value=settings), patch(
        "backend.src.services.llm_client.call_llm", new=AsyncMock(side_effect=RuntimeError("LLM down"))
    ):
        result = await telemetry.score_trace("trace", provider="openai")
    assert result is None


@pytest.mark.asyncio
async def test_score_trace_passes_custom_criteria():
    settings = type("S", (), {"llm_provider": "openai"})()
    judge_output = json.dumps({"score": 0.7, "pass": True, "reason": "ok"})
    with patch("backend.src.config.settings.get_settings", return_value=settings), patch(
        "backend.src.services.llm_client.call_llm", new=AsyncMock(return_value=judge_output)
    ) as mock_call:
        await telemetry.score_trace("trace", criteria="Validar WCAG 2.2", provider="openai")
    args, kwargs = mock_call.call_args
    user_prompt = kwargs.get("user_prompt", "")
    assert "WCAG 2.2" in user_prompt


@pytest.mark.asyncio
async def test_score_trace_truncates_long_trace():
    settings = type("S", (), {"llm_provider": "openai"})()
    judge_output = json.dumps({"score": 0.5, "pass": False, "reason": "incomplete"})
    long_trace = "x" * 20000  # 20KB, bem acima do limite de 8000
    with patch("backend.src.config.settings.get_settings", return_value=settings), patch(
        "backend.src.services.llm_client.call_llm", new=AsyncMock(return_value=judge_output)
    ) as mock_call:
        await telemetry.score_trace(long_trace, provider="openai")
    args, kwargs = mock_call.call_args
    user_prompt = kwargs.get("user_prompt", "")
    # Trace deve ser truncado para não estourar o contexto do judge
    assert len(user_prompt) < 10000
