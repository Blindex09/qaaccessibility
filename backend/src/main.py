import hmac
import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.src.config.logging_config import configure_logging
from backend.src.config.settings import get_settings
from backend.src.middleware.logging_middleware import LoggingMiddleware
from backend.src.middleware.pii_middleware import PIIRedactionMiddleware
from backend.src.middleware.security_headers import SecurityHeadersMiddleware
from backend.src.routes.a2a_route import router as a2a_router
from backend.src.routes.analyze import router as analyze_router
from backend.src.routes.chat import router as chat_router
from backend.src.routes.checklist import router as checklist_router
from backend.src.routes.design_review_route import router as design_review_router
from backend.src.routes.export_xlsx import router as export_router
from backend.src.routes.fix import router as fix_router
from backend.src.routes.models_route import router as models_router
from backend.src.routes.preview import router as preview_router
from backend.src.routes.report import router as report_router
from backend.src.routes.screen_reader_route import router as screen_reader_router
from backend.src.routes.settings import router as settings_router
from backend.src.routes.tests_route import router as tests_router
from backend.src.routes.vpat_route import router as vpat_router
from backend.src.routes.webhook import router as webhook_router
from backend.src.services.config_drift import log_config_drift
from backend.src.services.telemetry import configure_telemetry

settings = get_settings()
if settings.backend_host not in {"127.0.0.1", "localhost", "::1"} and not settings.qa_api_token:
    raise RuntimeError("QA_API_TOKEN é obrigatório quando BACKEND_HOST não está restrito ao loopback.")
configure_logging(debug=settings.debug)
configure_telemetry()

logger = logging.getLogger(__name__)

# Configuration Drift Detection: acusa vars de override de endpoint (ex.:
# ANTHROPIC_BASE_URL) ativas no ambiente do processo mas nao declaradas em
# backend/.env -- runtime silenciosamente divergindo do .env documentado.
log_config_drift()

app = FastAPI(
    title="QA Accessibility API",
    description="Analisador de acessibilidade com IA — WCAG 2.2, WAI-ARIA, ADA 508",
    version="1.0.0",
)

# Middleware stack (Starlette LIFO: last added = outermost = first on request)
app.add_middleware(LoggingMiddleware)
app.add_middleware(PIIRedactionMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def require_api_token(request: Request, call_next):
    public_path = (
        request.url.path == "/health"
        or request.url.path.startswith("/webhook")
        or request.url.path.startswith("/.well-known")
        or request.url.path.startswith("/a2a")
    )
    expected = settings.qa_api_token
    if expected and not public_path:
        supplied = request.headers.get("X-QA-Accessibility-Token", "")
        if not hmac.compare_digest(supplied, expected):
            return JSONResponse(status_code=401, content={"detail": "Token de sessão inválido."})
    return await call_next(request)


app.include_router(analyze_router)
app.include_router(fix_router)
app.include_router(checklist_router)
app.include_router(report_router)
app.include_router(export_router)
# Agentes derivados de C:\agents — test_generator + vpat_reporter
app.include_router(tests_router)
app.include_router(vpat_router)
app.include_router(screen_reader_router)
app.include_router(design_review_router)
app.include_router(settings_router)
app.include_router(preview_router)

# Chat agentico com streaming (SSE) — AIAgent + tools de acessibilidade
app.include_router(chat_router)
# Catalogo de modelos (catalogo local) para o seletor de provider/modelo
app.include_router(models_router)
app.include_router(webhook_router)
app.include_router(a2a_router)


@app.get("/health")
async def health_check() -> dict:
    return {"status": "ok", "version": "1.0.0"}


logger.info("[App] QA Accessibility API inicializada")
