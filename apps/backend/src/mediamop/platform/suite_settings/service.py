"""Load and update the singleton ``suite_settings`` row."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from mediamop.platform.suite_settings.model import SuiteSettingsRow
from mediamop.platform.suite_settings.schemas import SuiteSettingsOut


def ensure_suite_settings_row(session: Session) -> SuiteSettingsRow:
    row = session.scalars(select(SuiteSettingsRow).where(SuiteSettingsRow.id == 1)).one_or_none()
    if row is None:
        row = SuiteSettingsRow(id=1, product_display_name="MediaMop", signed_in_home_notice=None)
        session.add(row)
        session.flush()
    return row


def build_suite_settings_out(row: SuiteSettingsRow) -> SuiteSettingsOut:
    return SuiteSettingsOut(
        product_display_name=(row.product_display_name or "MediaMop").strip() or "MediaMop",
        signed_in_home_notice=row.signed_in_home_notice,
        updated_at=row.updated_at,
    )


def apply_suite_settings_put(
    session: Session,
    *,
    product_display_name: str,
    signed_in_home_notice: str | None,
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

    row = ensure_suite_settings_row(session)
    row.product_display_name = name
    row.signed_in_home_notice = notice
    session.flush()
    return build_suite_settings_out(row)
