"""Testes de instrumentação OpenTelemetry do loop agêntico.

Bug real de auditoria: o `telemetry.py` configurava exportador OTLP e definia
`agent_span()`, mas `agent_span` nunca era chamado em lugar nenhum -- o único uso
do módulo era `configure_telemetry()` no startup. Ou seja: telemetria totalmente
configurada e zero spans produzidos.
"""

from typing import Any

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from backend.src.services import telemetry
from backend.src.services.chat_runtime import stream_chat
from run_agent import run_local_tool


@pytest.fixture
def exporter(monkeypatch) -> InMemorySpanExporter:
    """Tracer em memória no lugar do exportador OTLP real."""
    memory_exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(memory_exporter))
    monkeypatch.setattr(telemetry, "_CONFIGURED", True)
    monkeypatch.setattr(telemetry, "_tracer", trace.get_tracer("test", tracer_provider=provider))
    return memory_exporter


class _SpanningAgent:
    def __init__(self, **kwargs: Any) -> None:
        pass

    def run_conversation(self, user_message: str) -> dict[str, Any]:
        return {"final_response": "ok", "failed": False, "usage": {"input_tokens": 7, "output_tokens": 3}}


def test_tool_execution_creates_a_span(exporter, monkeypatch):
    from tools.registry import registry

    monkeypatch.setitem(
        registry.tools,
        "spanned_test_tool",
        {"schema": {"parameters": {}}, "handler": lambda _args: "ok", "is_async": False, "emoji": ""},
    )
    run_local_tool("spanned_test_tool", {})

    spans = exporter.get_finished_spans()
    assert [s.name for s in spans] == ["agent.tool"]
    assert spans[0].attributes["gen_ai.tool.name"] == "spanned_test_tool"


@pytest.mark.asyncio
async def test_chat_turn_creates_a_span_with_model_attributes(exporter):
    from unittest.mock import patch

    with patch("backend.src.services.chat_runtime.AIAgent", new=_SpanningAgent):
        _ = [ev async for ev in stream_chat("oi", provider="anthropic", model="claude-opus-5")]

    spans = [s for s in exporter.get_finished_spans() if s.name == "agent.chat_turn"]
    assert len(spans) == 1
    assert spans[0].attributes["gen_ai.system"] == "anthropic"
    assert spans[0].attributes["gen_ai.request.model"] == "claude-opus-5"
    assert spans[0].attributes["gen_ai.usage.input_tokens"] == 7
    assert spans[0].attributes["gen_ai.usage.output_tokens"] == 3
