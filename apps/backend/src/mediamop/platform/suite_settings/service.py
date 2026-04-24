"""Load and update the singleton ``suite_settings`` row."""

from __future__ import annotations

from datetime import time
from zoneinfo import ZoneInfo
from zoneinfo import ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.orm import Session

from mediamop.platform.suite_settings.model import SuiteSettingsRow
from mediamop.platform.suite_settings.schemas import SuiteSettingsOut


def ensure_suite_settings_row(session: Session) -> SuiteSettingsRow:
    row = session.scalars(select(SuiteSettingsRow).where(SuiteSettingsRow.id == 1)).one_or_none()
    if row is None:
        row = SuiteSettingsRow(
            id=1,
            product_display_name="MediaMop",
            signed_in_home_notice=None,
            setup_wizard_state="pending",
            app_timezone="UTC",
            log_retention_days=30,
            configuration_backup_enabled=False,
            configuration_backup_interval_hours=24,
            configuration_backup_preferred_time="02:00",
            configuration_backup_last_run_at=None,
        )
        session.add(row)
        session.flush()
    return row


def build_suite_settings_out(row: SuiteSettingsRow) -> SuiteSettingsOut:
    wizard_state = (row.setup_wizard_state or "pending").strip().lower() or "pending"
    if wizard_state not in {"pending", "skipped", "completed"}:
        wizard_state = "pending"
    return SuiteSettingsOut(
        product_display_name=(row.product_display_name or "MediaMop").strip() or "MediaMop",
        signed_in_home_notice=row.signed_in_home_notice,
        setup_wizard_state=wizard_state,
        app_timezone=(row.app_timezone or "UTC").strip() or "UTC",
        log_retention_days=max(1, min(int(row.log_retention_days), 3650)),
        configuration_backup_enabled=bool(row.configuration_backup_enabled),
        configuration_backup_interval_hours=max(1, min(int(row.configuration_backup_interval_hours or 24), 720)),
        configuration_backup_preferred_time=_normalize_backup_preferred_time(
            getattr(row, "configuration_backup_preferred_time", None),
        ),
        configuration_backup_last_run_at=row.configuration_backup_last_run_at,
        updated_at=row.updated_at,
    )


def _normalize_backup_preferred_time(raw: str | None) -> str:
    value = (raw or "").strip() or "02:00"
    try:
        hh, mm = value.split(":", 1)
        parsed = time(hour=int(hh), minute=int(mm))
    except (ValueError, TypeError) as exc:
        msg = "Backup time must use HH:MM in 24-hour time."
        raise ValueError(msg) from exc
    return f"{parsed.hour:02d}:{parsed.minute:02d}"


def apply_suite_settings_put(
    session: Session,
    *,
    product_display_name: str,
    signed_in_home_notice: str | None,
    app_timezone: str,
    log_retention_days: int,
    setup_wizard_state: str | None = None,
    configuration_backup_enabled: bool | None = None,
    configuration_backup_interval_hours: int | None = None,
    configuration_backup_preferred_time: str | None = None,
) -> SuiteSettingsOut:
    name = (product_display_name or "").strip()
    if not name:
        msg = "Product name cannot be empty."
        raise ValueError(msg)
    if len(name) > 120:
        msg = "Product name is too long (120 characters maximum)."
        raise ValueError(msg)
    notice = (signed_in_home_notice or "").strip() or None
    if notice is not None and len(notice) > 4000:
        msg = "Home notice is too long (4,000 characters maximum)."
        raise ValueError(msg)
    tz = (app_timezone or "").strip()
    if not tz:
        msg = "Timezone cannot be empty."
        raise ValueError(msg)
    try:
        ZoneInfo(tz)
    except ZoneInfoNotFoundError as exc:
        msg = "Choose a valid timezone (for example: UTC, Europe/London, America/New_York)."
        raise ValueError(msg) from exc
    keep_days = int(log_retention_days)
    if keep_days < 1 or keep_days > 3650:
        msg = "Log retention must be between 1 and 3650 days."
        raise ValueError(msg)
    wizard_state: str | None = None
    if setup_wizard_state is not None:
        wizard_state = (setup_wizard_state or "").strip().lower()
        if wizard_state not in {"pending", "skipped", "completed"}:
            msg = "Setup wizard state must be pending, skipped, or completed."
            raise ValueError(msg)
    backup_hours: int | None = None
    if configuration_backup_interval_hours is not None:
        backup_hours = int(configuration_backup_interval_hours)
        if backup_hours < 1 or backup_hours > 720:
            msg = "Backup interval must be between 1 and 720 hours."
            raise ValueError(msg)
    backup_time: str | None = None
    if configuration_backup_preferred_time is not None:
        backup_time = _normalize_backup_preferred_time(configuration_backup_preferred_time)

    row = ensure_suite_settings_row(session)
    row.product_display_name = name
    row.signed_in_home_notice = notice
    if wizard_state is not None:
        row.setup_wizard_state = wizard_state
    row.app_timezone = tz
    row.log_retention_days = keep_days
    if configuration_backup_enabled is not None:
        row.configuration_backup_enabled = bool(configuration_backup_enabled)
    if backup_hours is not None:
        row.configuration_backup_interval_hours = backup_hours
    if backup_time is not None:
        row.configuration_backup_preferred_time = backup_time
    session.flush()
    return build_suite_settings_out(row)
