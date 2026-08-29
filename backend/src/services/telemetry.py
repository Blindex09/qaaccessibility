"""
telemetry.py
Configuração de observabilidade OpenTelemetry para o loop agêntico.

Se OTEL_EXPORTER_OTLP_ENDPOINT não estiver definido, o módulo é
no-op silencioso — zero impacto em ambientes sem telemetria configurada.

Variáveis de ambiente:
  OTEL_EXPORTER_OTLP_ENDPOINT  ex.: http://localhost:4317  (gRPC OTLP)
  OTEL_SERVICE_NAME            default: qaaccessibility
  OTEL_EXPORTER_OTLP_HEADERS   ex.: Authorization=Bearer <token> (Langfuse)

Fonte: OpenTelemetry GenAI semantic conventions 2026 + Langfuse OTLP docs.
"""

import logging
import os
from collections.abc import Generator
from contextlib import contextmanager, suppress

logger = logging.getLogger(__name__)

_CONFIGURED = False
_tracer = None


def configure_telemetry() -> None:
    """Chama no startup da aplicação. No-op se OTEL_EXPORTER_OTLP_ENDPOINT não estiver definido."""
    global _CONFIGURED, _tracer
    if _CONFIGURED:
        return
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
    if not endpoint:
        logger.info("[telemetry] OTEL_EXPORTER_OTLP_ENDPOINT não configurado — telemetria desactivada.")
        _CONFIGURED = True
        return
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        service_name = os.getenv("OTEL_SERVICE_NAME", "qaaccessibility")
        headers_raw = os.getenv("OTEL_EXPORTER_OTLP_HEADERS", "")
        headers: dict[str, str] = {}
        for item in headers_raw.split(","):
            if "=" in item:
                k, v = item.split("=", 1)
                headers[k.strip()] = v.strip()

        resource = Resource.create({"service.name": service_name})
        exporter = OTLPSpanExporter(
            endpoint=endpoint,
            headers=headers or None,
        )
        provider = TracerProvider(resource=resource)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)
        _tracer = trace.get_tracer("qaaccessibility.agent")
        logger.info("[telemetry] OpenTelemetry configurado -> %s (service: %s)", endpoint, service_name)
    except Exception as exc:
        logger.warning("[telemetry] Falha ao configurar OpenTelemetry: %s. Telemetria desactivada.", exc)
    _CONFIGURED = True


def get_tracer():
    """Devolve o tracer configurado ou None se telemetria estiver desactivada."""
    if not _CONFIGURED:
        configure_telemetry()
    return _tracer


@contextmanager
def agent_span(name: str, attributes: dict | None = None) -> Generator:
    """
    Context manager que cria um span OpenTelemetry se a telemetria estiver activa.
    No-op transparente se o tracer não estiver configurado.

    Uso:
        with agent_span("agent_iteration", {"iteration_index": i}) as span:
            if span:
                span.set_attribute("gen_ai.model", model)
    """
    tracer = get_tracer()
    if tracer is None:
        yield None
        return
    try:
        with tracer.start_as_current_span(name) as span:
            if attributes:
                for k, v in attributes.items():
                    with suppress(Exception):
                        span.set_attribute(
                            k,
                            str(v) if not isinstance(v, (bool, int, float, str)) else v,
                        )
            yield span
    except Exception:
        yield None


# --------------------------------------------------------------------------- #
# Online scoring de traces (LLM-as-judge) — padrão Braintrust/DeepEval 2026
# --------------------------------------------------------------------------- #
# Pontua spans de produção assincronamente, sem impactar latência. Usa o
# call_llm do próprio projeto (mesmo provider configurado). Resultado deve
# ser anotado no span pelo chamador como atributo eval.score.
# Sem provider configurado -> no-op (devolve None).


_DEFAULT_RUBRIC = (
    "Avalie a qualidade do turno do agente nas dimensões:\n"
    "1. Factual accuracy: as afirmações são precisas e fundamentadas?\n"
    "2. Completeness: todos os aspectos pedidos foram cobertos?\n"
    "3. Tool efficiency: as ferramentas certas foram usadas um número razoável de vezes?\n"
    "Devolva um JSON: {\"score\": <0.0-1.0>, \"pass\": <bool>, \"reason\": \"<texto curto>\"}"
)


async def score_trace(
    trace_text: str,
    criteria: str = "",
    *,
    provider: str | None = None,
) -> dict | None:
    """
    Pontua um trace de produção com LLM-as-judge.

    Assíncrono (não impacta latência do fluxo principal). Usa call_llm do
    projeto. Sem provider configurado -> devolve None (no-op seguro).

    Args:
        trace_text: texto consolidado do trace (turno + tool calls + output).
        criteria: critérios adicionais além da rubric default (opcional).
        provider: override do provider julgador (default: config vigente).

    Returns:
        {"score": float, "pass": bool, "reason": str} ou None se no-op.
    """
    if not trace_text or not trace_text.strip():
        return None

    try:
        from backend.src.config.settings import get_settings
        settings = get_settings()
        prov = provider or getattr(settings, "llm_provider", "") or ""
        if not prov:
            return None  # no-op: sem provider configurado

        from backend.src.services.llm_client import call_llm

        rubric = _DEFAULT_RUBRIC
        if criteria:
            rubric = rubric + "\nCritérios adicionais:\n" + criteria

        prompt = (
            f"{rubric}\n\n"
            f"--- TRACE DO TURNO ---\n{trace_text[:8000]}\n--- FIM ---\n\n"
            "Devolva somente o JSON."
        )
        # call_llm devolve str (output cru do modelo); o AIAgent resolve provider/modelo.
        text = await call_llm(
            system_prompt="Você é um juiz de qualidade de traces de IA. Devolva somente JSON válido.",
            user_prompt=prompt,
            agent_label="trace-judge",
        )
        if not text:
            return None

        import json

        # Tenta parsear JSON do response
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict) and "score" in parsed:
                parsed["score"] = float(parsed["score"])
                parsed["pass"] = bool(parsed.get("pass", parsed["score"] >= 0.7))
                return parsed
        except (json.JSONDecodeError, ValueError, TypeError):
            pass
        # Fallback: extrair score com regex
        import re

        match = re.search(r"(\d*\.?\d+)", text)
        if match:
            score = float(match.group(1))
            score = max(0.0, min(1.0, score if score <= 1.0 else score / 10.0))
            return {"score": score, "pass": score >= 0.7, "reason": text[:200]}
        return None
    except Exception as exc:
        logger.warning("[telemetry] score_trace falhou: %s", exc)
        return None
