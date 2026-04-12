"""Enqueue ``fetcher_jobs`` rows for scheduled and manual Arr search work."""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable

from sqlalchemy.orm import Session

from mediamop.core.config import MediaMopSettings
from mediamop.modules.fetcher.fetcher_jobs_model import FetcherJob
from mediamop.modules.fetcher.fetcher_jobs_ops import fetcher_enqueue_or_get_job, fetcher_enqueue_or_requeue_schedule_job
from mediamop.modules.fetcher.fetcher_search_job_kinds import (
    DEDUPE_SCHEDULED_RADARR_MISSING,
    DEDUPE_SCHEDULED_RADARR_UPGRADE,
    DEDUPE_SCHEDULED_SONARR_MISSING,
    DEDUPE_SCHEDULED_SONARR_UPGRADE,
    JOB_KIND_MISSING_SEARCH_RADARR_MONITORED_MOVIES_V1,
    JOB_KIND_MISSING_SEARCH_SONARR_MONITORED_EPISODES_V1,
    JOB_KIND_UPGRADE_SEARCH_RADARR_CUTOFF_UNMET_V1,
    JOB_KIND_UPGRADE_SEARCH_SONARR_CUTOFF_UNMET_V1,
)

ArrSearchManualScope = str  # sonarr_missing | sonarr_upgrade | radarr_missing | radarr_upgrade


def enqueue_scheduled_sonarr_missing_search_job(session: Session) -> None:
    fetcher_enqueue_or_requeue_schedule_job(
        session,
        dedupe_key=DEDUPE_SCHEDULED_SONARR_MISSING,
        job_kind=JOB_KIND_MISSING_SEARCH_SONARR_MONITORED_EPISODES_V1,
        payload_json=json.dumps({"manual": False}),
    )


def enqueue_scheduled_sonarr_upgrade_search_job(session: Session) -> None:
    fetcher_enqueue_or_requeue_schedule_job(
        session,
        dedupe_key=DEDUPE_SCHEDULED_SONARR_UPGRADE,
        job_kind=JOB_KIND_UPGRADE_SEARCH_SONARR_CUTOFF_UNMET_V1,
        payload_json=json.dumps({"manual": False}),
    )


def enqueue_scheduled_radarr_missing_search_job(session: Session) -> None:
    fetcher_enqueue_or_requeue_schedule_job(
        session,
        dedupe_key=DEDUPE_SCHEDULED_RADARR_MISSING,
        job_kind=JOB_KIND_MISSING_SEARCH_RADARR_MONITORED_MOVIES_V1,
        payload_json=json.dumps({"manual": False}),
    )


def enqueue_scheduled_radarr_upgrade_search_job(session: Session) -> None:
    fetcher_enqueue_or_requeue_schedule_job(
        session,
        dedupe_key=DEDUPE_SCHEDULED_RADARR_UPGRADE,
        job_kind=JOB_KIND_UPGRADE_SEARCH_RADARR_CUTOFF_UNMET_V1,
        payload_json=json.dumps({"manual": False}),
    )


def enqueue_manual_arr_search_job(session: Session, *, scope: ArrSearchManualScope) -> FetcherJob:
    dedupe = f"fetcher.search.manual:{scope}:{uuid.uuid4()}"
    mapping: dict[str, tuple[str, str]] = {
        "sonarr_missing": (JOB_KIND_MISSING_SEARCH_SONARR_MONITORED_EPISODES_V1, dedupe),
        "sonarr_upgrade": (JOB_KIND_UPGRADE_SEARCH_SONARR_CUTOFF_UNMET_V1, dedupe),
        "radarr_missing": (JOB_KIND_MISSING_SEARCH_RADARR_MONITORED_MOVIES_V1, dedupe),
        "radarr_upgrade": (JOB_KIND_UPGRADE_SEARCH_RADARR_CUTOFF_UNMET_V1, dedupe),
    }
    kind, dk = mapping[scope]
    return fetcher_enqueue_or_get_job(
        session,
        dedupe_key=dk,
        job_kind=kind,
        payload_json=json.dumps({"manual": True}),
    )


def arr_search_schedule_specs(settings: MediaMopSettings) -> list[tuple[str, float, Callable[[Session], None]]]:
    """Periodic asyncio specs: (label, interval_seconds, enqueue_fn). Empty when disabled or missing URL/key."""

    out: list[tuple[str, float, Callable[[Session], None]]] = []
    son_b, son_k = settings.arr_http_sonarr_credentials()
    rad_b, rad_k = settings.arr_http_radarr_credentials()
    son_ok = bool(son_b and son_k)
    rad_ok = bool(rad_b and rad_k)
    if son_ok and settings.fetcher_sonarr_missing_search_enabled:
        out.append(
            (
                "sonarr_missing_search",
                float(settings.fetcher_sonarr_missing_search_schedule_interval_seconds),
                enqueue_scheduled_sonarr_missing_search_job,
            ),
        )
    if son_ok and settings.fetcher_sonarr_upgrade_search_enabled:
        out.append(
            (
                "sonarr_upgrade_search",
                float(settings.fetcher_sonarr_upgrade_search_schedule_interval_seconds),
                enqueue_scheduled_sonarr_upgrade_search_job,
            ),
        )
    if rad_ok and settings.fetcher_radarr_missing_search_enabled:
        out.append(
            (
                "radarr_missing_search",
                float(settings.fetcher_radarr_missing_search_schedule_interval_seconds),
                enqueue_scheduled_radarr_missing_search_job,
            ),
        )
    if rad_ok and settings.fetcher_radarr_upgrade_search_enabled:
        out.append(
            (
                "radarr_upgrade_search",
                float(settings.fetcher_radarr_upgrade_search_schedule_interval_seconds),
                enqueue_scheduled_radarr_upgrade_search_job,
            ),
        )
    return out
