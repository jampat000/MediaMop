"""Manual enqueue for Refiner ``refiner.candidate_gate.v1`` (``refiner_jobs`` only)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class RefinerCandidateGateManualEnqueueIn(BaseModel):
    """Operator supplies a real release candidate; workers compare it to every connected manager.

    The candidate is described by the **library it belongs to**, not by the product that
    manages it: one Movies library may be served by several connections at once, and the
    gate asks all of them.
    """

    media_scope: Literal["movie", "tv"]
    release_title: str = Field(..., min_length=1, max_length=500)
    release_year: int | None = None
    output_path: str | None = Field(None, max_length=4000)
    entity_id: int | None = Field(
        None,
        description="The manager's own id for this movie or series, when matching without a path",
    )
    csrf_token: str = Field(..., min_length=1)


class RefinerCandidateGateManualEnqueueOut(BaseModel):
    ok: bool = True
    job_id: int
    dedupe_key: str
    job_kind: str
