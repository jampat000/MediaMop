"""Turn media-manager queue signals into Refiner domain rows that remember who said what.

:mod:`mediamop.modules.refiner.domain` decides *whether* a row blocks a file. It has no
idea which manager the row came from, and should not: it is the one layer that was
already vendor-neutral. So attribution is carried alongside the view here, which is what
lets a blocked-upstream reason say "Deluno (Main) is still importing this file" instead
of naming a product the operator may not even have installed.

Domain applicability is ``any(...)`` over rows, so asking it about one row at a time
gives the same verdict as asking about all of them — and tells us which row it was.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from mediamop.modules.refiner.domain import (
    FileAnchorCandidate,
    RefinerQueueRowView,
    file_is_owned_by_queue,
    should_block_for_upstream,
)
from mediamop.modules.refiner.queue_adapter import map_queue_row_to_refiner_view, queue_dialect_for_scope
from mediamop.platform.media_managers.manager_port import ManagerQueueSignal


@dataclass(frozen=True, slots=True)
class AttributedQueueRow:
    """One mapped queue row, plus the connection that reported it."""

    connection_label: str
    view: RefinerQueueRowView


def attributed_queue_rows(
    signals: Sequence[ManagerQueueSignal],
    *,
    candidate_path: str | None = None,
    candidate_entity_id: int | None = None,
) -> list[AttributedQueueRow]:
    """Map every reported row through its scope dialect, keeping the reporter's name."""

    rows: list[AttributedQueueRow] = []
    for signal in signals:
        if not signal.is_reported:
            continue
        label = signal.connection.label
        for row in signal.rows:
            rows.append(
                AttributedQueueRow(
                    connection_label=label,
                    view=map_queue_row_to_refiner_view(
                        row.payload,
                        queue_dialect_for_scope(row.scope),
                        candidate_path=candidate_path,
                        candidate_entity_id=candidate_entity_id,
                    ),
                )
            )
    return rows


def attributed_rows_for_file(
    signals: Sequence[ManagerQueueSignal],
    *,
    file_path: Path,
) -> list[AttributedQueueRow]:
    """The rows any manager holds against one file on disk."""

    return attributed_queue_rows(signals, candidate_path=str(file_path.resolve()))


def views_of(rows: Sequence[AttributedQueueRow]) -> list[RefinerQueueRowView]:
    return [row.view for row in rows]


def file_is_owned_by_any_manager(
    rows: Sequence[AttributedQueueRow],
    *,
    candidate: FileAnchorCandidate | None = None,
) -> bool:
    return file_is_owned_by_queue(views_of(rows), file_candidate=candidate)


def blocking_connection_label(
    rows: Sequence[AttributedQueueRow],
    *,
    candidate: FileAnchorCandidate | None = None,
) -> str | None:
    """The first connection holding this file open, or ``None`` if none is.

    A block from **any** manager blocks the file, so the first one found is enough to
    explain the wait.
    """

    for row in rows:
        if should_block_for_upstream([row.view], file_candidate=candidate):
            return row.connection_label
    return None


def upstream_block_reason(
    rows: Sequence[AttributedQueueRow],
    *,
    candidate: FileAnchorCandidate | None = None,
) -> str | None:
    """Plain-language reason naming the connection, not the vendor."""

    label = blocking_connection_label(rows, candidate=candidate)
    if label is None:
        return None
    return f"{label} is still importing this file, so MediaMop left it alone for now."


@dataclass(frozen=True, slots=True)
class QueueSignalReport:
    """Which managers were asked, and which of them could not answer.

    ``silent`` is the point of this type. A manager that is unreachable, or that cannot
    report a queue at all, must never be counted as "nothing is importing" — so it is
    counted here instead, and every caller has to decide what to do about it.
    """

    consulted: int
    reported: int
    silent_labels: tuple[str, ...]
    silent_details: tuple[str, ...]

    @property
    def all_reported(self) -> bool:
        return not self.silent_labels

    @property
    def has_any_signal(self) -> bool:
        return self.reported > 0

    def note(self) -> str | None:
        """One sentence for an operator, or ``None`` when every manager answered."""

        if not self.silent_labels:
            return None
        names = ", ".join(self.silent_labels)
        return (
            f"MediaMop could not get an import check from {names}, so it did not treat that as 'nothing is importing'."
        )


def report_for_signals(signals: Sequence[ManagerQueueSignal]) -> QueueSignalReport:
    silent_labels: list[str] = []
    silent_details: list[str] = []
    reported = 0
    for signal in signals:
        if signal.is_reported:
            reported += 1
            continue
        silent_labels.append(signal.connection.label)
        silent_details.append(signal.detail or f"{signal.connection.label} did not answer.")
    return QueueSignalReport(
        consulted=len(signals),
        reported=reported,
        silent_labels=tuple(silent_labels),
        silent_details=tuple(silent_details),
    )


def no_manager_configured_note(media_scope: str) -> str:
    scope_word = "TV episodes" if media_scope == "tv" else "Movies"
    return (
        f"No media manager is connected for {scope_word}, so MediaMop had no import check to make. "
        "Add one on the Media managers settings page if you want that safety check."
    )
