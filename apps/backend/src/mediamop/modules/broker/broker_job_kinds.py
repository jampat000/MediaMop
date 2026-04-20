"""Durable Broker job kinds (``broker_jobs`` lane only)."""

from __future__ import annotations

BROKER_JOB_KIND_SYNC_SONARR_V1 = "broker.sync.sonarr.v1"
BROKER_JOB_KIND_SYNC_RADARR_V1 = "broker.sync.radarr.v1"
BROKER_JOB_KIND_SYNC_SONARR_MANUAL_V1 = "broker.sync.sonarr.manual.v1"
BROKER_JOB_KIND_SYNC_RADARR_MANUAL_V1 = "broker.sync.radarr.manual.v1"
BROKER_JOB_KIND_INDEXER_TEST_V1 = "broker.indexer.test.v1"

ALL_BROKER_PRODUCTION_JOB_KINDS: frozenset[str] = frozenset(
    {
        BROKER_JOB_KIND_SYNC_SONARR_V1,
        BROKER_JOB_KIND_SYNC_RADARR_V1,
        BROKER_JOB_KIND_SYNC_SONARR_MANUAL_V1,
        BROKER_JOB_KIND_SYNC_RADARR_MANUAL_V1,
        BROKER_JOB_KIND_INDEXER_TEST_V1,
    },
)
