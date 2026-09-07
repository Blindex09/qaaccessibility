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

    Tenta BROWSERLESS_WS_URL no ambiente e cai para Chromium local headless
    quando a variável não existe ou o remoto falha. Se os dois não estiverem
    disponíveis, devolve `tree_captured=false` para não confundir falha de
    captura com página sem problemas.

    `interaction_steps` permite validar sequências declarativas de teclado e
    interação sem áudio; a árvore é recapturada após cada passo.

    """
    logger.info("[Route] POST /analyze/screen-reader -- url=%s", body.url)
    if body.interaction_steps:
        result = await verify_screen_reader_announcements(
            body.url,
            interaction_steps=body.interaction_steps,
        )
    else:
        result = await verify_screen_reader_announcements(body.url)
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
        tree_captured=result.tree_captured,
        not_verified_reason=result.not_verified_reason,
        interaction_steps=result.interaction_steps,
        interaction_browser_mode=result.interaction_browser_mode,
    )
