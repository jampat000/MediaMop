"""Per-file ffprobe → plan → optional ffmpeg remux (Refiner ``refiner.file.remux_pass.v1``)."""

from __future__ import annotations

import contextlib
import logging
import os
import shutil
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from mediamop.core.config import MediaMopSettings
from mediamop.modules.refiner.file_remux_pass.paths import resolve_media_file_under_refiner_root
from mediamop.modules.refiner.file_remux_pass.visibility import (
    REMUX_PASS_OUTCOME_FAILED_BEFORE_EXECUTION,
    REMUX_PASS_OUTCOME_FAILED_DURING_EXECUTION,
    REMUX_PASS_OUTCOME_LIVE_OUTPUT_WRITTEN,
    REMUX_PASS_OUTCOME_LIVE_SKIPPED_NOT_REQUIRED,
    REMUX_PASS_OUTCOME_SKIPPED_GUARDRAIL,
    REMUX_PASS_OUTCOME_SOURCE_NOT_READY,
    remux_pass_result_to_activity_detail,
    summarize_remux_plan,
)
from mediamop.modules.refiner.refiner_file_settling import acquire_source_read_guard
from mediamop.modules.refiner.refiner_file_state_service import (
    record_measured_video_dimensions,
    record_output_collision,
)
from mediamop.modules.refiner.refiner_hardware_acceleration import (
    HardwareSettings,
    decide_acceleration,
    detect_acceleration,
    normalize_decode_mode,
    normalize_strictness,
    parse_disabled_vendors,
)
from mediamop.modules.refiner.refiner_movie_output_cleanup import (
    maybe_run_movie_output_folder_cleanup_after_remux,
)
from mediamop.modules.refiner.refiner_output_collision import (
    decide_output_collision,
    normalize_collision_policy,
)
from mediamop.modules.refiner.refiner_path_settings_service import RefinerPathRuntime
from mediamop.modules.refiner.refiner_remux_mux import (
    MediaCompletenessError,
    build_ffmpeg_argv,
    ffprobe_json,
    remux_to_temp_file,
    resolve_ffprobe_ffmpeg,
    validate_media_integrity,
    validate_remux_output,
)
from mediamop.modules.refiner.refiner_remux_rules import (
    PlannedTrack,
    RefinerRulesConfig,
    RemuxPlan,
    attachment_streams,
    default_refiner_remux_rules_config,
    is_refiner_media_candidate,
    is_remux_required,
    plan_remux,
    split_streams,
)
from mediamop.modules.refiner.refiner_remux_track_display import (
    audio_after_line_from_plan,
    audio_before_line_from_probe,
    metadata_removed_line_from_plan,
    subtitle_after_line_from_plan,
    subtitle_before_line_from_probe,
)
from mediamop.modules.refiner.refiner_runner_units import video_dimensions_from_streams
from mediamop.modules.refiner.refiner_sidecar_migration import (
    apply_original_timestamps,
    migrate_sidecars,
    parse_sidecar_patterns,
)
from mediamop.modules.refiner.refiner_tv_output_cleanup import (
    maybe_run_tv_output_season_folder_cleanup_after_remux,
)
from mediamop.modules.refiner.refiner_tv_season_folder_cleanup import (
    handle_tv_cleanup_after_success,
    init_tv_season_cleanup_activity_fields,
)
from mediamop.platform.file_lifecycle.guardrails import bytes_to_mb, check_minimum_free_disk_space
from mediamop.platform.file_lifecycle.mutations import safe_copy_to_final, safe_finalize_file
from mediamop.platform.metrics.service import record_module_savings

logger = logging.getLogger(__name__)


def _fail_before(
    *,
    relative_media_path: str,
    reason: str,
    inspected_source_path: str | None = None,
    **extra: Any,
) -> dict[str, Any]:
    return {
        "ok": False,
        "outcome": REMUX_PASS_OUTCOME_FAILED_BEFORE_EXECUTION,
        "preflight_status": "failed",
        "preflight_reason": reason,
        "reason": reason,
        "relative_media_path": relative_media_path,
        **extra,
        **({"inspected_source_path": inspected_source_path} if inspected_source_path else {}),
    }


def _source_not_ready(
    *,
    relative_media_path: str,
    reason: str,
    inspected_source_path: str | None = None,
) -> dict[str, Any]:
    return {
        "ok": False,
        "outcome": REMUX_PASS_OUTCOME_SOURCE_NOT_READY,
        "retryable_wait": True,
        "preflight_status": "waiting",
        "preflight_reason": reason,
        "reason": reason,
        "relative_media_path": relative_media_path,
        **({"inspected_source_path": inspected_source_path} if inspected_source_path else {}),
    }


def _source_fingerprint(path: Path) -> tuple[int, int, int, int]:
    stat = path.stat()
    return (int(stat.st_dev), int(stat.st_ino), int(stat.st_size), int(stat.st_mtime_ns))


def _assert_source_unchanged(path: Path, expected: tuple[int, int, int, int]) -> None:
    try:
        current = _source_fingerprint(path)
    except OSError as exc:
        raise MediaCompletenessError(
            f"The source could not be rechecked after processing ({exc}), so the staged output was not published."
        ) from exc
    if current != expected:
        raise MediaCompletenessError(
            "The source changed while Refiner was reading it. The staged output was discarded and MediaMop will wait "
            "for the downloader or importer to finish."
        )


def _skip_guardrail(
    *,
    relative_media_path: str,
    reason: str,
    guardrail: str,
    inspected_source_path: str | None = None,
    **extra: Any,
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "ok": True,
        "outcome": REMUX_PASS_OUTCOME_SKIPPED_GUARDRAIL,
        "preflight_status": "skipped",
        "preflight_reason": reason,
        "reason": reason,
        "guardrail": guardrail,
        "relative_media_path": relative_media_path,
        **extra,
    }
    if inspected_source_path is not None:
        data["inspected_source_path"] = inspected_source_path
    return data


def _normalize_media_scope_for_cleanup(raw: str | None) -> str:
    s = (raw or "movie").strip().lower()
    return "tv" if s == "tv" else "movie"


def _pass_through_plan(
    *,
    video: list[dict[str, Any]],
    audio: list[dict[str, Any]],
    subtitles: list[dict[str, Any]],
) -> RemuxPlan:
    """Describe an unchanged file without applying any Refiner selection rules.

    The plan is observability only: pass-through never invokes ffmpeg. Keeping every
    stream in the description makes the processing record truthful about what reached
    the output folder.
    """

    def tags(stream: dict[str, Any]) -> dict[str, Any]:
        value = stream.get("tags")
        return value if isinstance(value, dict) else {}

    def disposition(stream: dict[str, Any]) -> dict[str, Any]:
        value = stream.get("disposition")
        return value if isinstance(value, dict) else {}

    def integer(value: Any) -> int:
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    audio_tracks = [
        PlannedTrack(
            input_index=integer(stream.get("index")),
            lang_label=str(tags(stream).get("language") or "und"),
            forced=bool(disposition(stream).get("forced")),
            default=bool(disposition(stream).get("default")),
            channels=integer(stream.get("channels")),
            bitrate=integer(stream.get("bit_rate")),
            codec_name=str(stream.get("codec_name") or ""),
            kind="audio",
        )
        for stream in audio
    ]
    subtitle_tracks = [
        PlannedTrack(
            input_index=integer(stream.get("index")),
            lang_label=str(tags(stream).get("language") or "und"),
            forced=bool(disposition(stream).get("forced")),
            default=bool(disposition(stream).get("default")),
            kind="subtitle",
        )
        for stream in subtitles
    ]
    return RemuxPlan(
        video_indices=[integer(stream.get("index")) for stream in video],
        audio=audio_tracks,
        subtitles=subtitle_tracks,
        audio_selection_notes=["The operator chose Pass through unchanged, so every stream was preserved."],
    )


def _commit_cleanup_session(cleanup_session: Session | None) -> None:
    """Release a short Refiner metadata transaction before more media work begins.

    Progress and collision notes are useful observability, but they must never make a
    safe file mutation look like a failed remux. The worker owns the final job state;
    this helper only keeps optional metadata writes short and best-effort.
    """

    if cleanup_session is None:
        return
    try:
        cleanup_session.commit()
    except Exception:  # noqa: BLE001 - metadata persistence is deliberately best effort
        logger.warning("Refiner could not commit optional file metadata; continuing the media pass.", exc_info=True)
        cleanup_session.rollback()


def _probe_duration_seconds(probe: dict[str, Any]) -> float | None:
    candidates: list[float] = []
    fmt = probe.get("format")
    if isinstance(fmt, dict):
        with contextlib.suppress(TypeError, ValueError):
            candidates.append(float(fmt.get("duration") or 0))
    streams = probe.get("streams")
    if isinstance(streams, list):
        for stream in streams:
            if not isinstance(stream, dict):
                continue
            with contextlib.suppress(TypeError, ValueError):
                candidates.append(float(stream.get("duration") or 0))
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


def _copy_unchanged_source_to_output(
    *,
    src: Path,
    final: Path,
    mediamop_home: str,
    expected_audio: int,
    expected_duration_seconds: float | None,
    expected_source_fingerprint: tuple[int, int, int, int],
    progress_callback: Callable[[int, int], None] | None = None,
) -> tuple[bool, bool, str]:
    """For already-correct files, still place a copy in the output tree before cleanup."""

    src_resolved = src.resolve()
    final.parent.mkdir(parents=True, exist_ok=True)
    replaced_existing = final.exists()
    if replaced_existing:
        final_resolved = final.resolve()
        if final_resolved == src_resolved:
            raise RuntimeError(
                "Refiner output path resolves to the watched source file; output and watched folders must differ."
            )

    def validate_staged(staged: Path) -> None:
        validate_remux_output(
            staged,
            mediamop_home=mediamop_home,
            expected_audio=expected_audio,
            expected_duration_seconds=expected_duration_seconds,
        )
        _assert_source_unchanged(src_resolved, expected_source_fingerprint)

    # Never hard-link watched input into the output tree. On Linux a downloader can
    # continue writing through its original descriptor after the watched name is
    # removed, which would mutate the output through the shared inode.
    safe_copy_to_final(
        source=src_resolved,
        final=final,
        validate_staged=validate_staged,
        progress_callback=progress_callback,
    )
    return True, replaced_existing, "validated_copy"


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


def _migrate_sidecars_before_cleanup(
    *,
    src: Path,
    final_output_file: Path | None,
    sidecar_patterns: tuple[str, ...],
    preserve_timestamps: bool,
    out: dict[str, Any],
) -> None:
    """Carry configured sidecars to the output, and record whether deletion may proceed.

    Run before any cleanup gate. A sidecar that is not there is not a failure — the
    common case is a release with none — but one that exists and could not be copied
    stops the source folder being deleted, because proceeding would destroy the only
    copy of a file MediaMop was asked to keep (#344).
    """

    out.setdefault("sidecars_migrated", [])
    out.setdefault("sidecars_skipped", [])
    out.setdefault("sidecar_migration_blocked", False)
    out.setdefault("sidecar_migration_blocked_reason", None)
    out.setdefault("original_timestamps_note", None)

    if final_output_file is None or not sidecar_patterns:
        return

    result = migrate_sidecars(
        source_media=src,
        output_media=final_output_file,
        patterns=sidecar_patterns,
        preserve_timestamps=preserve_timestamps,
    )
    out["sidecars_migrated"] = [m.destination.name for m in result.migrated]
    out["sidecars_skipped"] = list(result.skipped)
    if result.blocks_source_deletion:
        out["sidecar_migration_blocked"] = True
        out["sidecar_migration_blocked_reason"] = result.blocking_reason
        logger.warning("Refiner sidecar migration: %s", result.blocking_reason)

    if preserve_timestamps:
        problem = apply_original_timestamps(source_media=src, output_media=final_output_file)
        if problem:
            # Never fatal: the output is correct either way, and refusing a finished
            # remux over a timestamp would be the wrong trade.
            out["original_timestamps_note"] = problem
            logger.info("Refiner timestamps: %s", problem)


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

    # Sidecars travel *before* any deletion gate runs, and a sidecar that exists and
    # could not be copied stops the deletion. Proceeding would destroy the only copy of
    # a file MediaMop was asked to keep (#344).
    if out.get("sidecar_migration_blocked"):
        _init_folder_cleanup_activity_fields(out)
        out["source_deleted_after_success"] = False
        out["source_folder_skip_reason"] = out.get("sidecar_migration_blocked_reason") or (
            "MediaMop did not remove the source folder because a file set to travel with the video could not be copied."
        )
        logger.warning("Refiner cleanup blocked by sidecar migration: %s", out["source_folder_skip_reason"])
        return

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
        out["source_folder_skip_reason"] = (
            "The video file is not under the saved watched folder, so nothing was removed."
        )
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
    cascade: list[str] = out["cascade_folders_deleted"]

    out_dir = Path(path_runtime.output_folder).resolve()
    if not str(path_runtime.output_folder).strip():
        out["output_completeness_check"] = "skipped"
        out["source_folder_skip_reason"] = (
            "No output folder is configured for Movies, so the release folder was not removed."
        )
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


def _run_refiner_file_remux_pass(
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
    refiner_min_input_file_size_mb: int = 0,
    minimum_free_disk_space_mb: int = 0,
    expected_source_fingerprint: tuple[int, int, int, int],
    pass_through_unchanged: bool = False,
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
    try:
        exists = src.exists()
        is_file = src.is_file() if exists else False
        suffix = src.suffix.lower()
    except OSError as exc:
        return _fail_before(
            relative_media_path=relative_media_path,
            reason=f"MediaMop could not inspect this file under the saved watched folder: {exc}",
            inspected_source_path=inspected,
        )
    if not exists:
        return _fail_before(
            relative_media_path=relative_media_path,
            reason=(
                "MediaMop could not find this file under the saved watched folder. "
                "Check the library path or restore the file, then try again."
            ),
            inspected_source_path=inspected,
        )
    if not is_file:
        return _fail_before(
            relative_media_path=relative_media_path,
            reason=(
                "This path is not a regular media file under the saved watched folder. Choose a file, then try again."
            ),
            inspected_source_path=inspected,
        )
    if not is_refiner_media_candidate(src):
        return _fail_before(
            relative_media_path=relative_media_path,
            reason=(
                f"Refiner does not process {suffix or 'this'} files in this pass. "
                "Use a supported media file or update the library's media types, then try again."
            ),
            inspected_source_path=inspected,
        )
    min_size_mb = max(0, int(refiner_min_input_file_size_mb))
    if min_size_mb > 0 and not pass_through_unchanged:
        try:
            source_size_bytes = int(src.stat().st_size)
        except OSError as exc:
            return _fail_before(
                relative_media_path=relative_media_path,
                reason=f"Refiner could not read the source file size: {exc}",
                inspected_source_path=inspected,
            )
        source_size_mb = bytes_to_mb(source_size_bytes)
        if source_size_bytes < min_size_mb * 1024 * 1024:
            return _skip_guardrail(
                relative_media_path=relative_media_path,
                inspected_source_path=inspected,
                guardrail="minimum_input_file_size",
                reason=f"Skipped: file below minimum size ({source_size_mb:.1f} MB < {min_size_mb} MB).",
                source_size_bytes=source_size_bytes,
                source_size_mb=round(source_size_mb, 1),
                minimum_input_file_size_mb=min_size_mb,
                media_scope=scope,
            )
    min_age = max(
        0,
        int(
            settings.refiner_watched_folder_min_file_age_seconds
            if min_file_age_seconds is None
            else min_file_age_seconds
        ),
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
    if not video:
        return _fail_before(
            relative_media_path=relative_media_path,
            reason=(
                "Refiner only processes movie and TV files that contain a video stream. "
                "This file contains no video, so it was rejected before any output was written."
            ),
            inspected_source_path=inspected,
            rejection_kind="no_video_stream",
            media_scope=scope,
            refiner_watched_folder_resolved=str(Path(root).resolve()),
        )
    # Measured once here and recorded, so the *next* enqueue of this file can weight it
    # against the runner budget instead of paying the "undetermined" cost forever (#338).
    measured_width, measured_height = video_dimensions_from_streams(video)
    if cleanup_session is not None and (measured_width is not None or measured_height is not None):
        record_measured_video_dimensions(
            cleanup_session,
            relative_path=relative_media_path,
            video_width=measured_width,
            video_height=measured_height,
        )
        _commit_cleanup_session(cleanup_session)
    duration_seconds = _probe_duration_seconds(probe)
    if os.name != "nt":
        try:
            # POSIX locks are advisory and many Docker bind-mount writers do not take
            # one. Read the complete primary video before mutation so a preallocated or
            # sparse in-progress download cannot look ready from size alone.
            validate_media_integrity(src, mediamop_home=settings.mediamop_home)
            _assert_source_unchanged(src, expected_source_fingerprint)
        except MediaCompletenessError as exc:
            return _source_not_ready(
                relative_media_path=relative_media_path,
                reason=str(exc),
                inspected_source_path=inspected,
            )
    config = rules_config if rules_config is not None else default_refiner_remux_rules_config()
    plan = (
        _pass_through_plan(video=video, audio=audio, subtitles=subs)
        if pass_through_unchanged
        else plan_remux(
            video=video,
            audio=audio,
            subtitles=subs,
            config=config,
            attachments=attachment_streams(probe),
        )
    )
    if plan is None:
        return _fail_before(
            relative_media_path=relative_media_path,
            reason="remux plan could not be built (no retainable audio)",
            inspected_source_path=inspected,
            rejection_kind="no_retainable_audio",
            media_scope=scope,
            refiner_watched_folder_resolved=str(Path(root).resolve()),
        )

    remux_needed = False if pass_through_unchanged else is_remux_required(plan, audio, subs)
    before_a = audio_before_line_from_probe(audio)
    after_a = audio_after_line_from_plan(plan)
    metadata_removed = metadata_removed_line_from_plan(plan)
    before_s = subtitle_before_line_from_probe(subs)
    after_s = subtitle_after_line_from_plan(
        plan,
        remove_all=False if pass_through_unchanged else config.subtitle_mode == "remove_all",
    )

    work_dir = Path(path_runtime.work_folder_effective)
    hardware = None
    argv: list[str] = []
    if not pass_through_unchanged:
        _, ffmpeg_bin = resolve_ffprobe_ffmpeg(mediamop_home=settings.mediamop_home)
        # Decided before the argv is built, because the flags go into it. A device that is
        # busy, absent or not compiled in falls back to software with a reason rather than
        # failing the file (#345).
        hardware = decide_acceleration(
            settings=HardwareSettings(
                mode=normalize_decode_mode(path_runtime.hardware_decode_mode),
                device=path_runtime.hardware_device or "",
                disabled_vendors=parse_disabled_vendors(path_runtime.hardware_disabled_vendors_csv),
                strictness=normalize_strictness(path_runtime.ffmpeg_strictness),
            ),
            report=detect_acceleration(ffmpeg_bin),
        )
        dst_placeholder = work_dir / "planned-ffmpeg-destination-placeholder.mkv"
        argv = build_ffmpeg_argv(
            ffmpeg_bin=ffmpeg_bin, src=src, dst=dst_placeholder, plan=plan, input_flags=hardware.argv_flags
        )

    watched_root = Path(path_runtime.watched_folder).resolve()

    out: dict[str, Any] = {
        "ok": True,
        "outcome": REMUX_PASS_OUTCOME_LIVE_OUTPUT_WRITTEN,
        "relative_media_path": relative_media_path,
        "inspected_source_path": inspected,
        "refiner_watched_folder_resolved": str(watched_root),
        "stream_counts": {"video": len(video), "audio": len(audio), "subtitle": len(subs)},
        "preflight_status": "ok",
        "preflight_reason": (
            "ffprobe completed and the operator's pass-through request was validated"
            if pass_through_unchanged
            else "ffprobe completed and remux plan was evaluated"
        ),
        "preflight_probe_settings": {
            "probe_size_mb": settings.refiner_probe_size_mb,
            "analyze_duration_seconds": settings.refiner_analyze_duration_seconds,
        },
        "plan_summary": summarize_remux_plan(plan),
        "audio_before": before_a,
        "audio_after": after_a,
        "subs_before": before_s,
        "subs_after": after_s,
        "removed_audio": list(plan.removed_audio),
        "removed_subtitles": list(plan.removed_subtitles),
        "removed_images": list(plan.removed_images),
        "removed_attachments": list(plan.removed_attachments),
        "metadata_removed": metadata_removed,
        "after_track_lines_meaning": "Planned output layout for this live pass.",
        "remux_required": remux_needed,
        "pass_through_unchanged": pass_through_unchanged,
        "ffmpeg_argv": [str(x) for x in argv],
        "audio_selection_notes": list(plan.audio_selection_notes),
        "media_scope": scope,
        "source_fingerprint": {
            "device": expected_source_fingerprint[0],
            "inode": expected_source_fingerprint[1],
            "size_bytes": expected_source_fingerprint[2],
            "modified_time_ns": expected_source_fingerprint[3],
        },
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

    collision_policy = normalize_collision_policy(path_runtime.output_collision_policy)
    sidecar_patterns = parse_sidecar_patterns(path_runtime.sidecar_patterns_csv)
    preserve_timestamps = bool(path_runtime.preserve_original_timestamps)

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
        if pass_through_unchanged:
            out["after_track_lines_meaning"] = (
                "No audio, subtitle, or metadata rules were applied because the operator chose Pass through unchanged."
            )
            out["reason"] = (
                "The operator bypassed Refiner rules for this edge case. MediaMop validated and copied the unchanged file "
                "to the output folder before running normal post-success source cleanup."
            )
        else:
            out["after_track_lines_meaning"] = (
                "No ffmpeg run was needed because the file already matched the saved Refiner rules."
            )
            out["reason"] = (
                "The file already matched the saved Refiner rules, so Refiner copied it to the output folder without rewriting it."
            )
        rel_skip = src.resolve().relative_to(watched_root)
        final_skip = out_dir / rel_skip
        disk = check_minimum_free_disk_space(
            target_path=final_skip,
            required_mb=minimum_free_disk_space_mb,
        )
        if not disk.ok:
            return _skip_guardrail(
                relative_media_path=relative_media_path,
                inspected_source_path=inspected,
                guardrail="minimum_free_disk_space",
                reason=disk.message,
                disk_checked_path=str(disk.checked_path),
                disk_free_mb=round(disk.free_mb, 1),
                minimum_free_disk_space_mb=disk.required_mb,
                media_scope=scope,
                refiner_output_folder_resolved=str(out_dir),
                stream_counts=out.get("stream_counts"),
                plan_summary=out.get("plan_summary"),
                audio_before=before_a,
                audio_after=after_a,
                subs_before=before_s,
                subs_after=after_s,
                remux_required=remux_needed,
            )
        # The unchanged-copy path collides exactly like the remux path does, and used to
        # overwrite just as silently.
        skip_collision = decide_output_collision(final=final_skip, source=src, staged=src, policy=collision_policy)
        copy_started_at = time.monotonic()
        last_copy_report = {"percent": -1.0, "at": copy_started_at}

        def report_copy_progress(copied_bytes: int, total_bytes: int) -> None:
            if progress_reporter is None:
                return
            now_monotonic = time.monotonic()
            elapsed = max(0.001, now_monotonic - copy_started_at)
            percent = 100.0 if total_bytes <= 0 else min(100.0, copied_bytes * 100.0 / total_bytes)
            if (
                percent < 100.0
                and percent - last_copy_report["percent"] < 1.0
                and now_monotonic - last_copy_report["at"] < 2.0
            ):
                return
            last_copy_report["percent"] = percent
            last_copy_report["at"] = now_monotonic
            bytes_per_second = copied_bytes / elapsed
            remaining_bytes = max(0, total_bytes - copied_bytes)
            eta_seconds = remaining_bytes / bytes_per_second if bytes_per_second > 0 else None
            progress_reporter(
                {
                    "status": "processing",
                    "percent": percent,
                    "eta_seconds": eta_seconds,
                    "elapsed_seconds": elapsed,
                    "relative_media_path": relative_media_path,
                    "inspected_source_path": inspected,
                    "media_scope": scope,
                    "processed_bytes": copied_bytes,
                    "total_bytes": total_bytes,
                    "speed": f"{bytes_per_second / (1024 * 1024):.1f} MB/s",
                    "message": (
                        "MediaMop is passing this file through unchanged."
                        if pass_through_unchanged
                        else "MediaMop is copying the unchanged file to the output folder."
                    ),
                }
            )

        try:
            if skip_collision.wrote:
                final_skip = skip_collision.destination
                _copied, output_replaced_existing, unchanged_output_method = _copy_unchanged_source_to_output(
                    src=src,
                    final=final_skip,
                    mediamop_home=settings.mediamop_home,
                    expected_audio=len(audio),
                    expected_duration_seconds=duration_seconds,
                    expected_source_fingerprint=expected_source_fingerprint,
                    progress_callback=report_copy_progress,
                )
            else:
                _copied, output_replaced_existing, unchanged_output_method = (
                    False,
                    False,
                    "skipped_by_collision_policy",
                )
        except MediaCompletenessError as exc:
            return _source_not_ready(
                relative_media_path=relative_media_path,
                reason=str(exc),
                inspected_source_path=inspected,
            )
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
        out["output_collision_policy"] = skip_collision.policy
        out["output_collision_action"] = skip_collision.action
        out["output_collision_reason"] = skip_collision.reason
        if cleanup_session is not None:
            record_output_collision(
                cleanup_session,
                relative_path=relative_media_path,
                policy=skip_collision.policy,
                action=skip_collision.action,
                reason=skip_collision.reason,
            )
            _commit_cleanup_session(cleanup_session)
        out["output_copied_without_remux"] = True
        out["unchanged_output_method"] = unchanged_output_method
        out["live_mutations_skipped"] = False
        _migrate_sidecars_before_cleanup(
            src=src,
            final_output_file=final_skip,
            sidecar_patterns=sidecar_patterns,
            preserve_timestamps=preserve_timestamps,
            out=out,
        )
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

    assert hardware is not None
    try:
        work_disk = check_minimum_free_disk_space(
            target_path=work_dir / f".{src.name}.work-preflight",
            required_mb=minimum_free_disk_space_mb,
        )
        if not work_disk.ok:
            return _skip_guardrail(
                relative_media_path=relative_media_path,
                inspected_source_path=inspected,
                guardrail="minimum_free_disk_space",
                reason=work_disk.message,
                disk_checked_path=str(work_disk.checked_path),
                disk_free_mb=round(work_disk.free_mb, 1),
                minimum_free_disk_space_mb=work_disk.required_mb,
                media_scope=scope,
                stream_counts=out.get("stream_counts"),
                plan_summary=out.get("plan_summary"),
                audio_before=before_a,
                audio_after=after_a,
                subs_before=before_s,
                subs_after=after_s,
                remux_required=remux_needed,
            )
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
        try:
            _assert_source_unchanged(src, expected_source_fingerprint)
        except MediaCompletenessError:
            with contextlib.suppress(OSError):
                tmp.unlink(missing_ok=True)
            raise
        rel = src.resolve().relative_to(watched_root)
        final = out_dir / rel
        output_disk = check_minimum_free_disk_space(
            target_path=final,
            required_mb=minimum_free_disk_space_mb,
        )
        if not output_disk.ok:
            with contextlib.suppress(OSError):
                tmp.unlink(missing_ok=True)
            return _skip_guardrail(
                relative_media_path=relative_media_path,
                inspected_source_path=inspected,
                guardrail="minimum_free_disk_space",
                reason=output_disk.message,
                disk_checked_path=str(output_disk.checked_path),
                disk_free_mb=round(output_disk.free_mb, 1),
                minimum_free_disk_space_mb=output_disk.required_mb,
                media_scope=scope,
                refiner_output_folder_resolved=str(out_dir),
                stream_counts=out.get("stream_counts"),
                plan_summary=out.get("plan_summary"),
                audio_before=before_a,
                audio_after=after_a,
                subs_before=before_s,
                subs_after=after_s,
                remux_required=remux_needed,
            )
        final.parent.mkdir(parents=True, exist_ok=True)
        # A collision used to be silent: the existing output was overwritten and the only
        # trace was a note in an activity row that could age out. The policy and the
        # decision are both recorded now (#349).
        collision = decide_output_collision(final=final, source=src, staged=tmp, policy=collision_policy)
        output_replaced_existing = collision.replaced_existing
        if collision.wrote:
            final = collision.destination
            final.parent.mkdir(parents=True, exist_ok=True)
            safe_finalize_file(staged=tmp, final=final)
    except MediaCompletenessError as exc:
        if progress_reporter is not None:
            progress_reporter(
                {
                    "status": "waiting",
                    "percent": None,
                    "eta_seconds": None,
                    "relative_media_path": relative_media_path,
                    "inspected_source_path": inspected,
                    "media_scope": scope,
                    "message": "Refiner is waiting for this file to finish downloading.",
                    "reason": str(exc),
                }
            )
        return _source_not_ready(
            relative_media_path=relative_media_path,
            reason=str(exc),
            inspected_source_path=inspected,
        )
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
    out["hardware_method"] = hardware.method or None
    out["hardware_fell_back_to_software"] = hardware.fell_back_to_software
    out["hardware_reason"] = hardware.reason
    out["output_collision_policy"] = collision.policy
    out["output_collision_action"] = collision.action
    # The reason is written for the person asking "why is there no new output for this
    # file", which is the question a silent collision made unanswerable.
    out["output_collision_reason"] = collision.reason
    if cleanup_session is not None:
        record_output_collision(
            cleanup_session,
            relative_path=relative_media_path,
            policy=collision.policy,
            action=collision.action,
            reason=collision.reason,
        )
        _commit_cleanup_session(cleanup_session)
    if not collision.wrote or output_replaced_existing:
        out["output_replacement_note"] = collision.reason
    out["after_track_lines_meaning"] = (
        "Live remux finished; before = source probe; after = planned disposition (copy remux — "
        "ffprobe of the written file was used for validation only)."
    )
    try:
        _src_sz = int(src.stat().st_size)
        _out_sz = int(final.stat().st_size)
        _saved = _src_sz - _out_sz
        if _saved > 0:
            record_module_savings(module="refiner", bytes_saved=_saved)
    except OSError:
        pass
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
    _migrate_sidecars_before_cleanup(
        src=src,
        final_output_file=final,
        sidecar_patterns=sidecar_patterns,
        preserve_timestamps=preserve_timestamps,
        out=out,
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
    refiner_min_input_file_size_mb: int = 0,
    minimum_free_disk_space_mb: int = 0,
    pass_through_unchanged: bool = False,
) -> dict[str, Any]:
    """Reserve the source against writers for the complete Refiner pass."""

    try:
        source = resolve_media_file_under_refiner_root(
            media_root=path_runtime.watched_folder,
            relative_path=relative_media_path,
        )
    except ValueError:
        # Preserve the core's existing operator-facing path validation result.
        source = None

    if source is None or not source.is_file():
        return _run_refiner_file_remux_pass(
            settings=settings,
            path_runtime=path_runtime,
            relative_media_path=relative_media_path,
            rules_config=rules_config,
            min_file_age_seconds=min_file_age_seconds,
            media_scope=media_scope,
            cleanup_session=cleanup_session,
            current_job_id=current_job_id,
            progress_reporter=progress_reporter,
            refiner_min_input_file_size_mb=refiner_min_input_file_size_mb,
            minimum_free_disk_space_mb=minimum_free_disk_space_mb,
            pass_through_unchanged=pass_through_unchanged,
            expected_source_fingerprint=(0, 0, 0, 0),
        )

    guard, problem = acquire_source_read_guard(source)
    if guard is None:
        return _source_not_ready(
            relative_media_path=relative_media_path,
            reason=problem or "MediaMop is waiting until no other program is writing this file.",
            inspected_source_path=str(source.resolve()),
        )
    with guard:
        try:
            fingerprint = _source_fingerprint(source)
        except OSError as exc:
            return _source_not_ready(
                relative_media_path=relative_media_path,
                reason=f"MediaMop could not read this file safely ({exc}), so it will wait.",
                inspected_source_path=str(source.resolve()),
            )
        return _run_refiner_file_remux_pass(
            settings=settings,
            path_runtime=path_runtime,
            relative_media_path=relative_media_path,
            rules_config=rules_config,
            min_file_age_seconds=min_file_age_seconds,
            media_scope=media_scope,
            cleanup_session=cleanup_session,
            current_job_id=current_job_id,
            progress_reporter=progress_reporter,
            refiner_min_input_file_size_mb=refiner_min_input_file_size_mb,
            minimum_free_disk_space_mb=minimum_free_disk_space_mb,
            pass_through_unchanged=pass_through_unchanged,
            expected_source_fingerprint=fingerprint,
        )


__all__ = [
    "remux_pass_result_to_activity_detail",
    "run_refiner_file_remux_pass",
]
