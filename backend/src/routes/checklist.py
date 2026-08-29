import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from backend.src.agents.checklist.checklist import run_checklist
from backend.src.security.dependencies import rate_limit_dependency
from backend.src.shared.models import AccessibilityIssue, AgentResult

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/checklist",
    tags=["checklist"],
    dependencies=[Depends(rate_limit_dependency)],
)


class ChecklistRequestBody(BaseModel):
    issues: list[AccessibilityIssue]
    html_content: str | None = None


@router.post("/", response_model=AgentResult)
async def generate_checklist(body: ChecklistRequestBody) -> AgentResult:
    logger.info("[Route] POST /checklist issues=%d (html_content=%s)", len(body.issues), bool(body.html_content))
    return await run_checklist(body.issues, body.html_content)
