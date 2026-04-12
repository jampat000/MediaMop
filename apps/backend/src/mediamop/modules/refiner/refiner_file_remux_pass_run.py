"""Per-file ffprobe → plan → optional ffmpeg remux (Refiner ``refiner.file.remux_pass.v1``)."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from mediamop.core.config import MediaMopSettings
from mediamop.modules.refiner.refiner_file_remux_pass_paths import resolve_media_file_under_refiner_root
from mediamop.modules.refiner.refiner_file_remux_pass_visibility import (
    REMUX_PASS_OUTCOME_DRY_RUN_PLANNED,
    REMUX_PASS_OUTCOME_FAILED_BEFORE_EXECUTION,
    REMUX_PASS_OUTCOME_FAILED_DURING_EXECUTION,
    REMUX_PASS_OUTCOME_LIVE_OUTPUT_WRITTEN,
    REMUX_PASS_OUTCOME_LIVE_SKIPPED_NOT_REQUIRED,
    remux_pass_result_to_activity_detail,
    summarize_remux_plan,
)
from mediamop.modules.refiner.refiner_remux_mux import (
    build_ffmpeg_argv,
    ffprobe_json,
    remux_to_temp_file,
    resolve_ffprobe_ffmpeg,
)
from mediamop.modules.refiner.refiner_remux_rules import (
    RefinerRulesConfig,
    is_refiner_media_candidate,
    is_remux_required,
    plan_remux,
    split_streams,
)
from mediamop.modules.refiner.refiner_remux_track_display import (
    audio_after_line_from_plan,
    audio_before_line_from_probe,
    subtitle_after_line_from_plan,
    subtitle_before_line_from_probe,
)


def default_refiner_remux_rules_config() -> RefinerRulesConfig:
    """Sane defaults when MediaMop has no per-operator Refiner rules DB yet (aligned with Fetcher movie defaults)."""

    return RefinerRulesConfig(
        primary_audio_lang="eng",
        secondary_audio_lang="jpn",
        tertiary_audio_lang="",
        default_audio_slot="primary",
        remove_commentary=True,
        subtitle_mode="remove_all",
        subtitle_langs=(),
        preserve_forced_subs=True,
        preserve_default_subs=True,
        audio_preference_mode="preferred_langs_quality",
    )


def _fail_before(
    *,
    relative_media_path: str,
    reason: str,
    inspected_source_path: str | None = None,
) -> dict[str, Any]:
    return {
        "ok": False,
        "outcome": REMUX_PASS_OUTCOME_FAILED_BEFORE_EXECUTION,
        "reason": reason,
        "relative_media_path": relative_media_path,
        **({"inspected_source_path": inspected_source_path} if inspected_source_path else {}),
    }


def run_refiner_file_remux_pass(
    *,
    settings: MediaMopSettings,
    relative_media_path: str,
    dry_run: bool,
) -> dict[str, Any]:
    """Run one pass: probe, plan, operator lines, optional remux.

    ``dry_run`` when True runs ffprobe and planning only (no ffmpeg output write, no source moves).
    """

    root = (settings.refiner_remux_media_root or "").strip()
    if not root:
        return _fail_before(
            relative_media_path=relative_media_path,
            reason="Set MEDIAMOP_REFINER_REMUX_MEDIA_ROOT to an existing directory containing media files.",
        )
    try:
        src = resolve_media_file_under_refiner_root(media_root=root, relative_path=relative_media_path)
    except ValueError as exc:
        return _fail_before(relative_media_path=relative_media_path, reason=str(exc))

    inspected = str(src.resolve())
    if not is_refiner_media_candidate(src):
        return _fail_before(
            relative_media_path=relative_media_path,
            reason="file is not a supported Refiner media candidate for this pass",
            inspected_source_path=inspected,
        )

    try:
        probe = ffprobe_json(src, mediamop_home=settings.mediamop_home)
    except Exception as exc:
        return _fail_before(
            relative_media_path=relative_media_path,
            reason=f"ffprobe failed: {exc}",
            inspected_source_path=inspected,
        )

    video, audio, subs = split_streams(probe)
    config = default_refiner_remux_rules_config()
    plan = plan_remux(video=video, audio=audio, subtitles=subs, config=config)
    if plan is None:
        return _fail_before(
            relative_media_path=relative_media_path,
            reason="remux plan could not be built (no retainable audio)",
            inspected_source_path=inspected,
        )

    remux_needed = is_remux_required(plan, audio, subs)
    before_a = audio_before_line_from_probe(audio)
    after_a = audio_after_line_from_plan(plan)
    before_s = subtitle_before_line_from_probe(subs)
    after_s = subtitle_after_line_from_plan(plan, remove_all=config.subtitle_mode == "remove_all")

    _, ffmpeg_bin = resolve_ffprobe_ffmpeg(mediamop_home=settings.mediamop_home)
    work_dir = Path(settings.mediamop_home).resolve() / "refiner" / "remux_work"
    dst_placeholder = work_dir / "dry-run-ffmpeg-destination-placeholder.mkv"
    argv = build_ffmpeg_argv(ffmpeg_bin=ffmpeg_bin, src=src, dst=dst_placeholder, plan=plan)

    out: dict[str, Any] = {
        "ok": True,
        "outcome": REMUX_PASS_OUTCOME_DRY_RUN_PLANNED,
        "dry_run": dry_run,
        "relative_media_path": relative_media_path,
        "inspected_source_path": inspected,
        "stream_counts": {"video": len(video), "audio": len(audio), "subtitle": len(subs)},
        "plan_summary": summarize_remux_plan(plan),
        "audio_before": before_a,
        "audio_after": after_a,
        "subs_before": before_s,
        "subs_after": after_s,
        "after_track_lines_meaning": (
            "Planned output layout only (dry run) — source file not modified; "
            "\"after\" lines show the selection the live pass would apply."
        ),
        "remux_required": remux_needed,
        "ffmpeg_argv": [str(x) for x in argv],
        "audio_selection_notes": list(plan.audio_selection_notes),
    }

    if dry_run:
        return out

    out["outcome"] = REMUX_PASS_OUTCOME_LIVE_OUTPUT_WRITTEN
    out.pop("after_track_lines_meaning", None)
    out_dir = Path(settings.mediamop_home).resolve() / "refiner" / "remux_output"
    if not remux_needed:
        out["outcome"] = REMUX_PASS_OUTCOME_LIVE_SKIPPED_NOT_REQUIRED
        out["live_mutations_skipped"] = True
        out["after_track_lines_meaning"] = (
            "No ffmpeg run; source file unchanged. Before/after lines compare the file as-is to the "
            "planned layout (they may match when remux was not required)."
        )
        out["reason"] = (
            "streams already match the remux plan; no ffmpeg run and source file left unchanged "
            "(no pass-through copy in this milestone)"
        )
        return out

    work_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        tmp = remux_to_temp_file(src=src, work_dir=work_dir, plan=plan, mediamop_home=settings.mediamop_home)
        final = out_dir / src.name
        if final.exists():
            final.unlink()
        shutil.move(str(tmp), str(final))
    except Exception as exc:
        return {
            "ok": False,
            "outcome": REMUX_PASS_OUTCOME_FAILED_DURING_EXECUTION,
            "reason": str(exc),
            "dry_run": False,
            "relative_media_path": relative_media_path,
            "inspected_source_path": inspected,
            "stream_counts": out.get("stream_counts"),
            "plan_summary": out.get("plan_summary"),
            "audio_before": before_a,
            "audio_after": after_a,
            "subs_before": before_s,
            "subs_after": after_s,
            "remux_required": remux_needed,
            "ffmpeg_argv": [str(x) for x in argv],
            "audio_selection_notes": list(plan.audio_selection_notes),
            "after_track_lines_meaning": (
                "Remux failed partway; lines above were computed before ffmpeg — output file was not committed."
            ),
        }

    out["output_file"] = str(final.resolve())
    out["after_track_lines_meaning"] = (
        "Live remux finished; before = source probe; after = planned disposition (copy remux — "
        "ffprobe of the written file was used for validation only)."
    )
    return out


__all__ = [
    "default_refiner_remux_rules_config",
    "remux_pass_result_to_activity_detail",
    "run_refiner_file_remux_pass",
]
