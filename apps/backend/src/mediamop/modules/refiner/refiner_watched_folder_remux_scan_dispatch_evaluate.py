"""Ask every media manager covering a scope, then apply Refiner domain rules (no duplicate rules).

The managers are a safety signal, not a permission slip. Refiner still processes files
when no manager is connected, and when the file is not in any manager's active queue.
What changed is that "no answer" is no longer spelled the same way as "nothing is
importing": a manager that could not be reached is reported to the operator, and the
file falls back to the file-settling gates rather than being waved through as clear.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from sqlalchemy.orm import Session

from mediamop.core.config import MediaMopSettings
from mediamop.modules.refiner.domain import FileAnchorCandidate
from mediamop.modules.refiner.manager_queue_signals import (
    AttributedQueueRow,
    QueueSignalReport,
    attributed_rows_for_file,
    blocking_connection_label,
    report_for_signals,
)
from mediamop.platform.media_managers.manager_binding import collect_queue_signals
from mediamop.platform.media_managers.manager_port import ManagerQueueSignal, MediaScope

Verdict = Literal["proceed", "wait_upstream", "not_held"]


@dataclass(frozen=True, slots=True)
class WatchedFileDispatchOutcome:
    """Whether one watched file can be processed, and which connection said otherwise."""

    verdict: Verdict
    blocked_reason: str | None = None
    # The connection holding the file, so the Files screen can name it without
    # re-parsing the prose reason (#334).
    blocked_connection: str | None = None


def merge_queue_views_for_watched_file(
    *,
    signals: Sequence[ManagerQueueSignal],
    media_scope: MediaScope,
    file_path: Path,
) -> list[AttributedQueueRow]:
    """Every manager's rows for one file, within ``media_scope``, still naming who sent each.

    Scope is not optional: a Movies scan must never be held by a manager's in-flight TV
    import, nor a TV scan by a film.
    """

    return attributed_rows_for_file(signals, media_scope=media_scope, file_path=file_path)


def verdict_for_watched_scan_file(
    rows: Sequence[AttributedQueueRow],
    *,
    candidate: FileAnchorCandidate,
) -> WatchedFileDispatchOutcome:
    """Decide whether a watched-folder file can be processed.

    A block from **any** manager blocks the file — two connections covering one library
    is an ordinary 4K-plus-1080p setup, and either of them may be mid-import.
    """

    label = blocking_connection_label(rows, candidate=candidate)
    if label is not None:
        return WatchedFileDispatchOutcome(
            verdict="wait_upstream",
            blocked_reason=f"{label} is still importing this file, so MediaMop left it alone for now.",
            blocked_connection=label,
        )
    return WatchedFileDispatchOutcome(verdict="proceed")


def fetch_manager_queue_signals_for_scan(
    session: Session,
    settings: MediaMopSettings,
    *,
    media_scope: MediaScope,
) -> tuple[tuple[ManagerQueueSignal, ...], QueueSignalReport]:
    """Ask every manager covering ``media_scope``, and say who did not answer.

    Never raises: a manager being down degrades the scan to the file-settling gates, and
    the report is what stops that degradation from being silent.
    """

    signals = collect_queue_signals(session, settings, media_scope=media_scope)
    return signals, report_for_signals(signals)


def evaluate_watched_media_file_for_dispatch(
    *,
    signals: Sequence[ManagerQueueSignal],
    media_scope: MediaScope,
    file_path: Path,
) -> WatchedFileDispatchOutcome:
    """Ownership + upstream blocking using the same :class:`RefinerQueueRowView` rules as the candidate gate."""

    rows = merge_queue_views_for_watched_file(signals=signals, media_scope=media_scope, file_path=file_path)
    candidate = FileAnchorCandidate(title=file_path.stem, year=None)
    return verdict_for_watched_scan_file(rows, candidate=candidate)


def format_scan_summary_for_activity(summary: dict[str, Any]) -> str:
    """JSON activity detail bounded for SQLite activity rows."""

    raw = json.dumps(summary, separators=(",", ":"), ensure_ascii=True)
    return raw[:10_000]
