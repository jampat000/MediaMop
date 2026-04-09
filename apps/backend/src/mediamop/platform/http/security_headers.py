"""Browser-oriented security headers for API responses (Phase 6).

The backend is primarily JSON; CSP still applies if a response is ever rendered as a document.
Values are conservative and API-oriented (``default-src 'none'``).

HSTS is **off by default** and must only be enabled when **all** clients reach this app over HTTPS;
otherwise browsers may force HTTPS to hosts that do not serve TLS.
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from mediamop.core.config import MediaMopSettings

# API-only baseline: no scripts, no frames, no base-tag surprises, no forms to third parties.
_API_CSP = (
    "default-src 'none'; "
    "base-uri 'none'; "
    "frame-ancestors 'none'; "
    "form-action 'none'"
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Attach explicit security headers to every HTTP response."""

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        settings: MediaMopSettings | None = getattr(request.app.state, "settings", None)

        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Content-Security-Policy", _API_CSP)
        response.headers.setdefault("X-Frame-Options", "DENY")
        # Sensitive auth JSON should not be cached by shared intermediaries.
        path = request.url.path
        if path.startswith("/api/v1/auth"):
            response.headers.setdefault("Cache-Control", "no-store, private")

        if settings is not None and settings.security_enable_hsts:
            response.headers.setdefault(
                "Strict-Transport-Security",
                "max-age=31536000; includeSubDomains",
            )
        return response
