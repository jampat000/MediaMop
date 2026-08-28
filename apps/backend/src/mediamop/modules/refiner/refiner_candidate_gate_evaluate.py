"""Evaluate a file/release candidate against every media manager covering its scope.

The verdicts are four, not three, and the fourth is the point of this change.
``not_held`` now means what it says — every manager answered, and none of them holds
this candidate. ``no_upstream_signal`` means MediaMop could not get that answer at all,
either because nothing is connected for the scope or because what is connected did not
reply. Those two used to be the same verdict, which is how a Deluno-managed library came
to look permanently clear.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from mediamop.modules.refiner.domain import FileAnchorCandidate
from mediamop.modules.refiner.manager_queue_signals import (
    attributed_queue_rows,
    blocking_connection_label,
    file_is_owned_by_any_manager,
    no_manager_configured_note,
    report_for_signals,
)
from mediamop.platform.media_managers.manager_port import ManagerQueueSignal, MediaScope

Verdict = Literal["proceed", "wait_upstream", "not_held", "no_upstream_signal"]


@dataclass(frozen=True, slots=True)
class RefinerCandidateGateOutcome:
    """Structured result for operators and activity (plain-language reasons)."""

    verdict: Verdict
    owned: bool
    blocked_upstream: bool
    queue_row_count: int
    media_scope: MediaScope
    managers_consulted: int
    managers_reporting: int
    managers_without_queue_signal: tuple[str, ...]
    blocked_by_connection: str | None
    reasons: tuple[str, ...]


def evaluate_refiner_candidate_gate_from_manager_signals(
    *,
    media_scope: MediaScope,
    signals: Sequence[ManagerQueueSignal],
    release_title: str,
    release_year: int | None,
    output_path: str | None,
    entity_id: int | None,
) -> RefinerCandidateGateOutcome:
    """Map every reported row with the same candidate anchors Refiner uses elsewhere, then apply domain."""

    report = report_for_signals(signals)
    rows = attributed_queue_rows(
        signals,
        media_scope=media_scope,
        candidate_path=output_path,
        candidate_entity_id=entity_id,
    )
    candidate = FileAnchorCandidate(title=release_title, year=release_year)
    owned = file_is_owned_by_any_manager(rows, candidate=candidate)
    blocked_by = blocking_connection_label(rows, candidate=candidate)
    row_count = len(rows)

    def _outcome(verdict: Verdict, *reasons: str) -> RefinerCandidateGateOutcome:
        collected = list(reasons)
        note = report.note()
        if note:
            collected.append(note)
        return RefinerCandidateGateOutcome(
            verdict=verdict,
            owned=owned,
            blocked_upstream=blocked_by is not None,
            queue_row_count=row_count,
            media_scope=media_scope,
            managers_consulted=report.consulted,
            managers_reporting=report.reported,
            managers_without_queue_signal=report.silent_labels,
            blocked_by_connection=blocked_by,
            reasons=tuple(collected),
        )

    if report.consulted == 0:
        return _outcome("no_upstream_signal", no_manager_configured_note(media_scope))

    if not report.has_any_signal:
        return _outcome(
            "no_upstream_signal",
            "No connected media manager could say what it is importing, so MediaMop has no upstream check "
            "for this candidate. That is not the same as an empty queue.",
        )

    if row_count == 0:
        return _outcome(
            "not_held",
            "Every media manager that answered reported an empty queue, so nothing upstream holds this candidate.",
        )

    if not owned:
        return _outcome(
            "not_held",
            "No queue row applies to this candidate by path, id, or title/year anchor rules.",
        )

    if blocked_by is not None:
        return _outcome(
            "wait_upstream",
            f"{blocked_by} is still importing this file, so MediaMop treats this candidate as held upstream.",
        )

    return _outcome(
        "proceed",
        "A media manager holds this candidate, but no manager reports it in an active upstream or download "
        "state, so it is not waiting on an import.",
    )
