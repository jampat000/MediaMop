"""Pydantic shapes for ``refiner_jobs`` inspection and pending cancel (Refiner lane only)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class RefinerJobInspectionRow(BaseModel):
    """One persisted Refiner durable job row (lifecycle from ``refiner_jobs`` only)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    dedupe_key: str
    job_kind: str
    status: str = Field(description="Persisted status value for this row.")
    attempt_count: int
    max_attempts: int
    lease_owner: str | None
    lease_expires_at: datetime | None
    last_error: str | None
    operator_message: str = Field(default="", description="Short plain-language explanation for the operator.")
    next_action: str = Field(default="", description="The next action an operator can take, or why none is needed.")
    technical_detail: str | None = Field(
        default=None,
        description="Technical diagnostic detail, kept secondary to the operator message.",
    )
    payload_json: str | None = None
    created_at: datetime
    updated_at: datetime


class RefinerJobsInspectionOut(BaseModel):
    """Bounded list of ``refiner_jobs`` rows, newest ``updated_at`` first."""

    model_config = ConfigDict(extra="forbid")

    jobs: list[RefinerJobInspectionRow]
    default_recent_slice: bool = Field(
        description=(
            "True when no ``status`` filter was applied: the newest rows across all statuses. "
            "False when one or more ``status`` query params narrowed the query."
        ),
    )


class RefinerJobCancelPendingIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    csrf_token: str = Field(..., min_length=1)


class RefinerJobCancelPendingOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: bool = True
    job_id: int
    status: str = Field(description="Always ``cancelled`` on success.")


class RefinerJobRecoverFinalizeFailedIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    csrf_token: str = Field(..., min_length=1)


class RefinerJobRecoverFinalizeFailedOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: bool = True
    job_id: int
    status: str = Field(description="Always ``completed`` on success.")
