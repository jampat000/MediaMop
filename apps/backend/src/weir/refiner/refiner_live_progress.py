"""How far the pass currently working on a file has got (#463).

Progress is already recorded: while a file is being processed, the pass keeps a single
``refiner.file_processing_progress`` activity row updated with a JSON payload carrying
``percent``, ``eta_seconds`` and the message it would show an operator. That write is already
throttled (roughly one update every two seconds) and already tolerates a locked database.

So this module **reads** rather than adding a second source of truth. Nothing here writes, and
no new column or table was needed to show a live bar.

Two things it must not do:

* **Show stale progress.** A row is only considered when it was updated recently and its payload
  still says a pass is running. A finished file showing 61% forever is worse than showing nothing.
* **Fail a page load.** The payload is operator-facing JSON written by another process; anything
  malformed is skipped rather than raised.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from weir.core.datetime_util import as_utc
from weir.platform.activity import constants as activity_constants
from weir.platform.activity.models import ActivityEvent
from weir.platform.auth.sessions import utcnow

logger = logging.getLogger(__name__)

#: Beyond this, a progress row is treated as abandoned. The writer updates about every two
#: seconds, so anything older than this means the pass stopped without a final update.
STALE_AFTER = timedelta(minutes=2)

#: Payload states that mean work is still happening. Anything else (finished, failed) is the
#: pass's own last word and must not be drawn as an in-flight bar.
_LIVE_STATUSES = frozenset({"processing", "finishing"})

#: A bounded look-back. Only a handful of files can be in flight at once (one per lane), so a
#: small window is plenty and keeps this off the critical path of a page load.
_MAX_ROWS = 64


@dataclass(frozen=True, slots=True)
class LiveProgress:
    percent: float | None
    message: str | None
    eta_seconds: float | None


def _coerce_percent(raw: Any) -> float | None:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    if value != value:  # NaN
        return None
    return max(0.0, min(100.0, value))


def _coerce_seconds(raw: Any) -> float | None:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    if value != value or value < 0:
        return None
    return value


def live_progress_by_path(db: Session) -> dict[str, LiveProgress]:
    """Map ``relative_media_path`` to the progress of the pass currently running on it.

    Returns an empty mapping when nothing is in flight, which is the normal state.
    """

    cutoff = utcnow() - STALE_AFTER
    rows = db.scalars(
        select(ActivityEvent)
        .where(
            ActivityEvent.event_type == activity_constants.REFINER_FILE_PROCESSING_PROGRESS,
            ActivityEvent.created_at >= cutoff,
        )
        .order_by(ActivityEvent.created_at.desc())
        .limit(_MAX_ROWS),
    ).all()

    out: dict[str, LiveProgress] = {}
    for row in rows:
        try:
            payload = json.loads(row.detail or "{}")
        except (ValueError, TypeError):
            # Written by another process; a page load must not fail because one row is odd.
            logger.debug("Refiner live progress: unreadable payload on activity %s", row.id, exc_info=True)
            continue
        if not isinstance(payload, dict):
            continue
        if str(payload.get("status") or "").strip().lower() not in _LIVE_STATUSES:
            continue
        path = str(payload.get("relative_media_path") or "").strip()
        if not path or path in out:
            # Rows are newest-first, so the first hit for a path is the current one.
            continue
        out[path] = LiveProgress(
            percent=_coerce_percent(payload.get("percent")),
            message=(str(payload.get("message") or "").strip() or None),
            eta_seconds=_coerce_seconds(payload.get("eta_seconds")),
        )
    return out


def stale_cutoff_for_tests() -> Any:
    """Exposed so tests can build rows either side of the staleness boundary."""

    return as_utc(utcnow() - STALE_AFTER)
