"""Readiness response models."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ReadinessStep(BaseModel):
    name: str = Field(..., description="Startup area checked by readiness.")
    status: str = Field(..., description="ready, starting, or failed.")
    detail: str = Field(..., description="Operator-readable status detail.")


class ReadinessWorkerOut(BaseModel):
    module: str
    expected_workers: int = Field(..., ge=0)
    active_workers: int = Field(..., ge=0)
    stale_workers: int = Field(..., ge=0)
    stopped_workers: int = Field(..., ge=0)
    status: str
    detail: str


class ReadinessResponse(BaseModel):
    ready: bool
    status: str
    startup_seconds: float
    steps: list[ReadinessStep]
    worker_health: list[ReadinessWorkerOut] = Field(default_factory=list)
