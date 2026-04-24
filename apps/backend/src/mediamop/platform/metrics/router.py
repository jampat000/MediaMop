"""Prometheus-style runtime metrics endpoint."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

from mediamop.platform.metrics.service import render_prometheus_metrics

router = APIRouter(include_in_schema=False)


@router.get("/metrics", response_class=PlainTextResponse)
def get_metrics() -> PlainTextResponse:
    return PlainTextResponse(render_prometheus_metrics(), media_type="text/plain; version=0.0.4")
