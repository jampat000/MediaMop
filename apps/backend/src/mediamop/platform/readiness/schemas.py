"""Readiness response models."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ReadinessStep(BaseModel):
    name: str = Field(..., description="Startup area checked by readiness.")
    status: str = Field(..., description="ready, starting, or failed.")
    detail: str = Field(..., description="Operator-readable status detail.")


class ReadinessResponse(BaseModel):
    ready: bool
    status: str
    startup_seconds: float
    steps: list[ReadinessStep]
