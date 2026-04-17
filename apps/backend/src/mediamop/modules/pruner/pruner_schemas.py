"""Pydantic schemas for Pruner HTTP APIs."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from mediamop.modules.pruner.pruner_constants import (
    MEDIA_SCOPE_MOVIES,
    MEDIA_SCOPE_TV,
    RULE_FAMILY_WATCHED_MOVIES_REPORTED,
    RULE_FAMILY_WATCHED_TV_REPORTED,
)

PrunerProviderWire = Literal["emby", "jellyfin", "plex"]


class PrunerScopeSummaryOut(BaseModel):
    media_scope: str
    missing_primary_media_reported_enabled: bool
    never_played_stale_reported_enabled: bool = False
    never_played_min_age_days: int = 90
    watched_tv_reported_enabled: bool = False
    watched_movies_reported_enabled: bool = False
    preview_max_items: int
    scheduled_preview_enabled: bool = False
    scheduled_preview_interval_seconds: int = 3600
    last_scheduled_preview_enqueued_at: datetime | None = None
    last_preview_run_uuid: str | None = None
    last_preview_at: datetime | None = None
    last_preview_candidate_count: int | None = None
    last_preview_outcome: str | None = None
    last_preview_error: str | None = None


class PrunerServerInstanceOut(BaseModel):
    id: int
    provider: str
    display_name: str
    base_url: str
    enabled: bool
    last_connection_test_at: datetime | None = None
    last_connection_test_ok: bool | None = None
    last_connection_test_detail: str | None = None
    scopes: list[PrunerScopeSummaryOut] = Field(default_factory=list)


class PrunerServerInstanceCreateIn(BaseModel):
    provider: PrunerProviderWire
    display_name: str = Field(..., min_length=1, max_length=200)
    base_url: str = Field(..., min_length=1, max_length=512)
    credentials: dict[str, str] = Field(
        ...,
        description="Provider-specific secret map (e.g. api_key for Emby/Jellyfin; auth_token for Plex).",
    )


class PrunerServerInstancePatchIn(BaseModel):
    display_name: str | None = Field(None, min_length=1, max_length=200)
    base_url: str | None = Field(None, min_length=1, max_length=512)
    enabled: bool | None = None
    credentials: dict[str, str] | None = None


class PrunerScopePatchIn(BaseModel):
    missing_primary_media_reported_enabled: bool | None = None
    never_played_stale_reported_enabled: bool | None = None
    never_played_min_age_days: int | None = Field(None, ge=7, le=3650)
    watched_tv_reported_enabled: bool | None = None
    watched_movies_reported_enabled: bool | None = None
    preview_max_items: int | None = Field(None, ge=1, le=5000)
    scheduled_preview_enabled: bool | None = None
    scheduled_preview_interval_seconds: int | None = Field(None, ge=60, le=86_400)


class PrunerEnqueueOut(BaseModel):
    pruner_job_id: int


PrunerPreviewRuleFamilyWire = Literal[
    "missing_primary_media_reported",
    "never_played_stale_reported",
    "watched_tv_reported",
    "watched_movies_reported",
]


class PrunerPreviewEnqueueIn(BaseModel):
    media_scope: Literal["tv", "movies"]
    rule_family_id: PrunerPreviewRuleFamilyWire = "missing_primary_media_reported"
    csrf_token: str = Field(..., min_length=1)

    @model_validator(mode="after")
    def _rule_family_requires_matching_tab(self) -> PrunerPreviewEnqueueIn:
        if self.rule_family_id == RULE_FAMILY_WATCHED_TV_REPORTED and self.media_scope != MEDIA_SCOPE_TV:
            msg = "watched_tv_reported preview is only available for the TV tab (media_scope must be tv)."
            raise ValueError(msg)
        if self.rule_family_id == RULE_FAMILY_WATCHED_MOVIES_REPORTED and self.media_scope != MEDIA_SCOPE_MOVIES:
            msg = "watched_movies_reported preview is only available for the Movies tab (media_scope must be movies)."
            raise ValueError(msg)
        return self


class PrunerConnectionTestIn(BaseModel):
    csrf_token: str = Field(..., min_length=1)


class PrunerServerInstanceCreateHttpIn(PrunerServerInstanceCreateIn):
    csrf_token: str = Field(..., min_length=1)


class PrunerServerInstancePatchHttpIn(PrunerServerInstancePatchIn):
    csrf_token: str = Field(..., min_length=1)

    @model_validator(mode="after")
    def _at_least_one_field(self) -> PrunerServerInstancePatchHttpIn:
        if (
            self.display_name is None
            and self.base_url is None
            and self.enabled is None
            and self.credentials is None
        ):
            msg = "At least one of display_name, base_url, enabled, or credentials must be provided."
            raise ValueError(msg)
        return self


class PrunerScopePatchHttpIn(PrunerScopePatchIn):
    csrf_token: str = Field(..., min_length=1)

    @model_validator(mode="after")
    def _at_least_one_scope_field(self) -> PrunerScopePatchHttpIn:
        if (
            self.missing_primary_media_reported_enabled is None
            and self.never_played_stale_reported_enabled is None
            and self.never_played_min_age_days is None
            and self.watched_tv_reported_enabled is None
            and self.watched_movies_reported_enabled is None
            and self.preview_max_items is None
            and self.scheduled_preview_enabled is None
            and self.scheduled_preview_interval_seconds is None
        ):
            msg = (
                "At least one of missing_primary_media_reported_enabled, never_played_stale_reported_enabled, "
                "never_played_min_age_days, watched_tv_reported_enabled, watched_movies_reported_enabled, "
                "preview_max_items, scheduled_preview_enabled, or scheduled_preview_interval_seconds must be provided."
            )
            raise ValueError(msg)
        return self


class PrunerJobsInspectionRow(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    dedupe_key: str
    job_kind: str
    status: str
    payload_json: str | None
    last_error: str | None
    updated_at: datetime


class PrunerJobsInspectionOut(BaseModel):
    jobs: list[PrunerJobsInspectionRow]
    default_recent_slice: bool


class PrunerPreviewRunOut(BaseModel):
    model_config = {"from_attributes": True}

    preview_run_id: str
    server_instance_id: int
    media_scope: str
    rule_family_id: str
    candidate_count: int
    truncated: bool
    outcome: str
    unsupported_detail: str | None
    error_message: str | None
    created_at: datetime
    candidates_json: str


class PrunerApplyEligibilityOut(BaseModel):
    """Read-only: whether apply can be enqueued for this snapshot (not a second dry run)."""

    eligible: bool
    reasons: list[str] = Field(default_factory=list)
    apply_feature_enabled: bool
    preview_run_id: str
    server_instance_id: int
    media_scope: str
    provider: str
    display_name: str
    preview_created_at: datetime | None = None
    candidate_count: int = 0
    preview_outcome: str = ""
    rule_family_id: str = ""
    apply_operator_label: str = ""


class PrunerApplyHttpIn(BaseModel):
    csrf_token: str = Field(..., min_length=1)


class PrunerPlexLiveEligibilityOut(BaseModel):
    """Read-only: retired Plex live-removal path; always ineligible with explanatory reasons."""

    eligible: bool
    reasons: list[str] = Field(default_factory=list)
    apply_feature_enabled: bool
    plex_live_feature_enabled: bool
    server_instance_id: int
    media_scope: str
    provider: str
    display_name: str
    rule_family_id: str
    rule_enabled: bool
    live_max_items_cap: int = Field(
        ...,
        description=(
            "Historical field name: Plex missing-primary preview collects at most this many leaf rows per run "
            "(min per-scope preview cap, process ceiling MEDIAMOP_PRUNER_PLEX_LIVE_ABS_MAX_ITEMS, and 5k clamp)."
        ),
    )
    required_confirmation_phrase: str


class PrunerPreviewRunListItemOut(BaseModel):
    """Preview run metadata without ``candidates_json`` (list endpoint for operator history)."""

    model_config = {"from_attributes": True}

    preview_run_id: str
    server_instance_id: int
    media_scope: str
    rule_family_id: str
    pruner_job_id: int | None = None
    candidate_count: int
    truncated: bool
    outcome: str
    unsupported_detail: str | None
    error_message: str | None
    created_at: datetime
