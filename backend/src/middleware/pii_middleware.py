"""PII redaction middleware.

Scans JSON response bodies for personally identifiable information (PII)
and replaces detected patterns with [REDACTED] before returning to the client.
"""

import json
import logging

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from backend.src.security.pii_guard import contains_pii, redact_pii

logger = logging.getLogger(__name__)


class PIIRedactionMiddleware(BaseHTTPMiddleware):
    """Automatically redact PII from JSON response bodies."""

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        # Only process JSON responses
        content_type = response.headers.get("content-type", "")
        if "application/json" not in content_type:
            return response

        # Read the response body
        body_bytes = b""
        async for chunk in response.body_iterator:
            if isinstance(chunk, str):
                body_bytes += chunk.encode("utf-8")
            else:
                body_bytes += chunk

        body_text = body_bytes.decode("utf-8")

        # Check and redact PII if found
        if contains_pii(body_text):
            logger.warning("[PIIMiddleware] PII detected in response — redacting")
            try:
                data = json.loads(body_text)
                redacted_text = json.dumps(_redact_recursive(data), ensure_ascii=False)
                body_bytes = redacted_text.encode("utf-8")
            except (json.JSONDecodeError, TypeError):
                # Fallback: redact the raw text
                body_bytes = redact_pii(body_text).encode("utf-8")

        return Response(
            content=body_bytes,
            status_code=response.status_code,
            headers=dict(response.headers),
            media_type=response.media_type,
        )


def _redact_recursive(obj):
    """Walk a JSON-serializable structure and redact PII in string values."""
    if isinstance(obj, str):
        return redact_pii(obj)
    if isinstance(obj, dict):
        return {k: _redact_recursive(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_redact_recursive(item) for item in obj]
    return obj
