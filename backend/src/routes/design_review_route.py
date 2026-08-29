import logging

from fastapi import APIRouter, Depends, HTTPException

from backend.src.agents.design_review.design_review import run_design_review
from backend.src.security.dependencies import rate_limit_dependency
from backend.src.shared.models import AgentResult, DesignReviewRequest

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Rota: /analyze/design-review
#
# Agente invocado: design_review (shift-left)
#
# Diferente de /analyze (que audita HTML/codigo que ja existe), esta rota
# antecipa riscos de acessibilidade a partir de um requisito, user story ou
# descricao de componente/fluxo em texto livre -- ANTES de qualquer codigo
# ser escrito.
# ─────────────────────────────────────────────────────────────────────────────

router = APIRouter(
    prefix="/analyze",
    tags=["design-review"],
    dependencies=[Depends(rate_limit_dependency)],
)


@router.post("/design-review", response_model=AgentResult)
async def design_review(body: DesignReviewRequest) -> AgentResult:
    """
    Antecipa riscos de acessibilidade a partir de um requisito/user story/
    descricao de componente em texto livre, antes de qualquer codigo existir.

    Cada risco retornado (`risk_flags`) inclui os criterios WCAG 2.2
    provavelmente afetados, a severidade se ignorado, o porque especifico
    daquele requisito gerar esse risco, e uma recomendacao concreta e
    acionavel para o time decidir ANTES de implementar.
    """
    if not body.requirement_text.strip():
        raise HTTPException(status_code=422, detail="Forneça 'requirement_text' para revisar.")

    logger.info(
        "[Route] POST /analyze/design-review -- %d chars, component_type=%s",
        len(body.requirement_text),
        body.component_type or "não informado",
    )
    result = await run_design_review(body.requirement_text, body.component_type)

    if not result.success:
        logger.error("[Route] design_review falhou: %s", result.error)
        raise HTTPException(status_code=500, detail=f"Falha na revisão de design: {result.error}")

    return result
