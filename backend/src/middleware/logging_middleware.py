import logging
import time

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        start = time.perf_counter()
        logger.info("[HTTP] %s %s", request.method, request.url.path)

        response: Response = await call_next(request)

        elapsed = (time.perf_counter() - start) * 1000
        logger.info(
            "[HTTP] %s %s -> %d (%.1fms)",
            request.method,
            request.url.path,
            response.status_code,
            elapsed,
        )
        return response
