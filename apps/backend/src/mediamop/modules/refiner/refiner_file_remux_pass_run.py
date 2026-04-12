"""Per-file ffprobe → plan → optional ffmpeg remux (Refiner ``refiner.file.remux_pass.v1``)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from mediamop.core.config import MediaMopSettings
from mediamop.modules.refiner.refiner_file_remux_pass_paths import resolve_media_file_under_refiner_root
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
        return {
            "ok": False,
            "reason": "Set MEDIAMOP_REFINER_REMUX_MEDIA_ROOT to an existing directory containing media files.",
        }
    try:
        src = resolve_media_file_under_refiner_root(media_root=root, relative_path=relative_media_path)
    except ValueError as exc:
        return {"ok": False, "reason": str(exc)}

    if not is_refiner_media_candidate(src):
        return {"ok": False, "reason": "file is not a supported Refiner media candidate for this pass"}

    try:
        probe = ffprobe_json(src, mediamop_home=settings.mediamop_home)
    except Exception as exc:
        return {"ok": False, "reason": f"ffprobe failed: {exc}"}

    video, audio, subs = split_streams(probe)
    config = default_refiner_remux_rules_config()
    plan = plan_remux(video=video, audio=audio, subtitles=subs, config=config)
    if plan is None:
        return {"ok": False, "reason": "remux plan could not be built (no retainable audio)"}

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
        "dry_run": dry_run,
        "relative_media_path": relative_media_path,
        "audio_before": before_a,
        "audio_after": after_a,
        "subs_before": before_s,
        "subs_after": after_s,
        "remux_required": remux_needed,
        "ffmpeg_argv": [str(x) for x in argv],
        "audio_selection_notes": list(plan.audio_selection_notes),
    }

    if dry_run:
        return out

    out_dir = Path(settings.mediamop_home).resolve() / "refiner" / "remux_output"
    if not remux_needed:
        out["live_mutations_skipped"] = True
        out["reason"] = (
            "streams already match the remux plan; no ffmpeg run and source file left unchanged "
            "(no pass-through copy in this milestone)"
        )
        return out

    work_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    tmp = remux_to_temp_file(src=src, work_dir=work_dir, plan=plan, mediamop_home=settings.mediamop_home)
    final = out_dir / src.name
    if final.exists():
        final.unlink()
    shutil.move(str(tmp), str(final))
    out["output_file"] = str(final.resolve())
    return out


def remux_pass_result_to_activity_detail(payload: dict[str, Any], *, max_chars: int = 10_000) -> str:
    raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=True)
    return raw[:max_chars]
