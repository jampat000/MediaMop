"""Per-file ffprobe → plan → optional ffmpeg remux (Refiner ``refiner.file.remux_pass.v1``)."""

from __future__ import annotations

import logging
import shutil
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from mediamop.core.config import MediaMopSettings
from mediamop.modules.refiner.refiner_file_remux_pass_paths import resolve_media_file_under_refiner_root
from mediamop.modules.refiner.refiner_file_remux_pass_visibility import (
    REMUX_PASS_OUTCOME_FAILED_BEFORE_EXECUTION,
    REMUX_PASS_OUTCOME_FAILED_DURING_EXECUTION,
    REMUX_PASS_OUTCOME_LIVE_OUTPUT_WRITTEN,
    REMUX_PASS_OUTCOME_LIVE_SKIPPED_NOT_REQUIRED,
    remux_pass_result_to_activity_detail,
    summarize_remux_plan,
)
from mediamop.modules.refiner.refiner_path_settings_service import RefinerPathRuntime
from mediamop.modules.refiner.refiner_movie_output_cleanup import (
    maybe_run_movie_output_folder_cleanup_after_remux,
)
from mediamop.modules.refiner.refiner_tv_output_cleanup import (
    maybe_run_tv_output_season_folder_cleanup_after_remux,
)
from mediamop.modules.refiner.refiner_tv_season_folder_cleanup import (
    handle_tv_cleanup_after_success,
    init_tv_season_cleanup_activity_fields,
)
from mediamop.modules.refiner.refiner_remux_mux import (
    build_ffmpeg_argv,
    ffprobe_json,
    remux_to_temp_file,
    resolve_ffprobe_ffmpeg,
)
from mediamop.modules.refiner.refiner_remux_rules import (
    RefinerRulesConfig,
    default_refiner_remux_rules_config,
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

logger = logging.getLogger(__name__)


def _fail_before(
    *,
    relative_media_path: str,
    reason: str,
    inspected_source_path: str | None = None,
) -> dict[str, Any]:
    return {
        "ok": False,
        "outcome": REMUX_PASS_OUTCOME_FAILED_BEFORE_EXECUTION,
        "preflight_status": "failed",
        "preflight_reason": reason,
        "reason": reason,
        "relative_media_path": relative_media_path,
        **({"inspected_source_path": inspected_source_path} if inspected_source_path else {}),
    }


def _normalize_media_scope_for_cleanup(raw: str | None) -> str:
    s = (raw or "movie").strip().lower()
    return "tv" if s == "tv" else "movie"


def _probe_duration_seconds(probe: dict[str, Any]) -> float | None:
    candidates: list[float] = []
    fmt = probe.get("format")
    if isinstance(fmt, dict):
        try:
            candidates.append(float(fmt.get("duration")))
        except (TypeError, ValueError):
            pass
    streams = probe.get("streams")
    if isinstance(streams, list):
        for stream in streams:
            if not isinstance(stream, dict):
                continue
            try:
                candidates.append(float(stream.get("duration")))
            except (TypeError, ValueError):
                pass
    valid = [item for item in candidates if item > 0]
    return max(valid) if valid else None


def _check_output_file_completeness(*, output_file: Path, source_file: Path) -> dict[str, Any]:
    """Minimum safety gate: output exists, non-zero, not suspiciously small vs source."""

    if not output_file.is_file():
        return {
            "output_completeness_check": "failed",
            "output_size_bytes": None,
            "source_size_bytes": None,
            "output_completeness_note": "The output file is missing at the path Refiner expected.",
        }
    try:
        out_sz = int(output_file.stat().st_size)
        src_sz = int(source_file.stat().st_size)
    except OSError as exc:
        return {
            "output_completeness_check": "failed",
            "output_size_bytes": None,
            "source_size_bytes": None,
            "output_completeness_note": f"Refiner could not read the file size ({exc}).",
        }
    if out_sz <= 0:
        return {
            "output_completeness_check": "failed",
            "output_size_bytes": out_sz,
            "source_size_bytes": src_sz,
            "output_completeness_note": "The output file is empty (zero bytes).",
        }
    if src_sz > 0 and out_sz < max(1, src_sz // 100):
        return {
            "output_completeness_check": "failed",
            "output_size_bytes": out_sz,
            "source_size_bytes": src_sz,
            "output_completeness_note": (
                "The output file is much smaller than the source (under 1% of source size), "
                "so Refiner skipped removing the release folder as a safety step."
            ),
        }
    return {
        "output_completeness_check": "passed",
        "output_size_bytes": out_sz,
        "source_size_bytes": src_sz,
        "output_completeness_note": None,
    }


def _copy_unchanged_source_to_output(*, src: Path, final: Path) -> tuple[bool, bool]:
    """For already-correct files, still place a copy in the output tree before cleanup."""

    src_resolved = src.resolve()
    final.parent.mkdir(parents=True, exist_ok=True)
    if final.exists():
        final_resolved = final.resolve()
        if final_resolved == src_resolved:
            raise RuntimeError(
                "Refiner output path resolves to the watched source file; output and watched folders must differ."
            )
        final.unlink()
        shutil.copy2(src_resolved, final)
        return True, True
    shutil.copy2(src_resolved, final)
    return True, False


def _cascade_delete_empty_parents(
    *,
    first_parent: Path,
    watched_root: Path,
    cascade_folders_deleted: list[str],
) -> None:
    """Remove empty parents up to but not including watched_root (strictly under root)."""

    root = watched_root.resolve()
    cur = first_parent.resolve()
    while cur != root:
        try:
            cur.relative_to(root)
        except ValueError:
            logger.warning(
                "Refiner Movies cleanup: stopped cascade because folder is outside the watched folder (%s).",
                cur,
            )
            break
        if not cur.is_dir():
            break
        try:
            if any(cur.iterdir()):
                break
        except OSError:
            break
        try:
            cur.rmdir()
            cascade_folders_deleted.append(str(cur))
        except OSError as exc:
            logger.warning(
                "Refiner Movies cleanup: could not remove an empty parent folder (%s): %s",
                cur,
                exc,
            )
            break
        cur = cur.parent


def _delete_movie_folder_contents_then_dir(
    *,
    movie_folder: Path,
) -> tuple[bool, str | None, str | None]:
    """Delete everything under movie_folder then the folder itself. Returns (ok, skip_reason, locked_path)."""

    try:
        shutil.rmtree(movie_folder)
    except OSError as exc:
        locked = getattr(exc, "filename", None)
        if locked:
            msg = (
                f"A file could not be removed because the system reported it is in use or locked: {locked}. "
                "The whole release folder was left in place."
            )
        else:
            msg = f"Refiner could not remove the release folder ({movie_folder}): {exc}"
        logger.warning("Refiner Movies cleanup: %s", msg)
        return False, msg, str(locked) if locked else str(movie_folder)
    return True, None, None


def _init_folder_cleanup_activity_fields(out: dict[str, Any]) -> None:
    out.setdefault("source_folder_deleted", False)
    out.setdefault("source_folder_path", None)
    out.setdefault("source_folder_skip_reason", None)
    out.setdefault("output_completeness_check", None)
    out.setdefault("output_size_bytes", None)
    out.setdefault("source_size_bytes", None)
    out.setdefault("cascade_folders_deleted", [])
    out.setdefault("output_completeness_note", None)


def _handle_refiner_cleanup_after_success(
    *,
    src: Path,
    watched_root: Path,
    out: dict[str, Any],
    media_scope: str | None,
    path_runtime: RefinerPathRuntime,
    final_output_file: Path | None,
    cleanup_session: Session | None,
    settings: MediaMopSettings,
    min_file_age_seconds: int,
    current_job_id: int | None,
) -> None:
    """Movies: optional full release-folder removal + cascade. TV: season-folder cleanup (Pass 1b) or skip."""

    scope = _normalize_media_scope_for_cleanup(media_scope)

    if scope != "movie":
        if scope != "tv":
            return
        if cleanup_session is None:
            init_tv_season_cleanup_activity_fields(out)
            out["tv_season_folder_skip_reason"] = (
                "TV season cleanup needs a database session (internal error). Nothing was removed under the TV watched folder."
            )
            out["tv_episode_check_summary"] = [out["tv_season_folder_skip_reason"]]
            return
        handle_tv_cleanup_after_success(
            session=cleanup_session,
            settings=settings,
            path_runtime=path_runtime,
            src=src,
            watched_root=watched_root,
            out=out,
            min_file_age_seconds=min_file_age_seconds,
            current_job_id=current_job_id,
            remux_context=dict(out),
            final_output_file=final_output_file,
        )
        return

    _init_folder_cleanup_activity_fields(out)

    watched_resolved = watched_root.resolve()
    src_resolved = src.resolve()
    try:
        src_resolved.relative_to(watched_resolved)
    except ValueError:
        out["source_folder_skip_reason"] = "The video file is not under the saved watched folder, so nothing was removed."
        logger.warning("Refiner Movies cleanup: source not under watched root (%s).", src_resolved)
        out["source_deleted_after_success"] = False
        return

    movie_folder = src_resolved.parent
    try:
        movie_folder.relative_to(watched_resolved)
    except ValueError:
        out["source_folder_skip_reason"] = (
            "The release folder would sit outside the watched folder, so Refiner did not change it."
        )
        logger.warning("Refiner Movies cleanup: movie folder outside watched root (%s).", movie_folder)
        out["source_deleted_after_success"] = False
        return

    if movie_folder == watched_resolved:
        out["source_folder_skip_reason"] = (
            "The video file sits directly in the watched folder root, so Refiner does not remove a release folder here."
        )
        logger.warning("Refiner Movies cleanup: immediate parent is watched root (%s).", watched_resolved)
        out["source_deleted_after_success"] = False
        return

    out["source_folder_path"] = str(movie_folder)
    cascade: list[str] = out["cascade_folders_deleted"]  # type: ignore[assignment]

    out_dir = Path(path_runtime.output_folder).resolve()
    if not str(path_runtime.output_folder).strip():
        out["output_completeness_check"] = "skipped"
        out["source_folder_skip_reason"] = "No output folder is configured for Movies, so the release folder was not removed."
        out["output_completeness_note"] = out["source_folder_skip_reason"]
        out["source_deleted_after_success"] = False
        logger.warning("Refiner Movies cleanup: missing output folder configuration.")
        return

    if final_output_file is None:
        expected = out_dir / src_resolved.relative_to(watched_resolved)
        final_output_file = expected

    check = _check_output_file_completeness(output_file=final_output_file, source_file=src_resolved)
    out["output_completeness_check"] = check["output_completeness_check"]
    out["output_size_bytes"] = check["output_size_bytes"]
    out["source_size_bytes"] = check["source_size_bytes"]
    if check.get("output_completeness_note"):
        out["output_completeness_note"] = check["output_completeness_note"]

    if check["output_completeness_check"] != "passed":
        out["source_folder_skip_reason"] = (
            check.get("output_completeness_note")
            or "The output file did not pass the safety check, so the release folder was not removed."
        )
        out["source_deleted_after_success"] = False
        logger.warning("Refiner Movies cleanup: skipped — %s", out["source_folder_skip_reason"])
        return

    ok, skip_reason, _locked_path = _delete_movie_folder_contents_then_dir(movie_folder=movie_folder)
    if not ok:
        out["source_folder_skip_reason"] = skip_reason or "The release folder could not be removed."
        out["source_deleted_after_success"] = False
        out["source_folder_deleted"] = False
        return

    out["source_folder_deleted"] = True
    out["source_deleted_after_success"] = True
    out["source_folder_skip_reason"] = None
    _cascade_delete_empty_parents(
        first_parent=movie_folder.parent,
        watched_root=watched_resolved,
        cascade_folders_deleted=cascade,
    )


def run_refiner_file_remux_pass(
    *,
    settings: MediaMopSettings,
    path_runtime: RefinerPathRuntime,
    relative_media_path: str,
    rules_config: RefinerRulesConfig | None = None,
    min_file_age_seconds: int | None = None,
    media_scope: str | None = "movie",
    cleanup_session: Session | None = None,
    current_job_id: int | None = None,
    progress_reporter: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Run one pass: probe, plan, optional ffmpeg remux, and post-success cleanup.

    ``media_scope`` controls post-success watched-folder cleanup: Movies may remove a whole release folder; TV may remove
    a whole season folder when gates pass (requires ``cleanup_session`` for queue and history checks).
    """

    scope = _normalize_media_scope_for_cleanup(media_scope)
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
    min_age = max(
        0,
        int(settings.refiner_watched_folder_min_file_age_seconds if min_file_age_seconds is None else min_file_age_seconds),
    )
    if min_age > 0:
        try:
            age_s = time.time() - float(src.stat().st_mtime)
        except OSError:
            age_s = -1
        if age_s < min_age:
            return _fail_before(
                relative_media_path=relative_media_path,
                reason=(
                    "file was modified too recently for Refiner safety guardrails "
                    f"(minimum age {min_age}s, current age {max(0, int(age_s))}s)"
                ),
                inspected_source_path=inspected,
            )

    try:
        probe = ffprobe_json(
            src,
            mediamop_home=settings.mediamop_home,
            probe_size_mb=settings.refiner_probe_size_mb,
            analyze_duration_seconds=settings.refiner_analyze_duration_seconds,
        )
    except Exception as exc:
        return _fail_before(
            relative_media_path=relative_media_path,
            reason=f"ffprobe failed: {exc}",
            inspected_source_path=inspected,
        )

    video, audio, subs = split_streams(probe)
    duration_seconds = _probe_duration_seconds(probe)
    config = rules_config if rules_config is not None else default_refiner_remux_rules_config()
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
    dst_placeholder = work_dir / "planned-ffmpeg-destination-placeholder.mkv"
    argv = build_ffmpeg_argv(ffmpeg_bin=ffmpeg_bin, src=src, dst=dst_placeholder, plan=plan)

    watched_root = Path(path_runtime.watched_folder).resolve()

    out: dict[str, Any] = {
        "ok": True,
        "outcome": REMUX_PASS_OUTCOME_LIVE_OUTPUT_WRITTEN,
        "relative_media_path": relative_media_path,
        "inspected_source_path": inspected,
        "refiner_watched_folder_resolved": str(watched_root),
        "stream_counts": {"video": len(video), "audio": len(audio), "subtitle": len(subs)},
        "preflight_status": "ok",
        "preflight_reason": "ffprobe completed and remux plan was evaluated",
        "preflight_probe_settings": {
            "probe_size_mb": settings.refiner_probe_size_mb,
            "analyze_duration_seconds": settings.refiner_analyze_duration_seconds,
        },
        "plan_summary": summarize_remux_plan(plan),
        "audio_before": before_a,
        "audio_after": after_a,
        "subs_before": before_s,
        "subs_after": after_s,
        "after_track_lines_meaning": "Planned output layout for this live pass.",
        "remux_required": remux_needed,
        "ffmpeg_argv": [str(x) for x in argv],
        "audio_selection_notes": list(plan.audio_selection_notes),
        "media_scope": scope,
    }

    def _run_scope_output_cleanup(*, final_output_file: Path | None) -> None:
        if scope == "tv":
            maybe_run_tv_output_season_folder_cleanup_after_remux(
                session=cleanup_session,
                settings=settings,
                path_runtime=path_runtime,
                watched_root=watched_root,
                src=src,
                final_output_file=final_output_file,
                relative_media_path=relative_media_path,
                current_job_id=current_job_id,
                media_scope=scope,
                out=out,
            )
            return
        maybe_run_movie_output_folder_cleanup_after_remux(
            session=cleanup_session,
            settings=settings,
            path_runtime=path_runtime,
            watched_root=watched_root,
            src=src,
            final_output_file=final_output_file,
            relative_media_path=relative_media_path,
            current_job_id=current_job_id,
            media_scope=scope,
            out=out,
        )

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
        out["refiner_output_folder_resolved"] = str(out_dir)
        out["after_track_lines_meaning"] = (
            "No ffmpeg run was needed because the file already matched the saved Refiner rules."
        )
        out["reason"] = (
            "The file already matched the saved Refiner rules, so Refiner copied it to the output folder without rewriting it."
        )
        rel_skip = src.resolve().relative_to(watched_root)
        final_skip = out_dir / rel_skip
        try:
            _copied, output_replaced_existing = _copy_unchanged_source_to_output(src=src, final=final_skip)
        except Exception as exc:
            if progress_reporter is not None:
                progress_reporter(
                    {
                        "status": "failed",
                        "percent": None,
                        "eta_seconds": None,
                        "relative_media_path": relative_media_path,
                        "inspected_source_path": inspected,
                        "media_scope": scope,
                        "message": "Refiner could not copy this unchanged file to the output folder.",
                        "reason": str(exc),
                    }
                )
            return {
                "ok": False,
                "outcome": REMUX_PASS_OUTCOME_FAILED_DURING_EXECUTION,
                "preflight_status": "ok",
                "preflight_reason": "ffprobe completed and remux plan was evaluated",
                "reason": str(exc),
                "relative_media_path": relative_media_path,
                "inspected_source_path": inspected,
                "refiner_watched_folder_resolved": str(watched_root),
                "refiner_output_folder_resolved": str(out_dir),
                "stream_counts": out.get("stream_counts"),
                "plan_summary": out.get("plan_summary"),
                "audio_before": before_a,
                "audio_after": after_a,
                "subs_before": before_s,
                "subs_after": after_s,
                "remux_required": remux_needed,
                "ffmpeg_argv": [str(x) for x in argv],
                "audio_selection_notes": list(plan.audio_selection_notes),
            }
        out["output_file"] = str(final_skip.resolve())
        out["output_replaced_existing"] = output_replaced_existing
        out["output_copied_without_remux"] = True
        out["live_mutations_skipped"] = False
        _handle_refiner_cleanup_after_success(
            src=src,
            watched_root=watched_root,
            out=out,
            media_scope=media_scope,
            path_runtime=path_runtime,
            final_output_file=final_skip,
            cleanup_session=cleanup_session,
            settings=settings,
            min_file_age_seconds=min_age,
            current_job_id=current_job_id,
        )
        _run_scope_output_cleanup(final_output_file=final_skip)
        return out

    try:
        if progress_reporter is not None:
            progress_reporter(
                {
                    "status": "processing",
                    "percent": 0.0,
                    "eta_seconds": None,
                    "elapsed_seconds": 0,
                    "relative_media_path": relative_media_path,
                    "inspected_source_path": inspected,
                    "media_scope": scope,
                    "stream_counts": out.get("stream_counts"),
                    "duration_seconds": duration_seconds,
                    "message": "Refiner has started writing the cleaned-up file.",
                }
            )
        tmp = remux_to_temp_file(
            src=src,
            work_dir=work_dir,
            plan=plan,
            mediamop_home=settings.mediamop_home,
            duration_seconds=duration_seconds,
            progress_callback=(
                None
                if progress_reporter is None
                else lambda update: progress_reporter(
                    {
                        "status": "processing",
                        "relative_media_path": relative_media_path,
                        "inspected_source_path": inspected,
                        "media_scope": scope,
                        "stream_counts": out.get("stream_counts"),
                        "duration_seconds": duration_seconds,
                        "message": "Refiner is writing the cleaned-up file.",
                        **update,
                    }
                )
            ),
        )
        rel = src.resolve().relative_to(watched_root)
        final = out_dir / rel
        final.parent.mkdir(parents=True, exist_ok=True)
        output_replaced_existing = False
        if final.exists():
            output_replaced_existing = True
            final.unlink()
        shutil.move(str(tmp), str(final))
    except Exception as exc:
        if progress_reporter is not None:
            progress_reporter(
                {
                    "status": "failed",
                    "percent": None,
                    "eta_seconds": None,
                    "relative_media_path": relative_media_path,
                    "inspected_source_path": inspected,
                    "media_scope": scope,
                    "message": "Refiner could not finish this file.",
                    "reason": str(exc),
                }
            )
        return {
            "ok": False,
            "outcome": REMUX_PASS_OUTCOME_FAILED_DURING_EXECUTION,
            "preflight_status": "ok",
            "preflight_reason": "ffprobe completed and remux plan was evaluated",
            "reason": str(exc),
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
    if progress_reporter is not None:
        progress_reporter(
            {
                "status": "finishing",
                "percent": 100.0,
                "eta_seconds": 0,
                "relative_media_path": relative_media_path,
                "inspected_source_path": inspected,
                "output_file": str(final.resolve()),
                "media_scope": scope,
                "message": "The cleaned-up file was written. Refiner is doing final safety checks.",
            }
    )
    _handle_refiner_cleanup_after_success(
        src=src,
        watched_root=watched_root,
        out=out,
        media_scope=media_scope,
        path_runtime=path_runtime,
        final_output_file=final,
        cleanup_session=cleanup_session,
        settings=settings,
        min_file_age_seconds=min_age,
        current_job_id=current_job_id,
    )
    _run_scope_output_cleanup(final_output_file=final)
    if progress_reporter is not None:
        progress_reporter(
            {
                "status": "finished",
                "percent": 100.0,
                "eta_seconds": 0,
                "relative_media_path": relative_media_path,
                "inspected_source_path": inspected,
                "output_file": str(final.resolve()),
                "media_scope": scope,
                "message": "Refiner finished processing this file.",
            }
        )
    return out


__all__ = [
    "remux_pass_result_to_activity_detail",
    "run_refiner_file_remux_pass",
]
