"""Writing, reading, rendering and pruning the per-file processing record."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from mediamop.modules.refiner.refiner_file_log_model import RefinerFileLogRow
from mediamop.modules.refiner.refiner_file_state_model import RefinerFileRow
from mediamop.modules.refiner.refiner_library_model import RefinerLibraryRow

#: A single record is bounded so one pathological payload cannot fill the database. The
#: cap is generous — a full pass detail is a few kilobytes — and truncation is recorded
#: in the row rather than happening silently.
MAX_DETAIL_CHARS = 200_000


def _resolve_file_and_library(
    session: Session, *, relative_path: str
) -> tuple[RefinerFileRow | None, RefinerLibraryRow | None]:
    row = session.scalars(
        select(RefinerFileRow).where(RefinerFileRow.relative_path == relative_path).order_by(RefinerFileRow.id)
    ).first()
    if row is None:
        return None, None
    return row, session.get(RefinerLibraryRow, row.library_id)


def record_file_log(
    session: Session,
    *,
    relative_path: str,
    title: str,
    detail: dict[str, Any] | str,
    recorded_at: datetime | None = None,
) -> RefinerFileLogRow:
    """Persist one completed pass.

    Called from the same place the activity row is written, so the two cannot disagree
    about what happened.
    """

    payload = detail if isinstance(detail, dict) else _loads(detail)
    text = json.dumps(payload, separators=(",", ":"), ensure_ascii=False, default=str)
    truncated = len(text) > MAX_DETAIL_CHARS
    if truncated:
        # Say so in the record rather than leaving a reader to wonder why the JSON stops.
        payload = {
            "truncated": True,
            "truncated_note": (
                f"This record was longer than {MAX_DETAIL_CHARS} characters and was shortened when it was saved."
            ),
            "outcome": payload.get("outcome") if isinstance(payload, dict) else None,
            "detail_excerpt": text[: MAX_DETAIL_CHARS // 2],
        }
        text = json.dumps(payload, separators=(",", ":"), ensure_ascii=False, default=str)

    file_row, library = _resolve_file_and_library(session, relative_path=relative_path)
    row = RefinerFileLogRow(
        file_id=file_row.id if file_row is not None else None,
        library_id=library.id if library is not None else None,
        relative_path=relative_path,
        library_name=library.name if library is not None else "",
        outcome=str(payload.get("outcome") or "") if isinstance(payload, dict) else "",
        title=title,
        detail_json=text,
        recorded_at=recorded_at or datetime.now(UTC),
    )
    session.add(row)
    session.flush()
    return row


def _loads(raw: str | None) -> dict[str, Any]:
    if not raw or not raw.strip():
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {"unparsed_detail": raw[:MAX_DETAIL_CHARS]}
    return parsed if isinstance(parsed, dict) else {"detail": parsed}


def logs_for_file(session: Session, *, file_id: int, limit: int = 50) -> list[RefinerFileLogRow]:
    """Every retained pass over this file, newest first.

    Matched on the file's path as well as its id, so records written before a file row
    was recreated — or after it was forgotten and seen again — still belong to it.
    """

    row = session.get(RefinerFileRow, file_id)
    if row is None:
        return []
    return list(
        session.scalars(
            select(RefinerFileLogRow)
            .where(RefinerFileLogRow.relative_path == row.relative_path)
            .order_by(RefinerFileLogRow.recorded_at.desc(), RefinerFileLogRow.id.desc())
            .limit(max(1, min(limit, 500)))
        )
    )


def render_log_text(rows: list[RefinerFileLogRow]) -> str:
    """A plain-text rendering, for attaching to a bug report.

    Text rather than the raw JSON: the reason someone downloads this is to send it to
    somebody else, and a wall of minified JSON is not something a person can read in a
    forum post.
    """

    if not rows:
        return "MediaMop has no retained processing records for this file.\n"

    lines: list[str] = []
    first = rows[0]
    lines.append(f"MediaMop — processing record for {first.relative_path}")
    if first.library_name:
        lines.append(f"Library: {first.library_name}")
    lines.append(f"Records retained: {len(rows)} (newest first)")
    lines.append("")

    for row in rows:
        stamp = row.recorded_at
        if stamp is not None and stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=UTC)
        lines.append("=" * 78)
        lines.append(f"{stamp.isoformat() if stamp else 'unknown time'}  —  {row.outcome or 'no outcome recorded'}")
        if row.title:
            lines.append(row.title)
        lines.append("-" * 78)
        detail = _loads(row.detail_json)
        for key in sorted(detail):
            value = detail[key]
            rendered = json.dumps(value, ensure_ascii=False, default=str) if isinstance(value, (dict, list)) else value
            lines.append(f"{key}: {rendered}")
        lines.append("")
    return "\n".join(lines) + "\n"


def prune_file_logs(session: Session, *, retention_days: int, now: datetime | None = None) -> int:
    """Delete records older than the retention window. ``0`` keeps everything.

    Zero means forever rather than "delete immediately", matching the setting's own
    wording. Reading it the other way round would silently destroy the history the
    feature exists to keep, which is the worst possible direction for that ambiguity.
    """

    days = int(retention_days)
    if days <= 0:
        return 0
    cutoff = (now or datetime.now(UTC)) - timedelta(days=days)
    doomed = list(session.scalars(select(RefinerFileLogRow.id).where(RefinerFileLogRow.recorded_at < cutoff)))
    if not doomed:
        return 0
    session.execute(delete(RefinerFileLogRow).where(RefinerFileLogRow.id.in_(doomed)))
    session.flush()
    return len(doomed)
