"""ASGI entrypoint for uvicorn: ``weir.api.main:app``."""

from __future__ import annotations

from weir.api.factory import create_app

app = create_app()
