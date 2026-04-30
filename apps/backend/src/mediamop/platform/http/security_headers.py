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

# API baseline: no scripts, no frames, no base-tag surprises, no forms to third parties.
_API_CSP = (
    "default-src 'none'; "
    "base-uri 'none'; "
    "frame-ancestors 'none'; "
    "form-action 'none'"
)

# HTML baseline for the bundled SPA shell/static assets.
# Keep this narrow but allow first-party JS/CSS plus Google Fonts used by index.html.
_HTML_CSP = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' https://fonts.googleapis.com; "
    "font-src 'self' https://fonts.gstatic.com data:; "
    "img-src 'self' data: blob:; "
    "connect-src 'self'; "
    "base-uri 'none'; "
    "frame-ancestors 'none'; "
    "form-action 'self'"
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Attach explicit security headers to every HTTP response."""

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        settings: MediaMopSettings | None = getattr(request.app.state, "settings", None)
        content_type = (response.headers.get("content-type") or "").lower()

        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        if content_type.startswith("text/html"):
            response.headers.setdefault("Content-Security-Policy", _HTML_CSP)
        else:
            response.headers.setdefault("Content-Security-Policy", _API_CSP)
        response.headers.setdefault("X-Frame-Options", "DENY")
        # API responses can include filesystem paths, credentials metadata, and operator settings.
        path = request.url.path
        if path.startswith("/api/v1") or path in {"/health", "/ready", "/readiness", "/metrics"}:
            response.headers.setdefault("Cache-Control", "no-store, private")

        if settings is not None and settings.security_enable_hsts:
            response.headers.setdefault(
                "Strict-Transport-Security",
                "max-age=31536000; includeSubDomains",
            )
        return response
