"""Stable outcomes and operator-facing strings for ``refiner.file.remux_pass.v1`` (activity + UI)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mediamop.modules.refiner.refiner_remux_rules import RemuxPlan

# Persisted on activity detail JSON — keep aligned with web ``REFINER_FILE_REMUX_PASS_EVENT_TYPE`` consumers.
REMUX_PASS_OUTCOME_LIVE_OUTPUT_WRITTEN = "live_output_written"
REMUX_PASS_OUTCOME_LIVE_SKIPPED_NOT_REQUIRED = "live_skipped_not_required"
REMUX_PASS_OUTCOME_FAILED_BEFORE_EXECUTION = "failed_before_execution"
REMUX_PASS_OUTCOME_FAILED_DURING_EXECUTION = "failed_during_execution"


def summarize_remux_plan(plan: RemuxPlan, *, max_len: int = 600) -> str:
    """Compact, operator-meaningful plan summary (not a full ffmpeg command)."""

    aud = ", ".join(f"#{t.input_index} {t.lang_label or 'und'}" for t in plan.audio) or "none"
    sub = ", ".join(f"#{t.input_index} {t.lang_label or 'und'}" for t in plan.subtitles) or "none"
    ra = "; ".join(plan.removed_audio[:6])
    if len(plan.removed_audio) > 6:
        ra += f" (+{len(plan.removed_audio) - 6} more)"
    rs = "; ".join(plan.removed_subtitles[:6])
    if len(plan.removed_subtitles) > 6:
        rs += f" (+{len(plan.removed_subtitles) - 6} more)"
    parts = [
        f"video copy indices: {plan.video_indices}",
        f"audio out: {aud}",
        f"subtitles out: {sub}",
    ]
    if ra:
        parts.append(f"removed audio: {ra}")
    if rs:
        parts.append(f"removed subs: {rs}")
    s = " | ".join(parts)
    if len(s) > max_len:
        return s[: max_len - 12] + "…(truncated)"
    return s


def remux_pass_activity_title(payload: dict[str, Any]) -> str:
    """One-line activity title — plain language, filename when available."""

    rel = payload.get("relative_media_path")
    name = Path(str(rel)).name if isinstance(rel, str) and rel.strip() else "unknown file"
    outcome = payload.get("outcome")
    if outcome == REMUX_PASS_OUTCOME_LIVE_OUTPUT_WRITTEN:
        return f"{name} was processed successfully"
    if outcome == REMUX_PASS_OUTCOME_LIVE_SKIPPED_NOT_REQUIRED:
        return f"No changes needed for {name}"
    if outcome == REMUX_PASS_OUTCOME_FAILED_DURING_EXECUTION:
        return f"{name} could not be processed"
    if outcome == REMUX_PASS_OUTCOME_FAILED_BEFORE_EXECUTION or payload.get("ok") is False:
        return f"{name} could not be checked"
    return "Refiner file processing finished"


def clip_remux_pass_payload_for_activity(payload: dict[str, Any]) -> dict[str, Any]:
    """Bound ffmpeg argv list so activity JSON stays under typical row limits."""

    out = dict(payload)
    argv = out.get("ffmpeg_argv")
    if isinstance(argv, list) and len(argv) > 64:
        out["ffmpeg_argv"] = list(argv[:64]) + ["…(truncated for activity log)"]
        out["ffmpeg_argv_truncated"] = True
    return out


def remux_pass_result_to_activity_detail(payload: dict[str, Any], *, max_chars: int = 10_000) -> str:
    clipped = clip_remux_pass_payload_for_activity(payload)
    raw = json.dumps(clipped, separators=(",", ":"), ensure_ascii=True)
    return raw[:max_chars]
