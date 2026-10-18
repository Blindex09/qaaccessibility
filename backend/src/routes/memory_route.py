"""Memória de longo prazo visível e editável pela pessoa (regra 10 e regra 18): lista, lê, edita e apaga habilidades SKILL.md."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.src.security.dependencies import rate_limit_dependency
from backend.src.services import mcp_client, skill_memory

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/memory", tags=["memory"], dependencies=[Depends(rate_limit_dependency)])


class SkillBody(BaseModel):
    description: str = Field(min_length=1, max_length=skill_memory.MAX_DESCRIPTION)
    instructions: str = Field(min_length=1)


@router.get("/mcp-servers")
async def list_mcp_servers() -> dict[str, list[dict]]:
    """Servidores MCP externos que a pessoa registrou (só os nomes das credenciais, nunca os valores)."""
    return {"servers": mcp_client.list_servers()}


@router.delete("/mcp-servers/{name}")
async def delete_mcp_server(name: str) -> dict[str, bool]:
    if not mcp_client.remove_server(name):
        raise HTTPException(status_code=404, detail="Servidor MCP não registrado.")
    return {"deleted": True}


@router.get("/skills")
async def list_skills() -> dict[str, list[dict[str, str]]]:
    return {"skills": skill_memory.list_skills()}


@router.get("/skills/{name}")
async def get_skill(name: str) -> dict:
    try:
        return skill_memory.read_skill(name)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Habilidade não encontrada.") from None
    except skill_memory.SkillError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None


@router.put("/skills/{name}")
async def put_skill(name: str, body: SkillBody) -> dict:
    """Quando a pessoa edita, a origem passa a ser dela e a confiança sobe: ela é a fonte."""
    try:
        return skill_memory.save_skill(name, body.description, body.instructions, origin=skill_memory.ORIGIN_PERSON, source="editada pela pessoa")
    except skill_memory.SkillError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None


@router.delete("/skills/{name}")
async def delete_skill(name: str) -> dict[str, bool]:
    try:
        removed = skill_memory.delete_skill(name)
    except skill_memory.SkillError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    if not removed:
        raise HTTPException(status_code=404, detail="Habilidade não encontrada.")
    return {"deleted": True}
