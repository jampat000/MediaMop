"""Unit tests for supplied cue timeline constraint evaluation (no worker, no DB)."""

from __future__ import annotations

from mediamop.modules.subber.subber_supplied_cue_timeline_constraints_evaluate import (
    evaluate_supplied_cue_timeline_constraints,
)


def test_valid_ordered_non_overlapping_cues() -> None:
    ok, reason, detail = evaluate_supplied_cue_timeline_constraints(
        {"cues": [{"start_sec": 0, "end_sec": 10}, {"start_sec": 10, "end_sec": 20}]},
    )
    assert ok is True
    assert reason is None
    assert detail["cue_count"] == 2


def test_rejects_overlap() -> None:
    ok, reason, _ = evaluate_supplied_cue_timeline_constraints(
        {"cues": [{"start_sec": 0, "end_sec": 10}, {"start_sec": 5, "end_sec": 15}]},
    )
    assert ok is False
    assert reason is not None
    assert "overlap" in reason.lower() or "ordered" in reason.lower()


def test_rejects_when_cues_extend_past_source_duration() -> None:
    ok, reason, _ = evaluate_supplied_cue_timeline_constraints(
        {
            "cues": [{"start_sec": 0, "end_sec": 8}, {"start_sec": 8, "end_sec": 16}],
            "source_duration_sec": 10,
        },
    )
    assert ok is False
    assert reason is not None
    assert "source_duration" in reason.lower()
