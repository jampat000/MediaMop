"""Manual enqueue for ``refiner.supplied_payload_evaluation.v1`` (``refiner_jobs`` only)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class RefinerSuppliedPayloadEvaluationManualEnqueueIn(BaseModel):
    """Operator-triggered enqueue (singleton dedupe; returns existing row when present)."""

    csrf_token: str = Field(..., min_length=1)


class RefinerSuppliedPayloadEvaluationManualEnqueueOut(BaseModel):
    ok: bool = True
    job_id: int
    dedupe_key: str
    job_kind: str
