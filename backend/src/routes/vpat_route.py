import logging

from fastapi import APIRouter, Depends, HTTPException

from backend.src.agents.orchestrator.orchestrator import orchestrate
from backend.src.agents.vpat_reporter.vpat_reporter import run_vpat_reporter
from backend.src.security.dependencies import rate_limit_dependency
from backend.src.shared.models import AgentResult, TaskType, VPATRequest

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Rota: /analyze/vpat
#
# Agente invocado: vpat_reporter
# Fonte do agente: compliance-auditor.md (C:\agents\security\compliance-auditor.md)
#
# Gera um VPAT - Voluntary Product Accessibility Template (WCAG 2.2 Edition).
# Exigido por enterprise, governo (Section 508) e processos de licitacao.
#
# Para cada criterio WCAG 2.2 Level A e AA declara:
#   Supports | Partially Supports | Does Not Support | Not Applicable | Not Evaluated
# ─────────────────────────────────────────────────────────────────────────────

router = APIRouter(
    prefix="/analyze",
    tags=["vpat"],
    dependencies=[Depends(rate_limit_dependency)],
)


@router.post("/vpat", response_model=AgentResult)
async def generate_vpat(body: VPATRequest) -> AgentResult:
    """
    Gera um VPAT (Voluntary Product Accessibility Template) WCAG 2.2 Edition
    baseado nos issues encontrados na análise.

    O VPAT e o documento padrão exigido por empresas enterprise, governo
    (Section 508) e processos de licitacao para declarar conformidade WCAG.

    Declara conformidade para todos os criterios WCAG 2.2 Level A e AA:
    - Supports: nenhum issue relacionado ao criterio
    - Partially Supports: issues medium/high encontrados
    - Does Not Support: issues critical bloqueando o criterio
    - Not Applicable: criterio não se aplica ao conteúdo
    - Not Evaluated: requer teste manual não realizado

    Baseado em compliance-auditor.md:
    - Gap analysis por criterio WCAG
    - Evidence-based conformance declarations
    - Resumo executivo de conformidade
    """
    if not body.issues and not body.html_content:
        raise HTTPException(
            status_code=422,
            detail="Forneca 'issues' (de /analyze/*) ou 'html_content' para análise em uma chamada.",
        )

    if body.html_content:
        logger.info(
            "[Route] POST /analyze/vpat (HTML->VPAT) -- product=%s, target=%s",
            body.product_name,
            body.target or "não informado",
        )
        result = await orchestrate(
            body.html_content,
            TaskType.VPAT,
            target=body.target,
            product_name=body.product_name,
        )
    else:
        logger.info(
            "[Route] POST /analyze/vpat -- %d issues, product=%s, target=%s",
            len(body.issues),
            body.product_name,
            body.target or "não informado",
        )
        result = await run_vpat_reporter(
            issues=body.issues,
            target=body.target,
            product_name=body.product_name,
        )

    if not result.success:
        logger.error("[Route] vpat_reporter falhou: %s", result.error)
        raise HTTPException(
            status_code=500,
            detail=f"Falha ao gerar VPAT: {result.error}",
        )

    return result
