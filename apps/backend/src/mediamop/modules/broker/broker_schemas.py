"""Pydantic schemas for Broker HTTP APIs."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class BrokerIndexerOut(BaseModel):
    id: int
    name: str
    slug: str
    kind: str
    protocol: str
    privacy: str
    url: str
    api_key: str = Field("", description="Never exposes stored secrets; empty when a key is saved.")
    enabled: bool
    priority: int
    categories: list[int]
    tags: list[str]
    last_tested_at: datetime | None = None
    last_test_ok: bool | None = None
    last_test_error: str | None = None
    created_at: datetime
    updated_at: datetime


class BrokerIndexerCreate(BaseModel):
    name: str
    slug: str
    kind: str
    protocol: str
    privacy: str = "public"
    url: str = ""
    api_key: str = ""
    enabled: bool = False
    priority: int = 25
    categories: list[int] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class BrokerIndexerUpdate(BaseModel):
    name: str | None = None
    slug: str | None = None
    kind: str | None = None
    protocol: str | None = None
    privacy: str | None = None
    url: str | None = None
    api_key: str | None = None
    enabled: bool | None = None
    priority: int | None = None
    categories: list[int] | None = None
    tags: list[str] | None = None


class BrokerArrConnectionOut(BaseModel):
    id: int
    arr_type: str
    url: str
    api_key: str = Field("", description="Never exposes stored secrets; empty when a key is saved.")
    sync_mode: str
    last_synced_at: datetime | None = None
    last_sync_ok: bool | None = None
    last_sync_error: str | None = None
    last_manual_sync_at: datetime | None = None
    last_manual_sync_ok: bool | None = None
    indexer_fingerprint: str | None = None
    created_at: datetime
    updated_at: datetime


class BrokerArrConnectionUpdate(BaseModel):
    url: str | None = None
    api_key: str | None = None
    sync_mode: str | None = None


class BrokerJobOut(BaseModel):
    """One ``broker_jobs`` row for inspection (mirrors ``SubberJobsInspectionRow`` shape)."""

    id: int
    dedupe_key: str
    job_kind: str
    status: str
    attempt_count: int = 0
    scope: str | None = None
    payload_json: str | None = None
    last_error: str | None = None
    created_at: datetime
    updated_at: datetime


class BrokerJobsInspectionOut(BaseModel):
    jobs: list[BrokerJobOut]
    default_recent_slice: bool


class BrokerIndexerTestEnqueueIn(BaseModel):
    csrf_token: str = Field(..., min_length=1)


class BrokerArrConnectionPutIn(BrokerArrConnectionUpdate):
    csrf_token: str = Field(..., min_length=1)


class BrokerArrConnectionSyncIn(BaseModel):
    csrf_token: str = Field(..., min_length=1)


class BrokerResultOut(BaseModel):
    title: str
    url: str
    magnet: str | None
    size: int
    seeders: int | None
    leechers: int | None
    protocol: str
    indexer_slug: str
    categories: list[int]
    published_at: datetime | None
    imdb_id: str | None
    info_hash: str | None


class BrokerSettingsOut(BaseModel):
    proxy_api_key: str


class BrokerSettingsRotateIn(BaseModel):
    """POST body for rotating the Broker Torznab/Newznab proxy API key."""

    model_config = ConfigDict(extra="forbid")

    csrf_token: str = Field(..., min_length=1)
