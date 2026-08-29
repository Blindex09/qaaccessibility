import json
import logging
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend.src.security.dependencies import rate_limit_dependency
from backend.src.services import chat_progress
from backend.src.services.chat_runtime import stream_chat
from backend.src.shared.error_formatter import format_human_friendly_error

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/chat",
    tags=["chat"],
    dependencies=[Depends(rate_limit_dependency)],
)


class ChatMessage(BaseModel):
    role: str = Field(..., description="'user' ou 'assistant'")
    content: str


class ChatRequest(BaseModel):
    message: str = Field(..., description="Mensagem do usuário")
    history: list[ChatMessage] = Field(default_factory=list, description="Historico do dialogo")
    provider: str | None = Field(default=None, description="Provider escolhido (ex.: openai, anthropic)")
    model: str | None = Field(default=None, description="Modelo escolhido (ex.: gpt-5.2)")
    conversation_id: str | None = Field(
        default=None,
        max_length=128,
        description="Identificador estável da conversa para continuidade nativa do provedor",
    )


class ClarifyAnswer(BaseModel):
    request_id: str = Field(..., description="ID da pergunta pendente (evento 'clarify')")
    answer: str = Field(default="", description="Resposta do usuário (vazio = pular)")


class CancelRequest(BaseModel):
    stream_id: str = Field(..., description="ID do turno em andamento (evento 'stream_id')")


def _sse(event: dict[str, object]) -> str:
    """Formata um evento como Server-Sent Event."""
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


@router.post("/stream")
async def chat_stream(body: ChatRequest) -> StreamingResponse:
    """
    Chat agentico de acessibilidade com streaming token-a-token (SSE).

    O agente conversa, chama a tool `analyze_page` quando necessário e envia
    apenas progresso observável. Cada evento é um SSE:
    token | phase | agent | tool_start | tool_result | done | error.
    """
    history = [{"role": m.role, "content": m.content} for m in body.history]

    async def event_source() -> AsyncIterator[str]:
        logger.info("[Route] POST /chat/stream -- %d chars, history=%d", len(body.message), len(history))
        try:
            async for event in stream_chat(
                body.message,
                history,
                provider=body.provider,
                model=body.model,
                conversation_id=body.conversation_id,
            ):
                yield _sse(event)
        except Exception as exc:  # pragma: no cover - defensivo
            logger.error("[Route] chat_stream erro: %s", exc)
            yield _sse({"type": "error", "error": format_human_friendly_error(exc)})

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/clarify")
async def chat_clarify(body: ClarifyAnswer) -> dict:
    """Recebe a resposta do usuário a uma pergunta do agente (evento 'clarify')
    e desbloqueia o turno em andamento. Canal de volta do chat (o stream SSE
    e mao-unica). ``delivered=False`` se a pergunta ja expirou/não existe."""
    delivered = chat_progress.answer_clarify(body.request_id, body.answer)
    return {"delivered": delivered}


@router.post("/cancel")
async def chat_cancel(body: CancelRequest) -> dict:
    """Interrompe o turno de chat identificado pelo `stream_id` (1º evento SSE
    do stream). Best-effort: para de entregar eventos ao stream imediatamente;
    não aborta uma chamada HTTP síncrona já em andamento no provider (ver
    chat_progress.py). ``cancelled=False`` se o turno já terminou/não existe."""
    cancelled = chat_progress.request_cancel(body.stream_id)
    return {"cancelled": cancelled}


@router.get("/history/{conversation_id}")
async def get_chat_history(conversation_id: str) -> dict:
    """Histórico persistido de uma conversa -- permite ao frontend restaurar a
    tela depois de um reload em vez de começar do zero (chat_history_store.py)."""
    from backend.src.services import chat_history_store

    messages = chat_history_store.get_history(session_id=conversation_id)
    return {"conversation_id": conversation_id, "messages": messages}


@router.get("/conversations")
async def list_chat_conversations(limit: int = 20) -> dict:
    """Lista as conversas mais recentes (id, prévia da primeira mensagem,
    contagem, última atualização) -- para um seletor de conversas na UI."""
    from backend.src.services import chat_history_store

    conversations = chat_history_store.list_conversations(limit=limit)
    return {"conversations": conversations}


@router.delete("/history/{conversation_id}")
async def delete_chat_history(conversation_id: str) -> dict:
    """Apaga o histórico persistido de uma conversa (ex.: usuário pede para
    começar uma conversa nova do zero, ou 'esquecer' esta)."""
    from backend.src.services import chat_history_store

    chat_history_store.clear_history(session_id=conversation_id)
    return {"cleared": True}
