"""Singleton ``subber_settings`` row (id = 1)."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from mediamop.modules.fetcher.fetcher_arr_operator_settings_model import FetcherArrOperatorSettingsRow
from mediamop.modules.subber.subber_settings_model import SubberSettingsRow


def ensure_subber_settings_row(db: Session) -> SubberSettingsRow:
    row = db.scalars(select(SubberSettingsRow).where(SubberSettingsRow.id == 1)).one_or_none()
    if row is None:
        row = SubberSettingsRow(id=1)
        db.add(row)
        db.flush()
    return row


def get_fetcher_arr_hints(db: Session) -> tuple[str, str]:
    """(sonarr_base_url, radarr_base_url) from Fetcher singleton for UI prefill hints."""

    r = db.scalars(select(FetcherArrOperatorSettingsRow).where(FetcherArrOperatorSettingsRow.id == 1)).one_or_none()
    if r is None:
        return "", ""
    return (str(r.sonarr_connection_base_url or "").strip(), str(r.radarr_connection_base_url or "").strip())


def language_preferences_list(row: SubberSettingsRow) -> list[str]:
    try:
        data = json.loads(row.language_preferences_json or "[]")
    except json.JSONDecodeError:
        return ["en"]
    if not isinstance(data, list):
        return ["en"]
    out = [str(x).strip().lower() for x in data if str(x).strip()]
    return out or ["en"]


def set_language_preferences_json(db: Session, row: SubberSettingsRow, langs: list[str]) -> None:
    norm = [str(x).strip().lower() for x in langs if str(x).strip()]
    row.language_preferences_json = json.dumps(norm or ["en"], separators=(",", ":"))
    row.updated_at = datetime.now(timezone.utc)
    db.flush()


def touch_updated_at(row: SubberSettingsRow) -> None:
    row.updated_at = datetime.now(timezone.utc)
