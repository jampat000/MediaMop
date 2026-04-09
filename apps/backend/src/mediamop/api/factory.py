"""FastAPI application factory."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from mediamop import __version__
from mediamop.api.router import build_v1_router
from mediamop.core.config import MediaMopSettings
from mediamop.core.lifespan import lifespan
from mediamop.platform.health import health_router
from mediamop.platform.http.security_headers import SecurityHeadersMiddleware


def create_app() -> FastAPI:
    settings = MediaMopSettings.load()
    application = FastAPI(
        title="MediaMop API",
        version=__version__,
        lifespan=lifespan,
    )

    application.add_middleware(SecurityHeadersMiddleware)
    if settings.cors_origins:
        application.add_middleware(
            CORSMiddleware,
            allow_origins=list(settings.cors_origins),
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    application.include_router(health_router)
    application.include_router(build_v1_router())

    return application
