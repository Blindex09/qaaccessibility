"""Security headers middleware.

Adds standard security headers to every response following OWASP recommendations.
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Inject security headers into all HTTP responses."""

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        # Prevent MIME-type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"

        # Enable browser XSS filter (legacy, harmless to keep alongside CSP)
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # The preview endpoint intentionally renders in an iframe embedded by the
        # frontend (a different origin in local dev). It sets its own CSP with
        # frame-ancestors pointing to the frontend origin; do not override it with
        # DENY or a restrictive frame-ancestors here.
        is_preview_render = request.url.path.startswith("/preview/render/")
        if not is_preview_render:
            # Prevent clickjacking for every other route.
            response.headers["X-Frame-Options"] = "DENY"

        # Restrict resource loading to same-origin by default. A route that renders
        # untrusted third-party content (e.g. routes/preview.py, which serves
        # user-analyzed HTML on this same origin) sets its own, stricter CSP on the
        # Response before this middleware runs -- respect it instead of overwriting,
        # since this app's own domain is not a safe execution context for that content.
        if "content-security-policy" not in response.headers and not is_preview_render:
            response.headers["Content-Security-Policy"] = "default-src 'self'; frame-ancestors 'none'"

        # Prevent leaking referrer data to external sites
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Opt out of FLoC / Topics tracking, and lock down sensor/device APIs this
        # app never uses.
        response.headers["Permissions-Policy"] = (
            "interest-cohort=(), camera=(), microphone=(), geolocation=()"
        )

        # Force HTTPS on repeat visits (no-op over plain HTTP, e.g. local dev).
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

        # Isolate this origin from cross-origin windows/documents -- relevant given
        # routes/preview.py renders untrusted HTML on this same origin.
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        response.headers["Cross-Origin-Resource-Policy"] = "same-origin"

        return response
