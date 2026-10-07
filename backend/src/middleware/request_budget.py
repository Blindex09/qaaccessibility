"""Todo pedido HTTP roda dentro de um orçamento de progresso (regra 8).

O orçamento carrega o limite de tokens que a pessoa escolheu nas Configurações, então ele vale
para qualquer programa que use o sistema por fora do chat (CI, scripts, outras IAs) do mesmo
jeito que vale no chat. É um middleware ASGI puro: o orçamento fica visível para o endpoint e
também durante respostas em streaming.
"""

import json
import logging

from starlette.types import ASGIApp, Receive, Scope, Send

from backend.src.services.execution_scope import execution_scope

logger = logging.getLogger(__name__)

_DEFAULT_WINDOW_SECONDS = 90.0


def _window_seconds() -> float:
    """Janela de silêncio inicial; qualquer configuração ilegível cai no padrão, nunca derruba o pedido."""
    try:
        from backend.src.config.settings import get_settings

        value = float(get_settings().agent_timeout_seconds)
        return value if value > 0 else _DEFAULT_WINDOW_SECONDS
    except Exception:
        return _DEFAULT_WINDOW_SECONDS


class RequestBudgetMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        with execution_scope(_window_seconds()) as budget:
            try:
                await self.app(scope, receive, send)
            finally:
                summary = budget.cost_summary()
                if summary["calls"]:
                    logger.info(
                        "[Custo] %s %s %s", scope.get("method", ""), scope.get("path", ""),
                        json.dumps(summary, ensure_ascii=False),
                    )
