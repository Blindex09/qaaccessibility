import logging
import time
from collections import defaultdict

from fastapi import HTTPException, Request

logger = logging.getLogger(__name__)

# Janela de 60 segundos, max 30 requisicoes por IP
_WINDOW_SECONDS = 60
_MAX_REQUESTS = 30

_request_log: dict[str, list[float]] = defaultdict(list)


def _get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def check_rate_limit(request: Request) -> None:
    """Levanta HTTP 429 se o IP exceder o limite de requisicoes."""
    ip = _get_client_ip(request)
    now = time.time()
    window_start = now - _WINDOW_SECONDS

    # Remove timestamps fora da janela
    _request_log[ip] = [t for t in _request_log[ip] if t > window_start]

    if len(_request_log[ip]) >= _MAX_REQUESTS:
        logger.warning("[RateLimiter] IP bloqueado: %s", ip)
        raise HTTPException(
            status_code=429,
            detail="Muitas requisicoes. Tente novamente em instantes.",
        )

    _request_log[ip].append(now)
