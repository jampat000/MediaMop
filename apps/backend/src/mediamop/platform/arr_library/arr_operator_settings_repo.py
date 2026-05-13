from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from mediamop.platform.arr_library.arr_operator_settings_model import ArrLibraryOperatorSettingsRow


def ensure_arr_library_operator_settings_row(session: Session) -> ArrLibraryOperatorSettingsRow:
    row = session.scalars(
        select(ArrLibraryOperatorSettingsRow).where(ArrLibraryOperatorSettingsRow.id == 1)
    ).one_or_none()
    if row is None:
        row = ArrLibraryOperatorSettingsRow(id=1)
        session.add(row)
        session.flush()
    return row
