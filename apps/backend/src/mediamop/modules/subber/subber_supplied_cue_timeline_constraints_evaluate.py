"""Evaluate supplied subtitle cue timeline JSON — clock times only (no files, no OCR, no mux)."""

from __future__ import annotations

from typing import Any


def evaluate_supplied_cue_timeline_constraints(
    payload: dict[str, Any],
) -> tuple[bool, str | None, dict[str, Any]]:
    """Return ``(ok, reason_if_invalid, detail)``.

    Rules (honest scope):

    - ``cues`` is a non-empty list of objects with numeric ``start_sec`` and ``end_sec`` (display interval on a
      notional media clock — not read from any file here).
    - Each cue interval has ``end_sec > start_sec >= 0``.
    - Cues ordered by ``start_sec`` ascending; no overlap; abutting allowed.
    - Optional ``source_duration_sec``: all cues within the window and total displayed span does not exceed it.
    """

    detail: dict[str, Any] = {"cue_count": 0}
    raw_cues = payload.get("cues")
    if not isinstance(raw_cues, list) or len(raw_cues) == 0:
        return False, "payload.cues must be a non-empty list", detail

    cues: list[tuple[float, float]] = []
    for i, item in enumerate(raw_cues):
        if not isinstance(item, dict):
            return False, f"payload.cues[{i}] must be an object", detail
        try:
            start = float(item["start_sec"])
            end = float(item["end_sec"])
        except (KeyError, TypeError, ValueError):
            return False, f"payload.cues[{i}] requires numeric start_sec and end_sec", detail
        if start < 0 or end <= start:
            return False, f"payload.cues[{i}] needs 0 <= start_sec < end_sec", detail
        cues.append((start, end))

    detail["cue_count"] = len(cues)

    for i in range(1, len(cues)):
        prev_end = cues[i - 1][1]
        cur_start = cues[i][0]
        if cur_start < prev_end:
            return False, "cues overlap or are not ordered by start_sec ascending", detail

    src = payload.get("source_duration_sec")
    if src is not None:
        try:
            source_dur = float(src)
        except (TypeError, ValueError):
            return False, "source_duration_sec must be numeric when present", detail
        if source_dur <= 0:
            return False, "source_duration_sec must be positive when present", detail
        total = 0.0
        for start, end in cues:
            if end > source_dur or start > source_dur:
                return False, "cue extends past source_duration_sec", detail
            total += end - start
        if total > source_dur + 1e-9:
            return False, "sum of cue display lengths exceeds source_duration_sec", detail
        detail["source_duration_sec"] = source_dur
        detail["total_cue_span_seconds"] = total

    detail["valid"] = True
    return True, None, detail
