"""Pydantic schemas for Pruner HTTP APIs."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel, Field, field_validator, model_validator

from mediamop.modules.pruner.pruner_constants import (
    MEDIA_SCOPE_MOVIES,
    MEDIA_SCOPE_TV,
    PRUNER_PREVIEW_YEAR_FILTER_MAX,
    PRUNER_PREVIEW_YEAR_FILTER_MIN,
    RULE_FAMILY_UNWATCHED_MOVIE_STALE_REPORTED,
    RULE_FAMILY_WATCHED_MOVIE_LOW_RATING_REPORTED,
    RULE_FAMILY_WATCHED_MOVIES_REPORTED,
    RULE_FAMILY_WATCHED_TV_REPORTED,
)
from mediamop.modules.pruner.pruner_genre_filters import normalized_genre_filter_tokens
from mediamop.modules.pruner.pruner_people_filters import (
    normalized_people_filter_tokens,
    validate_preview_people_roles_list,
)

PrunerProviderWire = Literal["emby", "jellyfin", "plex"]


class PrunerScopeSummaryOut(BaseModel):
    media_scope: str
    missing_primary_media_reported_enabled: bool
    never_played_stale_reported_enabled: bool = False
    never_played_min_age_days: int = 90
    watched_tv_reported_enabled: bool = False
    watched_movies_reported_enabled: bool = False
    watched_movie_low_rating_reported_enabled: bool = False
    watched_movie_low_rating_max_jellyfin_emby_community_rating: float = 4.0
    watched_movie_low_rating_max_plex_audience_rating: float = 4.0
    unwatched_movie_stale_reported_enabled: bool = False
    unwatched_movie_stale_min_age_days: int = 90
    preview_max_items: int
    preview_include_genres: list[str] = Field(
        default_factory=list,
        description=(
            "Optional genre names (per tab) that narrow preview collection only. Empty means no filter. "
            "A successful preview with zero candidates can mean no items matched the rule plus filters — "
            "not necessarily a clean library."
        ),
    )
    preview_include_people: list[str] = Field(
        default_factory=list,
        description=(
            "Optional person display names (per tab) that narrow preview collection only — full-name tokens, "
            "case-insensitive exact match against provider-reported names. Empty means no filter. "
            "Apply still uses only the frozen snapshot; it does not re-apply people filters."
        ),
    )
    preview_include_people_roles: list[str] = Field(
        default_factory=list,
        description=(
            "Which credit roles count toward people-name matching for preview narrowing on this tab. "
            "Jellyfin/Emby match ``People[].Name`` when ``People[].Type`` maps to a selected role. "
            "Plex uses Role / Director / Writer tags on allLeaves; producer and guest_star are ignored on Plex. "
            "When empty, names match against all credits the provider exposes for this rule (all People on JF/Emby; "
            "Role, Director, and Writer tags on Plex)."
        ),
    )
    preview_year_min: int | None = Field(
        default=None,
        description=(
            "Optional inclusive minimum **production / release year** for preview narrowing only "
            f"({PRUNER_PREVIEW_YEAR_FILTER_MIN}–{PRUNER_PREVIEW_YEAR_FILTER_MAX}). "
            "Jellyfin/Emby use Items ``ProductionYear``; Plex missing-primary uses leaf ``year`` when present. "
            "Items with no year never match when any year bound is set."
        ),
    )
    preview_year_max: int | None = Field(
        default=None,
        description=(
            "Optional inclusive maximum year for preview narrowing (same semantics as ``preview_year_min``)."
        ),
    )
    preview_include_studios: list[str] = Field(
        default_factory=list,
        description=(
            "Optional studio name tokens (per tab) that narrow preview only — exact normalized match against "
            "Jellyfin/Emby ``Studios`` names or Plex ``Studio`` tags on the same leaf rows as other preview filters. "
            "This is **not** a separate “network” filter."
        ),
    )
    preview_include_collections: list[str] = Field(
        default_factory=list,
        description=(
            "Optional collection name tokens for preview narrowing. **Plex missing-primary only** in this slice "
            "(``Collection`` tags on ``allLeaves`` metadata). Jellyfin/Emby Items rows used here do not expose "
            "library collection membership without extra API calls, so this list is ignored on those providers."
        ),
    )
    scheduled_preview_enabled: bool = False
    scheduled_preview_interval_seconds: int = 3600
    scheduled_preview_hours_limited: bool = False
    scheduled_preview_days: str = ""
    scheduled_preview_start: str = "00:00"
    scheduled_preview_end: str = "23:59"
    last_scheduled_preview_enqueued_at: datetime | None = None
    auto_apply_enabled: bool = False
    max_deletes_per_run: int = 50
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


class PrunerStudiosOut(BaseModel):
    studios: list[str] = Field(default_factory=list)


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
    watched_movie_low_rating_reported_enabled: bool | None = None
    watched_movie_low_rating_max_jellyfin_emby_community_rating: float | None = Field(None, ge=0, le=10)
    watched_movie_low_rating_max_plex_audience_rating: float | None = Field(None, ge=0, le=10)
    unwatched_movie_stale_reported_enabled: bool | None = None
    unwatched_movie_stale_min_age_days: int | None = Field(None, ge=7, le=3650)
    preview_max_items: int | None = Field(None, ge=1, le=5000)
    preview_include_genres: list[str] | None = Field(
        default=None,
        description="Replace per-tab genre include list; omit field to leave unchanged.",
    )
    preview_include_people: list[str] | None = Field(
        default=None,
        description="Replace per-tab people-name include list; omit field to leave unchanged.",
    )
    preview_include_people_roles: list[str] | None = Field(
        default=None,
        description="Replace per-tab people credit roles for preview narrowing; omit field to leave unchanged.",
    )
    preview_year_min: int | None = Field(
        default=None,
        ge=PRUNER_PREVIEW_YEAR_FILTER_MIN,
        le=PRUNER_PREVIEW_YEAR_FILTER_MAX,
    )
    preview_year_max: int | None = Field(
        default=None,
        ge=PRUNER_PREVIEW_YEAR_FILTER_MIN,
        le=PRUNER_PREVIEW_YEAR_FILTER_MAX,
    )
    preview_include_studios: list[str] | None = Field(
        default=None,
        description="Replace per-tab studio include list; omit field to leave unchanged.",
    )
    preview_include_collections: list[str] | None = Field(
        default=None,
        description="Replace per-tab collection include list (Plex missing-primary only); omit to leave unchanged.",
    )
    scheduled_preview_enabled: bool | None = None
    scheduled_preview_interval_seconds: int | None = Field(None, ge=60, le=86_400)
    scheduled_preview_hours_limited: bool | None = None
    scheduled_preview_days: str | None = Field(default=None, max_length=200)
    scheduled_preview_start: str | None = Field(default=None, max_length=5)
    scheduled_preview_end: str | None = Field(default=None, max_length=5)
    auto_apply_enabled: bool | None = None
    max_deletes_per_run: int | None = Field(None, ge=1, le=5000)

    @field_validator("preview_include_genres", mode="before")
    @classmethod
    def _validate_preview_genres(cls, v: object) -> list[str] | None:
        if v is None:
            return None
        if not isinstance(v, list):
            msg = "preview_include_genres must be a list of strings or null"
            raise ValueError(msg)
        return normalized_genre_filter_tokens([str(x) for x in v if x is not None])

    @field_validator("preview_include_people", mode="before")
    @classmethod
    def _validate_preview_people(cls, v: object) -> list[str] | None:
        if v is None:
            return None
        if not isinstance(v, list):
            msg = "preview_include_people must be a list of strings or null"
            raise ValueError(msg)
        return normalized_people_filter_tokens([str(x) for x in v if x is not None])

    @field_validator("preview_include_people_roles", mode="before")
    @classmethod
    def _validate_preview_people_roles(cls, v: object) -> list[str] | None:
        if v is None:
            return None
        if not isinstance(v, list):
            msg = "preview_include_people_roles must be a list of strings or null"
            raise ValueError(msg)
        return validate_preview_people_roles_list(v)

    @field_validator("preview_include_studios", mode="before")
    @classmethod
    def _validate_preview_studios(cls, v: object) -> list[str] | None:
        if v is None:
            return None
        if not isinstance(v, list):
            msg = "preview_include_studios must be a list of strings or null"
            raise ValueError(msg)
        return normalized_genre_filter_tokens([str(x) for x in v if x is not None])

    @field_validator("preview_include_collections", mode="before")
    @classmethod
    def _validate_preview_collections(cls, v: object) -> list[str] | None:
        if v is None:
            return None
        if not isinstance(v, list):
            msg = "preview_include_collections must be a list of strings or null"
            raise ValueError(msg)
        return normalized_genre_filter_tokens([str(x) for x in v if x is not None])

    @model_validator(mode="after")
    def _preview_year_bounds_order(self) -> Self:
        if self.preview_year_min is not None and self.preview_year_max is not None:
            if self.preview_year_min > self.preview_year_max:
                msg = "preview_year_min must be less than or equal to preview_year_max when both are set."
                raise ValueError(msg)
        return self


class PrunerEnqueueOut(BaseModel):
    pruner_job_id: int


PrunerPreviewRuleFamilyWire = Literal[
    "missing_primary_media_reported",
    "never_played_stale_reported",
    "watched_tv_reported",
    "watched_movies_reported",
    "watched_movie_low_rating_reported",
    "unwatched_movie_stale_reported",
    "genre_match_reported",
    "studio_match_reported",
    "people_match_reported",
    "year_range_match_reported",
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
        if self.rule_family_id == RULE_FAMILY_WATCHED_MOVIE_LOW_RATING_REPORTED and self.media_scope != MEDIA_SCOPE_MOVIES:
            msg = (
                "watched_movie_low_rating_reported preview is only available for the Movies tab "
                "(media_scope must be movies)."
            )
            raise ValueError(msg)
        if self.rule_family_id == RULE_FAMILY_UNWATCHED_MOVIE_STALE_REPORTED and self.media_scope != MEDIA_SCOPE_MOVIES:
            msg = (
                "unwatched_movie_stale_reported preview is only available for the Movies tab "
                "(media_scope must be movies)."
            )
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
            and self.watched_movie_low_rating_reported_enabled is None
            and self.watched_movie_low_rating_max_jellyfin_emby_community_rating is None
            and self.watched_movie_low_rating_max_plex_audience_rating is None
            and self.unwatched_movie_stale_reported_enabled is None
            and self.unwatched_movie_stale_min_age_days is None
            and self.preview_max_items is None
            and self.preview_include_genres is None
            and self.preview_include_people is None
            and self.preview_include_people_roles is None
            and self.preview_year_min is None
            and self.preview_year_max is None
            and self.preview_include_studios is None
            and self.preview_include_collections is None
            and self.scheduled_preview_enabled is None
            and self.scheduled_preview_interval_seconds is None
            and self.scheduled_preview_hours_limited is None
            and self.scheduled_preview_days is None
            and self.scheduled_preview_start is None
            and self.scheduled_preview_end is None
            and self.auto_apply_enabled is None
            and self.max_deletes_per_run is None
        ):
            msg = (
                "At least one of missing_primary_media_reported_enabled, never_played_stale_reported_enabled, "
                "never_played_min_age_days, watched_tv_reported_enabled, watched_movies_reported_enabled, "
                "watched_movie_low_rating_reported_enabled, watched_movie_low_rating_max_jellyfin_emby_community_rating, "
                "watched_movie_low_rating_max_plex_audience_rating, "
                "unwatched_movie_stale_reported_enabled, unwatched_movie_stale_min_age_days, "
                "preview_max_items, preview_include_genres, preview_include_people, preview_include_people_roles, "
                "preview_year_min, "
                "preview_year_max, preview_include_studios, preview_include_collections, scheduled_preview_enabled, "
                "scheduled_preview_interval_seconds, scheduled_preview_hours_limited, scheduled_preview_days, "
                "scheduled_preview_start, scheduled_preview_end, auto_apply_enabled, or max_deletes_per_run must be "
                "provided."
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
    plex_live_feature_enabled: bool = Field(
        ...,
        description=(
            "Legacy name: mirrors deprecated env MEDIAMOP_PRUNER_PLEX_LIVE_REMOVAL_ENABLED only for operator "
            "visibility. Plex removal always uses preview → apply-from-preview; this flag does not re-enable live scan."
        ),
    )
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
