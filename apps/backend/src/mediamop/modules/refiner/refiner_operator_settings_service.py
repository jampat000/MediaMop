"""Singleton Refiner operator settings service."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from mediamop.platform.arr_library.schedule_csv_validate import normalize_hhmm, validate_schedule_days_csv
from mediamop.platform.arr_library.schedule_wall_clock import schedule_time_window_active
from mediamop.modules.refiner.refiner_operator_settings_model import RefinerOperatorSettingsRow
from mediamop.modules.refiner.schemas_refiner_operator_settings import (
    RefinerOperatorSettingsOut,
    RefinerOperatorSettingsPutIn,
)
from mediamop.platform.suite_settings.service import ensure_suite_settings_row


def _clamp_max_concurrent_files(raw: int) -> int:
    return max(1, min(8, int(raw)))


def _clamp_min_file_age_seconds(raw: int) -> int:
    return max(0, min(int(raw), 7 * 24 * 3600))


def ensure_refiner_operator_settings_row(db: Session) -> RefinerOperatorSettingsRow:
    row = db.scalars(select(RefinerOperatorSettingsRow).where(RefinerOperatorSettingsRow.id == 1)).one_or_none()
    if row is None:
        row = RefinerOperatorSettingsRow(
            id=1,
            max_concurrent_files=1,
            min_file_age_seconds=60,
            movie_schedule_enabled=1,
            movie_schedule_hours_limited=0,
            movie_schedule_days="",
            movie_schedule_start="00:00",
            movie_schedule_end="23:59",
            tv_schedule_enabled=1,
            tv_schedule_hours_limited=0,
            tv_schedule_days="",
            tv_schedule_start="00:00",
            tv_schedule_end="23:59",
        )
        db.add(row)
        db.flush()
    return row


def refiner_periodic_scope_in_schedule_window(
    db: Session,
    row: RefinerOperatorSettingsRow,
    *,
    media_scope: str,
    now: datetime | None = None,
) -> bool:
    """True when a periodic Refiner watched-folder scan may run for this scope."""

    when = now if now is not None else datetime.now(timezone.utc)
    if media_scope == "movie":
        if not bool(row.movie_schedule_hours_limited):
            return True
        suite = ensure_suite_settings_row(db)
        tz_name = (suite.app_timezone or "UTC").strip() or "UTC"
        return schedule_time_window_active(
            schedule_enabled=True,
            schedule_days=(row.movie_schedule_days or "").strip(),
            schedule_start=(row.movie_schedule_start or "00:00").strip(),
            schedule_end=(row.movie_schedule_end or "23:59").strip(),
            timezone_name=tz_name,
            now=when,
        )
    if media_scope == "tv":
        if not bool(row.tv_schedule_hours_limited):
            return True
        suite = ensure_suite_settings_row(db)
        tz_name = (suite.app_timezone or "UTC").strip() or "UTC"
        return schedule_time_window_active(
            schedule_enabled=True,
            schedule_days=(row.tv_schedule_days or "").strip(),
            schedule_start=(row.tv_schedule_start or "00:00").strip(),
            schedule_end=(row.tv_schedule_end or "23:59").strip(),
            timezone_name=tz_name,
            now=when,
        )
    return False


def build_refiner_operator_settings_out(db: Session, row: RefinerOperatorSettingsRow) -> RefinerOperatorSettingsOut:
    suite = ensure_suite_settings_row(db)
    tz = (suite.app_timezone or "UTC").strip() or "UTC"
    return RefinerOperatorSettingsOut(
        max_concurrent_files=_clamp_max_concurrent_files(row.max_concurrent_files),
        min_file_age_seconds=_clamp_min_file_age_seconds(row.min_file_age_seconds),
        movie_schedule_enabled=bool(row.movie_schedule_enabled),
        movie_schedule_hours_limited=bool(row.movie_schedule_hours_limited),
        movie_schedule_days=(row.movie_schedule_days or "").strip(),
        movie_schedule_start=(row.movie_schedule_start or "00:00").strip(),
        movie_schedule_end=(row.movie_schedule_end or "23:59").strip(),
        tv_schedule_enabled=bool(row.tv_schedule_enabled),
        tv_schedule_hours_limited=bool(row.tv_schedule_hours_limited),
        tv_schedule_days=(row.tv_schedule_days or "").strip(),
        tv_schedule_start=(row.tv_schedule_start or "00:00").strip(),
        tv_schedule_end=(row.tv_schedule_end or "23:59").strip(),
        schedule_timezone=tz,
        updated_at=row.updated_at.isoformat() if row.updated_at else "",
    )


def apply_refiner_operator_settings_put(db: Session, body: RefinerOperatorSettingsPutIn) -> RefinerOperatorSettingsRow:
    row = ensure_refiner_operator_settings_row(db)
    if body.max_concurrent_files is not None:
        row.max_concurrent_files = _clamp_max_concurrent_files(body.max_concurrent_files)
    if body.min_file_age_seconds is not None:
        row.min_file_age_seconds = _clamp_min_file_age_seconds(body.min_file_age_seconds)
    if body.movie_schedule_enabled is not None:
        row.movie_schedule_enabled = 1 if body.movie_schedule_enabled else 0
        row.movie_schedule_hours_limited = 1 if body.movie_schedule_hours_limited else 0
        row.movie_schedule_days = validate_schedule_days_csv(cast(str, body.movie_schedule_days))
        row.movie_schedule_start = normalize_hhmm(cast(str, body.movie_schedule_start), fallback="00:00")
        row.movie_schedule_end = normalize_hhmm(cast(str, body.movie_schedule_end), fallback="23:59")
    if body.tv_schedule_enabled is not None:
        row.tv_schedule_enabled = 1 if body.tv_schedule_enabled else 0
        row.tv_schedule_hours_limited = 1 if body.tv_schedule_hours_limited else 0
        row.tv_schedule_days = validate_schedule_days_csv(cast(str, body.tv_schedule_days))
        row.tv_schedule_start = normalize_hhmm(cast(str, body.tv_schedule_start), fallback="00:00")
        row.tv_schedule_end = normalize_hhmm(cast(str, body.tv_schedule_end), fallback="23:59")
    db.flush()
    return row
