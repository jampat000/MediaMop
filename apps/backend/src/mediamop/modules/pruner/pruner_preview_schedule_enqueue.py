"""Periodic asyncio scan: enqueue scheduled ``pruner.candidate_removal.preview.v1`` jobs per scope row.

Each ``pruner_scope_settings`` row is evaluated independently for due-time (its own interval and
``last_scheduled_preview_enqueued_at`` only). Manual preview HTTP enqueue must never touch
``last_scheduled_preview_enqueued_at`` — only this module updates that column.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from mediamop.core.config import MediaMopSettings
from mediamop.modules.pruner.pruner_constants import clamp_pruner_scheduled_preview_interval_seconds
from mediamop.modules.pruner.pruner_job_kinds import PRUNER_CANDIDATE_REMOVAL_PREVIEW_JOB_KIND
from mediamop.modules.pruner.pruner_jobs_ops import pruner_enqueue_or_get_job
from mediamop.modules.fetcher.fetcher_arr_search_schedule_window import DAY_NAMES, fetcher_arr_search_schedule_in_window
from mediamop.modules.pruner.pruner_scope_settings_model import PrunerScopeSettings
from mediamop.modules.pruner.pruner_server_instance_model import PrunerServerInstance
from mediamop.platform.suite_settings.service import ensure_suite_settings_row

logger = logging.getLogger(__name__)

PRUNER_PREVIEW_SCHEDULE_ENQUEUE_FAILURE_COOLDOWN_SECONDS = 2.0


def _scope_row_in_schedule_window(session: Session, sc: PrunerScopeSettings, *, when: datetime) -> bool:
    """When hours limiting is off, always True. Otherwise wall-clock must fall inside days + time window."""

    if not bool(sc.scheduled_preview_hours_limited):
        return True
    suite = ensure_suite_settings_row(session)
    tz_name = (suite.app_timezone or "UTC").strip() or "UTC"
    days_raw = (sc.scheduled_preview_days or "").strip()
    days_csv = days_raw if days_raw else ",".join(DAY_NAMES)
    start_s = (sc.scheduled_preview_start or "00:00").strip() or "00:00"
    end_s = (sc.scheduled_preview_end or "23:59").strip() or "23:59"
    return fetcher_arr_search_schedule_in_window(
        schedule_enabled=True,
        schedule_days=days_csv,
        schedule_start=start_s,
        schedule_end=end_s,
        timezone_name=tz_name,
        now=when,
    )


def _scope_row_due(sc: PrunerScopeSettings, *, now: datetime) -> bool:
    """Due using only this row's interval and ``last_scheduled_preview_enqueued_at``."""

    when = now if now.tzinfo else now.replace(tzinfo=timezone.utc)
    interval = clamp_pruner_scheduled_preview_interval_seconds(int(sc.scheduled_preview_interval_seconds))
    last_at = sc.last_scheduled_preview_enqueued_at
    if last_at is None:
        return True
    last = last_at if last_at.tzinfo else last_at.replace(tzinfo=timezone.utc)
    return (when - last).total_seconds() >= float(interval)


def enqueue_due_scheduled_pruner_previews(session: Session, *, now: datetime) -> int:
    """Inside the caller's transaction: enqueue due jobs and stamp scheduler timestamps.

    Preconditions checked per row:

    * ``scheduled_preview_enabled``
    * parent instance ``enabled``
    * ``missing_primary_media_reported_enabled`` for that scope row
    * row's own due-time vs ``last_scheduled_preview_enqueued_at`` and its interval
    """

    when = now if now.tzinfo else now.replace(tzinfo=timezone.utc)
    stmt = (
        select(PrunerScopeSettings)
        .join(
            PrunerServerInstance,
            PrunerScopeSettings.server_instance_id == PrunerServerInstance.id,
        )
        .where(
            PrunerScopeSettings.scheduled_preview_enabled.is_(True),
            PrunerServerInstance.enabled.is_(True),
            PrunerScopeSettings.missing_primary_media_reported_enabled.is_(True),
        )
        .order_by(PrunerScopeSettings.id.asc())
    )
    rows = list(session.scalars(stmt))
    enqueued = 0
    for sc in rows:
        if not _scope_row_due(sc, now=when):
            continue
        if not _scope_row_in_schedule_window(session, sc, when=when):
            continue
        sid = int(sc.server_instance_id)
        scope = str(sc.media_scope)
        dedupe = f"pruner:preview:sched:v1:{sid}:{scope}:{uuid.uuid4()}"
        payload = {"server_instance_id": sid, "media_scope": scope, "trigger": "scheduled"}
        pruner_enqueue_or_get_job(
            session,
            dedupe_key=dedupe,
            job_kind=PRUNER_CANDIDATE_REMOVAL_PREVIEW_JOB_KIND,
            payload_json=json.dumps(payload, separators=(",", ":")),
        )
        sc.last_scheduled_preview_enqueued_at = when
        enqueued += 1
    return enqueued


def run_pruner_preview_schedule_enqueue_tick(
    session_factory: sessionmaker[Session],
    *,
    now: datetime | None = None,
) -> int:
    when = now if now is not None else datetime.now(timezone.utc)
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    with session_factory() as session:
        with session.begin():
            return enqueue_due_scheduled_pruner_previews(session, now=when)


async def _run_pruner_preview_schedule_forever(
    session_factory: sessionmaker[Session],
    settings: MediaMopSettings,
    *,
    stop_event: asyncio.Event,
) -> None:
    loop = asyncio.get_running_loop()
    scan_iv = float(max(10, min(300, int(settings.pruner_preview_schedule_scan_interval_seconds))))
    while not stop_event.is_set():

        def _once() -> int:
            return run_pruner_preview_schedule_enqueue_tick(session_factory)

        try:
            await asyncio.to_thread(_once)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Pruner scheduled preview enqueue tick failed")
            fail_deadline = loop.time() + PRUNER_PREVIEW_SCHEDULE_ENQUEUE_FAILURE_COOLDOWN_SECONDS
            while loop.time() < fail_deadline and not stop_event.is_set():
                await asyncio.sleep(min(0.25, fail_deadline - loop.time()))
            continue

        if stop_event.is_set():
            break
        deadline = loop.time() + scan_iv
        while loop.time() < deadline and not stop_event.is_set():
            await asyncio.sleep(min(0.25, deadline - loop.time()))


def start_pruner_preview_schedule_enqueue_tasks(
    session_factory: sessionmaker[Session],
    *,
    stop_event: asyncio.Event,
    settings: MediaMopSettings,
) -> list[asyncio.Task[None]]:
    if not settings.pruner_preview_schedule_enqueue_enabled:
        return []
    return [
        asyncio.create_task(
            _run_pruner_preview_schedule_forever(session_factory, settings, stop_event=stop_event),
            name="pruner-preview-schedule-enqueue",
        ),
    ]


async def stop_pruner_preview_schedule_enqueue_tasks(tasks: list[asyncio.Task[None]]) -> None:
    for t in tasks:
        if not t.done():
            t.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
