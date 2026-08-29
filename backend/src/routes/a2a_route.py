import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from backend.src.services.a2a_service import (
    cancel_a2a_task,
    generate_agent_card,
    get_a2a_task_status,
    submit_a2a_task,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["a2a"])


@router.get("/.well-known/agent-card.json", response_class=JSONResponse)
@router.get("/.well-known/agent.json", response_class=JSONResponse)
async def get_agent_card(request: Request) -> dict[str, Any]:
    """
    Retorna o Agent Card oficial A2A v1.0 (Linux Foundation / W3C 2026 Specification).
    Permite que orquestradores de IA descubram dinamicamente as capacidades e skills do agente.
    """
    base_url = str(request.base_url).rstrip("/")
    return generate_agent_card(base_url)


@router.post("/a2a/v1/tasks")
async def create_a2a_task(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Delega uma tarefa A2A ao agente QA Accessibility.

    Body:
    {
        "skill_id": "accessibility_analysis|self_healing_fix|sarif_export",
        "input": { ... },
        "parameters": { ... },
        "stream": false
    }
    """
    skill_id = payload.get("skill_id", "accessibility_analysis")
    input_data = payload.get("input", {})
    parameters = payload.get("parameters", {})
    stream = bool(payload.get("stream", False))
    callback_url = payload.get("callback_url")

    if not input_data:
        raise HTTPException(status_code=400, detail="Input payload eh obrigatorio para criar tarefa A2A.")

    try:
        return await submit_a2a_task(
            skill_id=skill_id,
            input_data=input_data,
            parameters=parameters,
            stream=stream,
            callback_url=callback_url,
        )
    except Exception as exc:
        logger.error(f"[A2ARoute] Falha ao criar tarefa A2A: {exc}")
        raise HTTPException(status_code=500, detail="Falha ao criar tarefa A2A.") from exc


@router.get("/a2a/v1/tasks/{task_id}")
async def get_task_status_endpoint(task_id: str) -> dict[str, Any]:
    """
    Consulta o estado de execucao, progresso e resultados da tarefa A2A.
    """
    status_data = get_a2a_task_status(task_id)
    if status_data.get("error") == "Task ID nao encontrado.":
        raise HTTPException(status_code=404, detail="Tarefa A2A nao encontrada.")
    return status_data


@router.post("/a2a/v1/tasks/{task_id}/cancel", operation_id="cancel_task_endpoint_slash")
@router.post("/a2a/v1/tasks/{task_id}:cancel", operation_id="cancel_task_endpoint_colon")
async def cancel_task_endpoint(task_id: str) -> dict[str, Any]:
    """
    Cancela graciosamente uma tarefa A2A em andamento.
    """
    return cancel_a2a_task(task_id)


@router.get("/a2a/v1/tasks/{task_id}/subscribe")
async def subscribe_task_stream(task_id: str) -> StreamingResponse:
    """
    Streaming SSE em tempo real dos eventos de progresso da tarefa A2A.
    """
    async def event_generator():
        while True:
            status_data = get_a2a_task_status(task_id)
            current_status = status_data.get("status", "working")
            progress = status_data.get("progress", 0.0)

            event_payload = {
                "task_id": task_id,
                "status": current_status,
                "progress": progress,
                "updated_at": status_data.get("updated_at"),
            }

            yield f"event: TaskStatusUpdateEvent\ndata: {json.dumps(event_payload)}\n\n"

            if current_status in ["completed", "failed", "canceled"]:
                if current_status == "completed":
                    chunk_payload = {
                        "task_id": task_id,
                        "output": status_data.get("output"),
                    }
                    yield f"event: TaskOutputChunkEvent\ndata: {json.dumps(chunk_payload)}\n\n"
                break

            await asyncio.sleep(0.5)

    return StreamingResponse(event_generator(), media_type="text/event-stream")
