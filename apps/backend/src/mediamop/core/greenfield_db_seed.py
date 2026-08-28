"""Singleton rows required for a usable database after empty schema creation."""

from __future__ import annotations

from sqlalchemy.orm import Session

from mediamop.modules.refiner.refiner_operator_settings_model import RefinerOperatorSettingsRow
from mediamop.modules.refiner.refiner_path_settings_model import RefinerPathSettingsRow
from mediamop.modules.refiner.refiner_remux_rules_settings_service import ensure_refiner_remux_rules_settings_row
from mediamop.platform.arr_library.arr_operator_settings_model import ArrLibraryOperatorSettingsRow
from mediamop.platform.suite_settings.service import ensure_suite_settings_row


def seed_greenfield_singleton_rows(session: Session) -> None:
    """Ensure ``id = 1`` configuration rows exist (idempotent)."""

    ensure_suite_settings_row(session)
    if session.get(ArrLibraryOperatorSettingsRow, 1) is None:
        session.add(ArrLibraryOperatorSettingsRow(id=1))
    if session.get(RefinerOperatorSettingsRow, 1) is None:
        session.add(RefinerOperatorSettingsRow(id=1))
    if session.get(RefinerPathSettingsRow, 1) is None:
        session.add(RefinerPathSettingsRow(id=1))
    ensure_refiner_remux_rules_settings_row(session)
    session.flush()
