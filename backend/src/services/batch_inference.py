"""Batch Inference (2026): submissao assincrona de muitas chamadas de LLM de
uma vez, com desconto de custo (~50%) e SLA de ate 24h -- documentado nas 3
APIs abaixo apos pesquisa nas docs oficiais de cada provider.

Escopo deliberado: so OpenAI, Anthropic e Gemini. xAI documenta uma Batch API
mas SEM percentual de desconto explicito (diferente dos outros 3, que
documentam 50%); Ollama Cloud nao tem Batch API nenhuma (so /api/generate e
/api/chat sincronos). Chamar `submit_batch` com qualquer provider fora dos 3
suportados levanta `BatchNotSupportedError` -- o chamador deve cair pro
pipeline sincrono existente, nunca falhar o fluxo por isso.

Batch NAO serve para o fluxo principal do produto (usuario aperta "analisar"
e espera na hora): o SLA e best-effort de até 24h. O caso de uso real e
processamento em lote sem urgencia (ex.: crawl grande agendado). Ver
VERIFICATION.md para o racional completo e o que foi ou nao integrado ao
pipeline de crawl.
"""

import json
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)

_SUPPORTED_PROVIDERS = frozenset({"openai", "anthropic", "gemini"})


class BatchNotSupportedError(Exception):
    """Provider sem Batch API documentada com desconto claro (ver pesquisa
    2026 no docstring do modulo). O chamador deve cair pro pipeline sincrono."""


class BatchStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class BatchRequest:
    """Uma linha do batch: mesmo contrato de `llm_client.call_llm`
    (system_prompt + user_prompt), pra poder reusar prompts dos agentes de
    analise sem reescreve-los."""

    custom_id: str
    system_prompt: str
    user_prompt: str
    model: str
    max_tokens: int = 4096


def _require_supported(provider: str) -> None:
    if provider not in _SUPPORTED_PROVIDERS:
        raise BatchNotSupportedError(
            f"Provider '{provider}' nao tem Batch API com desconto documentado "
            f"(suportados: {sorted(_SUPPORTED_PROVIDERS)}). Use o pipeline sincrono."
        )


# ── OpenAI: upload JSONL -> cria batch referenciando o file_id ──────────────


def _submit_openai_batch(requests: list[BatchRequest], api_key: str, base_url: str | None) -> str:
    from openai import OpenAI

    client = OpenAI(api_key=api_key, base_url=base_url or None)
    lines = []
    for r in requests:
        lines.append(json.dumps({
            "custom_id": r.custom_id,
            "method": "POST",
            "url": "/v1/responses",
            "body": {
                "model": r.model,
                "input": [{"role": "user", "content": r.user_prompt}],
                "instructions": r.system_prompt,
                "max_output_tokens": r.max_tokens,
            },
        }))
    jsonl_bytes = ("\n".join(lines) + "\n").encode("utf-8")
    uploaded = client.files.create(file=("batch_input.jsonl", jsonl_bytes), purpose="batch")
    batch = client.batches.create(
        input_file_id=uploaded.id,
        endpoint="/v1/responses",
        completion_window="24h",
    )
    return batch.id


def _poll_openai_batch(batch_id: str, api_key: str, base_url: str | None) -> BatchStatus:
    from openai import OpenAI

    client = OpenAI(api_key=api_key, base_url=base_url or None)
    batch = client.batches.retrieve(batch_id)
    return {
        "validating": BatchStatus.PENDING,
        "in_progress": BatchStatus.RUNNING,
        "finalizing": BatchStatus.RUNNING,
        "completed": BatchStatus.COMPLETED,
        "failed": BatchStatus.FAILED,
        "expired": BatchStatus.FAILED,
        "cancelling": BatchStatus.FAILED,
        "cancelled": BatchStatus.FAILED,
    }.get(str(batch.status), BatchStatus.RUNNING)


def _fetch_openai_batch_results(batch_id: str, api_key: str, base_url: str | None) -> dict[str, str]:
    from openai import OpenAI

    client = OpenAI(api_key=api_key, base_url=base_url or None)
    batch = client.batches.retrieve(batch_id)
    if not batch.output_file_id:
        return {}
    content = client.files.content(batch.output_file_id)
    results: dict[str, str] = {}
    for line in content.text.splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        custom_id = row.get("custom_id", "")
        results[custom_id] = _extract_openai_responses_text(row.get("response", {}).get("body", {}))
    return results


def _extract_openai_responses_text(body: dict[str, Any]) -> str:
    for item in body.get("output", []):
        if item.get("type") != "message":
            continue
        for block in item.get("content", []):
            if block.get("type") == "output_text":
                return str(block.get("text", ""))
    return ""


# ── Anthropic: requests inline, sem upload de arquivo ────────────────────────


def _submit_anthropic_batch(requests: list[BatchRequest], api_key: str, base_url: str | None) -> str:
    import anthropic

    client = anthropic.Anthropic(api_key=api_key, base_url=base_url or None)
    batch_requests: list[dict[str, Any]] = [
        {
            "custom_id": r.custom_id,
            "params": {
                "model": r.model,
                "max_tokens": r.max_tokens,
                "system": r.system_prompt,
                "messages": [{"role": "user", "content": r.user_prompt}],
            },
        }
        for r in requests
    ]
    # O SDK tipa `requests` como TypedDict aninhado (Request -> params:
    # MessageCreateParamsNonStreaming), com dezenas de campos opcionais
    # (tool_choice, thinking, etc.). Nosso payload e um subconjunto valido em
    # runtime (mesmos campos que client.messages.create aceita), mas nao
    # combina estruturalmente com o TypedDict estrito via dict[str, Any].
    batch = client.messages.batches.create(requests=batch_requests)  # type: ignore[arg-type]
    return batch.id


def _poll_anthropic_batch(batch_id: str, api_key: str, base_url: str | None) -> BatchStatus:
    import anthropic

    client = anthropic.Anthropic(api_key=api_key, base_url=base_url or None)
    batch = client.messages.batches.retrieve(batch_id)
    return {
        "in_progress": BatchStatus.RUNNING,
        "canceling": BatchStatus.FAILED,
        "ended": BatchStatus.COMPLETED,
    }.get(str(batch.processing_status), BatchStatus.RUNNING)


def _fetch_anthropic_batch_results(batch_id: str, api_key: str, base_url: str | None) -> dict[str, str]:
    import anthropic

    client = anthropic.Anthropic(api_key=api_key, base_url=base_url or None)
    results: dict[str, str] = {}
    for entry in client.messages.batches.results(batch_id):
        custom_id = str(getattr(entry, "custom_id", ""))
        result = getattr(entry, "result", None)
        if result is None or getattr(result, "type", "") != "succeeded":
            results[custom_id] = ""
            continue
        message = getattr(result, "message", None)
        text_parts = [
            str(getattr(block, "text", ""))
            for block in (getattr(message, "content", None) or [])
            if getattr(block, "type", "") == "text"
        ]
        results[custom_id] = "".join(text_parts)
    return results


# ── Gemini: requests inline via InlinedRequest, correlacao por metadata ──────


def _submit_gemini_batch(requests: list[BatchRequest], api_key: str) -> str:
    from google import genai
    from google.genai import types

    if not requests:
        raise ValueError("submit_batch chamado sem nenhuma request")

    client = genai.Client(api_key=api_key)
    src = [
        types.InlinedRequest(
            contents=r.user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=r.system_prompt,
                max_output_tokens=r.max_tokens,
            ),
            metadata={"custom_id": r.custom_id},
        )
        for r in requests
    ]
    job = client.batches.create(model=requests[0].model, src=src)
    return str(job.name)


def _poll_gemini_batch(batch_id: str, api_key: str) -> BatchStatus:
    from google import genai

    client = genai.Client(api_key=api_key)
    job = client.batches.get(name=batch_id)
    state = str(job.state)
    if state in ("JobState.JOB_STATE_SUCCEEDED", "JOB_STATE_SUCCEEDED"):
        return BatchStatus.COMPLETED
    if state in (
        "JobState.JOB_STATE_FAILED", "JOB_STATE_FAILED",
        "JobState.JOB_STATE_CANCELLED", "JOB_STATE_CANCELLED",
        "JobState.JOB_STATE_EXPIRED", "JOB_STATE_EXPIRED",
    ):
        return BatchStatus.FAILED
    if state in ("JobState.JOB_STATE_QUEUED", "JOB_STATE_QUEUED", "JobState.JOB_STATE_PENDING", "JOB_STATE_PENDING"):
        return BatchStatus.PENDING
    return BatchStatus.RUNNING


def _fetch_gemini_batch_results(batch_id: str, api_key: str) -> dict[str, str]:
    from google import genai

    client = genai.Client(api_key=api_key)
    job = client.batches.get(name=batch_id)
    dest = getattr(job, "dest", None)
    inlined = getattr(dest, "inlined_responses", None) or []
    results: dict[str, str] = {}
    for item in inlined:
        metadata = getattr(item, "metadata", None) or {}
        custom_id = str(metadata.get("custom_id", ""))
        response = getattr(item, "response", None)
        if response is None:
            results[custom_id] = ""
            continue
        results[custom_id] = str(getattr(response, "text", "") or "")
    return results


# ── API pública (dispatcher por provider) ────────────────────────────────────


def submit_batch(
    requests: list[BatchRequest], provider: str, api_key: str, base_url: str | None = None
) -> str:
    """Submete todas as requests como UM job de batch. Devolve o batch_id.
    Levanta `BatchNotSupportedError` se o provider nao tiver Batch API."""
    _require_supported(provider)
    if not requests:
        raise ValueError("submit_batch chamado sem nenhuma request")
    if provider == "openai":
        return _submit_openai_batch(requests, api_key, base_url)
    if provider == "anthropic":
        return _submit_anthropic_batch(requests, api_key, base_url)
    return _submit_gemini_batch(requests, api_key)


def poll_batch(batch_id: str, provider: str, api_key: str, base_url: str | None = None) -> BatchStatus:
    """Consulta o status atual do batch (sem custo extra, nao conta como nova
    chamada de inferencia)."""
    _require_supported(provider)
    if provider == "openai":
        return _poll_openai_batch(batch_id, api_key, base_url)
    if provider == "anthropic":
        return _poll_anthropic_batch(batch_id, api_key, base_url)
    return _poll_gemini_batch(batch_id, api_key)


def fetch_batch_results(
    batch_id: str, provider: str, api_key: str, base_url: str | None = None
) -> dict[str, str]:
    """Devolve {custom_id: texto_da_resposta} para um batch já COMPLETED.
    Chamar antes disso devolve resultado parcial/vazio dependendo do provider
    -- o chamador deve checar `poll_batch` primeiro."""
    _require_supported(provider)
    if provider == "openai":
        return _fetch_openai_batch_results(batch_id, api_key, base_url)
    if provider == "anthropic":
        return _fetch_anthropic_batch_results(batch_id, api_key, base_url)
    return _fetch_gemini_batch_results(batch_id, api_key)
