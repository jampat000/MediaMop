"""Operator-facing labels for durable failed-import cleanup drive ``job_kind`` strings."""

from __future__ import annotations

from mediamop.modules.fetcher.failed_import_drive_job_kinds import (
    FAILED_IMPORT_JOB_KIND_RADARR_CLEANUP_DRIVE,
    FAILED_IMPORT_JOB_KIND_SONARR_CLEANUP_DRIVE,
)

OPERATOR_LABEL_BY_FAILED_IMPORT_DRIVE_JOB_KIND: dict[str, str] = {
    FAILED_IMPORT_JOB_KIND_RADARR_CLEANUP_DRIVE: "Radarr cleanup",
    FAILED_IMPORT_JOB_KIND_SONARR_CLEANUP_DRIVE: "Sonarr cleanup",
}


def operator_label_for_failed_import_drive_job_kind(job_kind: str) -> str:
    """Return a short operator label, or the raw ``job_kind`` when unknown."""

    return OPERATOR_LABEL_BY_FAILED_IMPORT_DRIVE_JOB_KIND.get(job_kind, job_kind)
