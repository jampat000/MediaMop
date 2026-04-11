"""Canonical ``job_kind`` strings for durable failed-import cleanup drive work on ``fetcher_jobs``."""

from __future__ import annotations

FAILED_IMPORT_JOB_KIND_RADARR_CLEANUP_DRIVE = "failed_import.radarr.cleanup_drive.v1"
FAILED_IMPORT_JOB_KIND_SONARR_CLEANUP_DRIVE = "failed_import.sonarr.cleanup_drive.v1"

FETCHER_FAILED_IMPORT_DRIVE_JOB_KINDS: frozenset[str] = frozenset(
    {
        FAILED_IMPORT_JOB_KIND_RADARR_CLEANUP_DRIVE,
        FAILED_IMPORT_JOB_KIND_SONARR_CLEANUP_DRIVE,
    },
)
