"""FastAPI application factory."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette import status

from mediamop import __version__
from mediamop.api.router import build_v1_router
from mediamop.core.config import MediaMopSettings
from mediamop.core.lifespan import lifespan
from mediamop.platform.health import health_router
from mediamop.platform.readiness import readiness_router
from mediamop.platform.http.request_context import RequestContextMiddleware
from mediamop.platform.http.security_headers import SecurityHeadersMiddleware
from mediamop.platform.metrics.router import router as metrics_router


def _web_dist_root() -> Path | None:
    raw = (os.environ.get("MEDIAMOP_WEB_DIST") or "").strip()
    if not raw:
        return None
    root = Path(raw).expanduser().resolve()
    if not root.is_dir() or not (root / "index.html").is_file():
        return None
    return root


def _index_no_cache_headers() -> dict[str, str]:
    return {
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Pragma": "no-cache",
        "Expires": "0",
    }


def _serve_index_with_no_cache(application: FastAPI) -> None:
    """Serve index.html with cache-busting headers.

    StaticFiles does not support per-file headers, so intercept index.html
    directly. Hashed JS/CSS/static assets remain served by StaticFiles.
    """

    @application.get("/", include_in_schema=False)
    @application.get("/index.html", include_in_schema=False)
    def _index() -> FileResponse:
        root = _web_dist_root()
        if root is None:
            raise StarletteHTTPException(status_code=status.HTTP_404_NOT_FOUND)
        return FileResponse(
            root / "index.html",
            media_type="text/html",
            headers=_index_no_cache_headers(),
        )


def _mount_web_spa_if_configured(application: FastAPI) -> None:
    """Serve the Vite production bundle from disk when ``MEDIAMOP_WEB_DIST`` is set."""
    root = _web_dist_root()
    if root is None:
        return
    application.mount("/", StaticFiles(directory=str(root), html=True), name="web")


def _is_browser_document_request(request: Request) -> bool:
    accept = (request.headers.get("accept") or "").lower()
    if "text/html" in accept:
        return True
    sec_fetch_dest = (request.headers.get("sec-fetch-dest") or "").lower()
    return sec_fetch_dest == "document"


def _is_spa_history_404(request: Request, exc: StarletteHTTPException) -> bool:
    """Serve the React shell for browser refreshes on client-side routes.

    FastAPI still owns JSON/API routes and missing static assets. We only convert
    document-style GET/HEAD 404s without a file suffix into ``index.html``.
    """

    if exc.status_code != status.HTTP_404_NOT_FOUND or request.method not in {"GET", "HEAD"}:
        return False
    if not _is_browser_document_request(request):
        return False
    path = request.url.path
    if path.startswith(("/api", "/health", "/ready", "/metrics")):
        return False
    if Path(path).suffix:
        return False
    return _web_dist_root() is not None


def _is_upgrade_browser_landing_404(request: Request, exc: StarletteHTTPException) -> bool:
    """Redirect stale/legacy in-app-upgrade browser landings back to the SPA.

    Older installed builds can leave the browser on an API-ish upgrade URL while the
    app restarts. Without this guard FastAPI returns ``{"detail":"Not Found"}``,
    which is technically correct but useless for a user during an upgrade.
    """

    if exc.status_code != status.HTTP_404_NOT_FOUND or request.method != "GET":
        return False
    path = request.url.path.lower()
    if not path.startswith("/api"):
        return False
    return any(token in path for token in ("update-now", "upgrade-now", "upgrade"))


def create_app() -> FastAPI:
    settings = MediaMopSettings.load()
    application = FastAPI(
        title="MediaMop API",
        version=__version__,
        lifespan=lifespan,
    )

    application.add_middleware(SecurityHeadersMiddleware)
    application.add_middleware(RequestContextMiddleware)

    @application.exception_handler(StarletteHTTPException)
    async def _friendly_upgrade_landing_handler(request: Request, exc: StarletteHTTPException):
        if _is_upgrade_browser_landing_404(request, exc):
            return RedirectResponse(url="/settings", status_code=status.HTTP_303_SEE_OTHER)
        if _is_spa_history_404(request, exc):
            root = _web_dist_root()
            if root is not None:
                return FileResponse(
                    root / "index.html",
                    media_type="text/html",
                    headers=_index_no_cache_headers(),
                )
        return await http_exception_handler(request, exc)

    if settings.cors_origins:
        application.add_middleware(
            CORSMiddleware,
            allow_origins=list(settings.cors_origins),
            allow_credentials=True,
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["Content-Type", "Accept", "X-CSRF-Token"],
        )

    application.include_router(health_router)
    application.include_router(readiness_router)
    application.include_router(metrics_router)
    application.include_router(build_v1_router())
    _serve_index_with_no_cache(application)
    _mount_web_spa_if_configured(application)

    return application
