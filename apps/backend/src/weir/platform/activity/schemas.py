"""Read-only JSON shapes for Activity API."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ActivityEventItemOut(BaseModel):
    id: int
    created_at: datetime
    event_type: str = Field(..., description="Stable type key, e.g. auth.login_succeeded.")
    module: str = Field(..., description="Source area, e.g. auth.")
    title: str
    detail: str | None = None
    trigger: str | None = Field(default=None, description="Why it happened: manual, scheduled, webhook, retry, …")
    result: str | None = Field(default=None, description="How it went: success, skipped, warning, running, failed.")
    library_id: int | None = None
    relative_path: str | None = Field(default=None, description="The file this concerns, relative to its library.")
    run_key: str | None = Field(default=None, description="Events sharing a run key belong to one run.")

    model_config = {"from_attributes": True}


class ActivityRecentOut(BaseModel):
    items: list[ActivityEventItemOut] = Field(default_factory=list)
    total: int = Field(default=0, ge=0)
    system_events: int = Field(default=0, ge=0)
    has_more: bool = Field(default=False, description="More matching persisted events exist beyond this bounded page.")
    retention_days: int = Field(
        default=90, ge=0, description="How far back history is kept. 0 means it is kept until cleared."
    )
    oldest_event_at: datetime | None = Field(
        default=None, description="The oldest event still kept, so the page can say how far back history goes."
    )


class ActivityFileHistoryIn(BaseModel):
    """Which file's history to count or remove."""

    library_id: int | None = Field(default=None, ge=1)
    relative_path: str = Field(..., min_length=1, max_length=2000)


class ActivityFileHistoryCountOut(BaseModel):
    relative_path: str
    activity_events: int = Field(ge=0)
    processing_records: int = Field(ge=0)
    message: str = Field(description="Exactly what removing it would delete, and what it would not.")


class ActivityFileHistoryRemoveIn(ActivityFileHistoryIn):
    csrf_token: str = Field(..., min_length=1)


class ActivityFileHistoryRemoveOut(BaseModel):
    relative_path: str
    activity_events_deleted: int = Field(ge=0)
    processing_records_deleted: int = Field(ge=0)
