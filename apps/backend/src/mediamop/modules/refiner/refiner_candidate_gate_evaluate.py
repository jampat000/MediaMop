"""Evaluate a file/release candidate against live queue rows using Refiner domain rules."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from mediamop.modules.refiner.domain import (
    FileAnchorCandidate,
    RefinerQueueRowView,
    file_is_owned_by_queue,
    should_block_for_upstream,
)
from mediamop.modules.refiner.radarr_queue_adapter import map_radarr_queue_row_to_refiner_view
from mediamop.modules.refiner.sonarr_queue_adapter import map_sonarr_queue_row_to_refiner_view

Verdict = Literal["proceed", "wait_upstream", "not_held"]


@dataclass(frozen=True, slots=True)
class RefinerCandidateGateOutcome:
    """Structured result for operators and activity (plain-language reasons)."""

    verdict: Verdict
    owned: bool
    blocked_upstream: bool
    queue_row_count: int
    target: Literal["radarr", "sonarr"]
    reasons: tuple[str, ...]


def evaluate_refiner_candidate_gate_from_queue_rows(
    *,
    target: Literal["radarr", "sonarr"],
    queue_rows: Sequence[Mapping[str, Any]],
    release_title: str,
    release_year: int | None,
    output_path: str | None,
    movie_id: int | None,
    series_id: int | None,
) -> RefinerCandidateGateOutcome:
    """Map each live queue row with the same candidate anchors Refiner uses elsewhere, then apply domain."""

    views: list[RefinerQueueRowView] = []
    for row in queue_rows:
        if target == "radarr":
            views.append(
                map_radarr_queue_row_to_refiner_view(
                    row,
                    candidate_path=output_path,
                    candidate_movie_id=movie_id,
                ),
            )
        else:
            views.append(
                map_sonarr_queue_row_to_refiner_view(
                    row,
                    candidate_path=output_path,
                    candidate_series_id=series_id,
                ),
            )

    candidate = FileAnchorCandidate(title=release_title, year=release_year)
    owned = file_is_owned_by_queue(views, file_candidate=candidate)
    blocked = should_block_for_upstream(views, file_candidate=candidate)
    n = len(views)
    reasons: list[str] = []

    if n == 0:
        reasons.append("Live download queue is empty; nothing to match against.")
        return RefinerCandidateGateOutcome(
            verdict="not_held",
            owned=False,
            blocked_upstream=False,
            queue_row_count=0,
            target=target,
            reasons=tuple(reasons),
        )

    if not owned:
        reasons.append(
            "No queue row applies to this candidate by path, id, or title/year anchor rules.",
        )
        return RefinerCandidateGateOutcome(
            verdict="not_held",
            owned=False,
            blocked_upstream=blocked,
            queue_row_count=n,
            target=target,
            reasons=tuple(reasons),
        )

    if blocked:
        reasons.append(
            "Refiner treats this candidate as held by the queue, and an applicable row is in an active upstream or download state without import-wait suppression.",
        )
        return RefinerCandidateGateOutcome(
            verdict="wait_upstream",
            owned=True,
            blocked_upstream=True,
            queue_row_count=n,
            target=target,
            reasons=tuple(reasons),
        )

    reasons.append(
        "Refiner treats this candidate as held by the queue and not blocked for upstream/download wait.",
    )
    return RefinerCandidateGateOutcome(
        verdict="proceed",
        owned=True,
        blocked_upstream=False,
        queue_row_count=n,
        target=target,
        reasons=tuple(reasons),
    )
