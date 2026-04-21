"""Load and update the singleton ``suite_settings`` row."""

from __future__ import annotations

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
            app_timezone="UTC",
            log_retention_days=30,
        )
        session.add(row)
        session.flush()
    return row


def build_suite_settings_out(row: SuiteSettingsRow) -> SuiteSettingsOut:
    return SuiteSettingsOut(
        product_display_name=(row.product_display_name or "MediaMop").strip() or "MediaMop",
        signed_in_home_notice=row.signed_in_home_notice,
        app_timezone=(row.app_timezone or "UTC").strip() or "UTC",
        log_retention_days=max(1, min(int(row.log_retention_days), 3650)),
        updated_at=row.updated_at,
    )


def apply_suite_settings_put(
    session: Session,
    *,
    product_display_name: str,
    signed_in_home_notice: str | None,
    app_timezone: str,
    log_retention_days: int,
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

    row = ensure_suite_settings_row(session)
    row.product_display_name = name
    row.signed_in_home_notice = notice
    row.app_timezone = tz
    row.log_retention_days = keep_days
    session.flush()
    return build_suite_settings_out(row)
