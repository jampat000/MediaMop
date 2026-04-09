"""Health check response models."""

from __future__ import annotations

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Minimal liveness payload for load balancers and ops."""

    status: str = Field(..., description="Application liveness indicator.")
