"""ASGI entrypoint for uvicorn: ``mediamop.api.main:app``."""

from __future__ import annotations

from mediamop.api.factory import create_app

app = create_app()
