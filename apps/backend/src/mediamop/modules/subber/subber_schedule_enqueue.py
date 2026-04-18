"""Periodic enqueue of Subber library scan jobs (TV and Movies independent)."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session, sessionmaker

from mediamop.core.config import MediaMopSettings
from mediamop.modules.fetcher.fetcher_arr_search_schedule_window import DAY_NAMES, fetcher_arr_search_schedule_in_window
from mediamop.modules.subber.subber_job_kinds import SUBBER_JOB_KIND_LIBRARY_SCAN_MOVIES, SUBBER_JOB_KIND_LIBRARY_SCAN_TV
from mediamop.modules.subber.subber_jobs_ops import subber_enqueue_or_get_job
from mediamop.modules.subber.subber_settings_model import SubberSettingsRow
from mediamop.modules.subber.subber_settings_service import ensure_subber_settings_row
from mediamop.platform.suite_settings.service import ensure_suite_settings_row

logger = logging.getLogger(__name__)

SUBBER_SCHEDULE_ENQUEUE_FAILURE_COOLDOWN_SECONDS = 2.0


def _clamp_interval_seconds(raw: int) -> int:
    return max(60, min(int(raw), 7 * 24 * 3600))


def _branch_due(last_at: datetime | None, interval_seconds: int, *, now: datetime) -> bool:
    iv = _clamp_interval_seconds(interval_seconds)
    if last_at is None:
        return True
    last = last_at if last_at.tzinfo else last_at.replace(tzinfo=timezone.utc)
    return (now - last).total_seconds() >= float(iv)


def _tv_in_window(session: Session, row: SubberSettingsRow, *, when: datetime) -> bool:
    if not bool(row.tv_schedule_hours_limited):
        return True
    suite = ensure_suite_settings_row(session)
    tz_name = (suite.app_timezone or "UTC").strip() or "UTC"
    days_raw = (row.tv_schedule_days or "").strip()
    days_csv = days_raw if days_raw else ",".join(DAY_NAMES)
    start_s = (row.tv_schedule_start or "00:00").strip() or "00:00"
    end_s = (row.tv_schedule_end or "23:59").strip() or "23:59"
    return fetcher_arr_search_schedule_in_window(
        schedule_enabled=True,
        schedule_days=days_csv,
        schedule_start=start_s,
        schedule_end=end_s,
        timezone_name=tz_name,
        now=when,
    )


def _movies_in_window(session: Session, row: SubberSettingsRow, *, when: datetime) -> bool:
    if not bool(row.movies_schedule_hours_limited):
        return True
    suite = ensure_suite_settings_row(session)
    tz_name = (suite.app_timezone or "UTC").strip() or "UTC"
    days_raw = (row.movies_schedule_days or "").strip()
    days_csv = days_raw if days_raw else ",".join(DAY_NAMES)
    start_s = (row.movies_schedule_start or "00:00").strip() or "00:00"
    end_s = (row.movies_schedule_end or "23:59").strip() or "23:59"
    return fetcher_arr_search_schedule_in_window(
        schedule_enabled=True,
        schedule_days=days_csv,
        schedule_start=start_s,
        schedule_end=end_s,
        timezone_name=tz_name,
        now=when,
    )


def enqueue_due_subber_library_scans(session: Session, *, now: datetime) -> int:
    when = now if now.tzinfo else now.replace(tzinfo=timezone.utc)
    row = ensure_subber_settings_row(session)
    if not row.enabled:
        return 0
    enq = 0
    if bool(row.tv_schedule_enabled):
        if _branch_due(row.tv_last_scheduled_scan_enqueued_at, int(row.tv_schedule_interval_seconds), now=when):
            if _tv_in_window(session, row, when=when):
                subber_enqueue_or_get_job(
                    session,
                    dedupe_key=f"subber:libscan:tv:{uuid.uuid4()}",
                    job_kind=SUBBER_JOB_KIND_LIBRARY_SCAN_TV,
                    payload_json=json.dumps({"media_scope": "tv"}, separators=(",", ":")),
                )
                row.tv_last_scheduled_scan_enqueued_at = when
                enq += 1
    if bool(row.movies_schedule_enabled):
        if _branch_due(row.movies_last_scheduled_scan_enqueued_at, int(row.movies_schedule_interval_seconds), now=when):
            if _movies_in_window(session, row, when=when):
                subber_enqueue_or_get_job(
                    session,
                    dedupe_key=f"subber:libscan:movies:{uuid.uuid4()}",
                    job_kind=SUBBER_JOB_KIND_LIBRARY_SCAN_MOVIES,
                    payload_json=json.dumps({"media_scope": "movies"}, separators=(",", ":")),
                )
                row.movies_last_scheduled_scan_enqueued_at = when
                enq += 1
    return enq


def run_subber_schedule_enqueue_tick(
    session_factory: sessionmaker[Session],
    *,
    now: datetime | None = None,
) -> int:
    when = now if now is not None else datetime.now(timezone.utc)
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    with session_factory() as session:
        with session.begin():
            return enqueue_due_subber_library_scans(session, now=when)


async def _run_subber_schedule_forever(
    session_factory: sessionmaker[Session],
    settings: MediaMopSettings,
    *,
    stop_event: asyncio.Event,
) -> None:
    loop = asyncio.get_running_loop()
    scan_iv = float(max(10, min(300, int(settings.subber_library_scan_schedule_scan_interval_seconds))))
    while not stop_event.is_set():

        def _once() -> int:
            return run_subber_schedule_enqueue_tick(session_factory)

        try:
            await asyncio.to_thread(_once)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Subber library scan schedule enqueue tick failed")
            fail_deadline = loop.time() + SUBBER_SCHEDULE_ENQUEUE_FAILURE_COOLDOWN_SECONDS
            while loop.time() < fail_deadline and not stop_event.is_set():
                await asyncio.sleep(min(0.25, fail_deadline - loop.time()))
            continue

        if stop_event.is_set():
            break
        deadline = loop.time() + scan_iv
        while loop.time() < deadline and not stop_event.is_set():
            await asyncio.sleep(min(0.25, deadline - loop.time()))


def start_subber_library_scan_schedule_enqueue_tasks(
    session_factory: sessionmaker[Session],
    *,
    stop_event: asyncio.Event,
    settings: MediaMopSettings,
) -> list[asyncio.Task[None]]:
    if not settings.subber_library_scan_schedule_enqueue_enabled:
        return []
    return [
        asyncio.create_task(
            _run_subber_schedule_forever(session_factory, settings, stop_event=stop_event),
            name="subber-library-scan-schedule-enqueue",
        ),
    ]


async def stop_subber_library_scan_schedule_enqueue_tasks(tasks: list[asyncio.Task[None]]) -> None:
    for t in tasks:
        if not t.done():
            t.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
