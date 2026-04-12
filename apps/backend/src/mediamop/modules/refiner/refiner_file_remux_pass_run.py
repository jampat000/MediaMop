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
from mediamop.modules.refiner.refiner_path_settings_service import RefinerPathRuntime
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


def _source_file_eligible_for_automatic_delete(*, src: Path, watched_root: Path) -> bool:
    """Manual family: only delete the operator-resolved file when it sits under the configured watched folder."""

    try:
        src.resolve().relative_to(watched_root.resolve())
    except ValueError:
        return False
    return src.is_file()


def _maybe_delete_source_after_success(*, src: Path, watched_root: Path, out: dict[str, Any]) -> None:
    if not _source_file_eligible_for_automatic_delete(src=src, watched_root=watched_root):
        out["source_deleted_after_success"] = False
        out["source_cleanup_note"] = (
            "Source file was not deleted because it did not resolve under the saved Refiner watched folder."
        )
        return
    try:
        src.unlink()
        out["source_deleted_after_success"] = True
    except OSError as exc:
        out["source_deleted_after_success"] = False
        out["source_cleanup_note"] = f"Source deletion was skipped after success due to an OS error: {exc}"


def run_refiner_file_remux_pass(
    *,
    settings: MediaMopSettings,
    path_runtime: RefinerPathRuntime,
    relative_media_path: str,
    dry_run: bool,
) -> dict[str, Any]:
    """Run one pass: probe, plan, operator lines, optional remux.

    ``dry_run`` when True runs ffprobe and planning only (no ffmpeg output write, no source deletion).
    Live passes use saved Refiner work/temp and output folders from ``path_runtime`` (no fixed home subpaths).
    """

    root = path_runtime.watched_folder
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
    work_dir = Path(path_runtime.work_folder_effective)
    dst_placeholder = work_dir / "dry-run-ffmpeg-destination-placeholder.mkv"
    argv = build_ffmpeg_argv(ffmpeg_bin=ffmpeg_bin, src=src, dst=dst_placeholder, plan=plan)

    watched_root = Path(path_runtime.watched_folder).resolve()

    out: dict[str, Any] = {
        "ok": True,
        "outcome": REMUX_PASS_OUTCOME_DRY_RUN_PLANNED,
        "dry_run": dry_run,
        "relative_media_path": relative_media_path,
        "inspected_source_path": inspected,
        "refiner_watched_folder_resolved": str(watched_root),
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
    out_dir = Path(path_runtime.output_folder).resolve()

    if path_runtime.work_folder_is_default:
        work_dir.mkdir(parents=True, exist_ok=True)
    elif not work_dir.is_dir():
        return _fail_before(
            relative_media_path=relative_media_path,
            reason="Refiner work/temp folder is missing on disk (custom path must exist before a live pass).",
            inspected_source_path=inspected,
        )

    if not remux_needed:
        out["outcome"] = REMUX_PASS_OUTCOME_LIVE_SKIPPED_NOT_REQUIRED
        out["live_mutations_skipped"] = True
        out["refiner_output_folder_resolved"] = str(out_dir)
        out["after_track_lines_meaning"] = (
            "No ffmpeg run; before/after lines compare the file as-is to the planned layout "
            "(they may match when remux was not required)."
        )
        out["reason"] = (
            "Streams already match the remux plan; no ffmpeg run in this pass. "
            "On success, the source file under the watched folder may still be removed per Refiner path settings."
        )
        _maybe_delete_source_after_success(src=src, watched_root=watched_root, out=out)
        return out

    try:
        tmp = remux_to_temp_file(src=src, work_dir=work_dir, plan=plan, mediamop_home=settings.mediamop_home)
        rel = src.resolve().relative_to(watched_root)
        final = out_dir / rel
        final.parent.mkdir(parents=True, exist_ok=True)
        output_replaced_existing = False
        if final.exists():
            output_replaced_existing = True
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
            "refiner_watched_folder_resolved": str(watched_root),
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
    out["output_replaced_existing"] = output_replaced_existing
    out["refiner_output_folder_resolved"] = str(out_dir)
    if output_replaced_existing:
        out["output_replacement_note"] = (
            "An existing output file at the same relative path was replaced (default Refiner output collision policy)."
        )
    out["after_track_lines_meaning"] = (
        "Live remux finished; before = source probe; after = planned disposition (copy remux — "
        "ffprobe of the written file was used for validation only)."
    )
    _maybe_delete_source_after_success(src=src, watched_root=watched_root, out=out)
    return out


__all__ = [
    "default_refiner_remux_rules_config",
    "remux_pass_result_to_activity_detail",
    "run_refiner_file_remux_pass",
]
