"""Request and response shapes for media manager connections.

Secrets go in and never come back out. Each response says whether one is *saved*,
which is what a settings screen needs in order to be honest without ever displaying
a credential.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

MediaManagerKind = Literal["radarr", "sonarr", "deluno", "native"]
SearchLane = Literal["missing", "upgrade"]


class MediaManagerSearchLaneOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    lane: SearchLane
    enabled: bool = Field(description="Whether this automatic search lane is turned on.")
    max_items_per_run: int = Field(ge=1, le=1000)
    retry_delay_minutes: int = Field(ge=1, le=525600)
    schedule_enabled: bool = Field(description="When on, searches only run inside the days and times below.")
    schedule_days: str = Field(description="Comma-separated weekdays, e.g. Mon,Tue. Empty means every day.")
    schedule_start: str = Field(max_length=5)
    schedule_end: str = Field(max_length=5)
    schedule_interval_seconds: int = Field(ge=60, le=604800)


class MediaManagerSearchLaneIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    csrf_token: str = Field(..., min_length=1)
    enabled: bool
    max_items_per_run: int = Field(ge=1, le=1000)
    retry_delay_minutes: int = Field(ge=1, le=525600)
    schedule_enabled: bool
    schedule_days: str = Field(max_length=2000)
    schedule_start: str = Field(max_length=5)
    schedule_end: str = Field(max_length=5)
    schedule_interval_seconds: int = Field(ge=60, le=604800)


class MediaManagerConnectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: MediaManagerKind
    name: str
    enabled: bool
    base_url: str = Field(description="Address MediaMop uses to reach this manager. Empty means not set.")
    api_key_is_saved: bool = Field(description="Whether an API key is stored encrypted for this manager.")
    webhook_secret_is_set: bool = Field(
        description="Whether this manager must present a secret when it posts to the intake webhook."
    )
    webhook_url_path: str = Field(description="Where this manager should post its events.")
    last_test_ok: bool | None = None
    last_test_at: datetime | None = None
    last_test_detail: str | None = None
    lanes: list[MediaManagerSearchLaneOut] = Field(default_factory=list)


class MediaManagerConnectionCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    csrf_token: str = Field(..., min_length=1)
    kind: MediaManagerKind
    name: str = Field(..., min_length=1, max_length=200)
    enabled: bool = True
    base_url: str = Field(default="", max_length=2000)
    api_key: str = Field(
        default="",
        max_length=2000,
        description="Stored encrypted. Empty means no key.",
    )


class MediaManagerConnectionUpdateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    csrf_token: str = Field(..., min_length=1)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    enabled: bool | None = None
    base_url: str | None = Field(default=None, max_length=2000)
    api_key: str | None = Field(
        default=None,
        max_length=2000,
        description="Omit to leave the saved key alone. Send an empty string to clear it.",
    )


class MediaManagerConnectionDeleteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    csrf_token: str = Field(..., min_length=1)


class MediaManagerWebhookSecretOut(BaseModel):
    """The generated secret, shown once. MediaMop keeps only the encrypted copy."""

    connection_id: int
    webhook_secret: str
    webhook_url_path: str
    header_name: str = "X-Webhook-Secret"


class MediaManagerConnectionTestIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    csrf_token: str = Field(..., min_length=1)


class MediaManagerConnectionTestOut(BaseModel):
    connection_id: int
    ok: bool
    detail: str
    checked_at: datetime


class MediaManagerCapabilityOut(BaseModel):
    """What one connected manager can be asked, and what it says it manages.

    This is the outbound half of ADR-0013 made visible: an operator can see, before
    anything runs, whether a manager will give Refiner an upstream safety check and
    whether it can clear a folder for deletion. A manager that cannot do one of those
    says so here rather than looking like a clean pass later.
    """

    connection_id: int
    kind: MediaManagerKind
    name: str
    label: str = Field(description="How this connection is named in operator messages, e.g. 'Deluno (Main)'.")
    media_scopes: list[Literal["movie", "tv"]] = Field(
        description="Which libraries this manager looks after. A manager may serve both."
    )
    reports_import_queue: bool = Field(
        description="Whether MediaMop can ask this manager what it is currently importing."
    )
    reports_library_truth: bool = Field(
        description="Whether MediaMop can ask this manager which files it still keeps, which folder cleanup needs."
    )
    reachable: bool = Field(description="Whether the manager answered when MediaMop asked what it manages.")
    library_roots: list[str] = Field(default_factory=list, description="Folders this manager reported that it manages.")
    summary: str = Field(description="One plain-language sentence about what MediaMop can do with this manager.")
    detail: str | None = Field(default=None, description="Why MediaMop could not ask, when it could not.")
