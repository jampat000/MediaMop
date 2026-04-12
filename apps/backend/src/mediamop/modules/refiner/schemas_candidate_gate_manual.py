"""Manual enqueue for Refiner ``refiner.candidate_gate.v1`` (``refiner_jobs`` only)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class RefinerCandidateGateManualEnqueueIn(BaseModel):
    """Operator supplies a real release candidate; workers compare it to the live download queue."""

    target: Literal["radarr", "sonarr"]
    release_title: str = Field(..., min_length=1, max_length=500)
    release_year: int | None = None
    output_path: str | None = Field(None, max_length=4000)
    movie_id: int | None = Field(None, description="Radarr movie id when matching without path")
    series_id: int | None = Field(None, description="Sonarr series id when matching without path")
    csrf_token: str = Field(..., min_length=1)

    @model_validator(mode="after")
    def ids_match_target(self):
        if self.target == "radarr" and self.series_id is not None:
            msg = "series_id applies only when target is sonarr"
            raise ValueError(msg)
        if self.target == "sonarr" and self.movie_id is not None:
            msg = "movie_id applies only when target is radarr"
            raise ValueError(msg)
        return self


class RefinerCandidateGateManualEnqueueOut(BaseModel):
    ok: bool = True
    job_id: int
    dedupe_key: str
    job_kind: str
