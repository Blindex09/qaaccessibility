import logging

from fastapi import Request

from backend.src.security.rate_limiter import check_rate_limit

logger = logging.getLogger(__name__)


def rate_limit_dependency(request: Request) -> None:
    """Dependencia FastAPI que aplica rate limiting por IP."""
    check_rate_limit(request)
