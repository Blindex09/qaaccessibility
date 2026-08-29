import logging

from fastapi import APIRouter, Depends

from backend.src.security.dependencies import rate_limit_dependency
from backend.src.services.screen_reader_verification import verify_screen_reader_announcements
from backend.src.shared.models import (
    ScreenReaderFindingResponse,
    ScreenReaderVerificationRequest,
    ScreenReaderVerificationResponse,
)

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Rota: /analyze/screen-reader
#
# Verifica anuncios de leitor de tela cruzando a arvore de acessibilidade REAL
# computada pelo motor do navegador (Chromium/CDP -- a mesma API que
# NVDA/JAWS/Narrator consultam no Windows) contra regras deterministicas de
# nome acessivel ausente ou generico. Ver services/screen_reader_verification.py
# para o porque desta abordagem em vez de captura de fala do NVDA (sem API
# oficial pra isso).
# ─────────────────────────────────────────────────────────────────────────────

router = APIRouter(
    prefix="/analyze",
    tags=["screen-reader"],
    dependencies=[Depends(rate_limit_dependency)],
)


@router.post("/screen-reader", response_model=ScreenReaderVerificationResponse)
async def verify_screen_reader(body: ScreenReaderVerificationRequest) -> ScreenReaderVerificationResponse:
    """
    Verifica os anuncios de leitor de tela de uma URL.

    Diferente de /analyze (que estima problemas a partir do HTML bruto via
    LLM), este endpoint confirma o achado direto na arvore de acessibilidade
    real computada pelo proprio motor do navegador -- um no interativo sem
    nome, ou com nome generico, e uma violacao que qualquer leitor de tela
    real (NVDA, JAWS, Narrator) tambem veria.

    Requer BROWSERLESS_WS_URL configurado no ambiente; sem isso, devolve
    `total_interactive_nodes=0` e `findings=[]` (nunca falha a chamada).

    `speak_via_nvda=true`: se o NVDA real estiver rodando na maquina do
    servidor, le os achados em voz alta para confirmacao humana (mesmo canal
    de fala ja usado pela ferramenta de chat `nvda_speak`).
    """
    logger.info("[Route] POST /analyze/screen-reader -- url=%s", body.url)
    result = await verify_screen_reader_announcements(body.url, speak_via_nvda=body.speak_via_nvda)
    return ScreenReaderVerificationResponse(
        url=result.url,
        total_interactive_nodes=result.total_interactive_nodes,
        findings=[
            ScreenReaderFindingResponse(
                role=f.role,
                path=f.path,
                problem=f.problem,
                severity=f.severity,
                announcement_preview=f.announcement_preview,
            )
            for f in result.findings
        ],
        nvda_running=result.nvda_running,
        spoken_findings=result.spoken_findings,
    )
