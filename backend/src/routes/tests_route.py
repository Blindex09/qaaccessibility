import logging

from fastapi import APIRouter, Depends, HTTPException

from backend.src.agents.orchestrator.orchestrator import orchestrate
from backend.src.agents.test_generator.test_generator import run_test_generator
from backend.src.security.dependencies import rate_limit_dependency
from backend.src.shared.models import AgentResult, TaskType, TestGeneratorRequest

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Rota: /analyze/tests
#
# Agente invocado: test_generator
# Fontes do agente:
#   playwright-expert.toml  (C:\agents\general\playwright-expert.toml)
#   accessibility-tester.md (C:\agents\security\accessibility-tester.md)
#   tdd-orchestrator.toml   (C:\agents\architecture\tdd-orchestrator.toml)
#
# Dado um conjunto de issues encontrados, gera código de teste real -
# Playwright + axe-core - pronto para integrar no CI do projeto auditado.
# ─────────────────────────────────────────────────────────────────────────────

router = APIRouter(
    prefix="/analyze",
    tags=["tests"],
    dependencies=[Depends(rate_limit_dependency)],
)


@router.post("/tests", response_model=AgentResult)
async def generate_tests(body: TestGeneratorRequest) -> AgentResult:
    """
    Gera uma suite de testes de acessibilidade (Playwright + axe-core)
    a partir dos issues encontrados na análise.

    Os testes gerados podem ser integrados diretamente no CI do projeto
    auditado para prevenir regressoes de acessibilidade.

    Baseado em:
    - playwright-expert.toml: POM, semantic locators, CI integration
    - accessibility-tester.md: WCAG 2.2 test procedures, AT testing patterns
    - tdd-orchestrator.toml: TDD red-green-refactor, test isolation
    """
    if not body.issues and not body.html_content:
        raise HTTPException(
            status_code=422,
            detail="Forneca 'issues' (de /analyze/*) ou 'html_content' para análise em uma chamada.",
        )

    if body.html_content:
        logger.info(
            "[Route] POST /analyze/tests (HTML->tests) -- target=%s",
            body.target or "não informado",
        )
        result = await orchestrate(
            body.html_content,
            TaskType.TESTS,
            target=body.target,
        )
    else:
        logger.info(
            "[Route] POST /analyze/tests -- %d issues, target=%s",
            len(body.issues),
            body.target or "não informado",
        )
        result = await run_test_generator(
            issues=body.issues,
            target=body.target,
        )

    if not result.success:
        logger.error("[Route] test_generator falhou: %s", result.error)
        raise HTTPException(
            status_code=500,
            detail=f"Falha ao gerar testes: {result.error}",
        )

    return result
