import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from backend.src.agents.orchestrator.orchestrator import orchestrate
from backend.src.security.dependencies import rate_limit_dependency
from backend.src.shared.models import AgentResult, TaskType

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/report", tags=["report"], dependencies=[Depends(rate_limit_dependency)])


class ReportRequest(BaseModel):
    html_content: str


@router.post("/", response_model=AgentResult)
async def generate_report(body: ReportRequest) -> AgentResult:
    logger.info("[Route] POST /report")
    return await orchestrate(body.html_content, TaskType.REPORT)
