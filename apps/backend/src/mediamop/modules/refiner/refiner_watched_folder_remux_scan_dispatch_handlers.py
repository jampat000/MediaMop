"""In-process Refiner worker handler for ``refiner.watched_folder.remux_scan_dispatch.v1``."""

from __future__ import annotations

import json
import logging
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from mediamop.core.config import MediaMopSettings
from mediamop.modules.refiner.file_remux_pass.job_kinds import REFINER_FILE_REMUX_PASS_JOB_KIND
from mediamop.modules.refiner.jobs_ops import refiner_enqueue_or_get_job
from mediamop.modules.refiner.refiner_file_state_service import (
    decide_file_state,
    library_in_schedule_window,
    record_file_state,
)
from mediamop.modules.refiner.refiner_library_service import resolve_library
from mediamop.modules.refiner.refiner_operator_settings_service import ensure_refiner_operator_settings_row
from mediamop.modules.refiner.refiner_path_settings_service import resolve_refiner_path_runtime_for_remux
from mediamop.modules.refiner.refiner_remux_rules import refiner_media_extensions_sorted
from mediamop.modules.refiner.refiner_watched_folder_remux_scan_dispatch_evaluate import (
    evaluate_watched_media_file_for_dispatch,
    fetch_manager_queue_signals_for_scan,
)
from mediamop.modules.refiner.refiner_watched_folder_remux_scan_dispatch_ops import (
    iter_watched_folder_media_candidates,
    refiner_active_remux_pass_exists_for_relative_path,
    refiner_completed_remux_output_exists_for_relative_path,
    relative_posix_path_under_watched,
    retry_completed_movie_source_cleanup,
)
from mediamop.modules.refiner.worker_loop import RefinerJobWorkContext
from mediamop.platform.media_managers.manager_port import MediaScope

logger = logging.getLogger(__name__)


def _parse_job_payload(payload_json: str | None) -> dict[str, Any]:
    if not payload_json or not payload_json.strip():
        return {}
    data = json.loads(payload_json)
    if not isinstance(data, dict):
        msg = "watched-folder remux scan dispatch payload must be a JSON object"
        raise ValueError(msg)
    return data


def make_refiner_watched_folder_remux_scan_dispatch_handler(
    settings: MediaMopSettings,
    session_factory: sessionmaker[Session],
) -> Callable[[RefinerJobWorkContext], None]:
    """Scan saved watched folder, classify each media file against every media manager covering the scope, optionally enqueue remux."""

    def _run(ctx: RefinerJobWorkContext) -> None:
        body = _parse_job_payload(ctx.payload_json)
        enqueue_remux_jobs = bool(body.get("enqueue_remux_jobs", False))
        scan_trigger = body.get("scan_trigger", "manual")
        if scan_trigger not in ("manual", "periodic"):
            scan_trigger = "manual"
        media_scope_raw = body.get("media_scope", "movie")
        media_scope: MediaScope = "tv" if media_scope_raw == "tv" else "movie"

        with session_factory() as session:
            op_settings = ensure_refiner_operator_settings_row(session)
            rt, path_err = resolve_refiner_path_runtime_for_remux(
                session,
                settings,
                media_scope=media_scope,
            )
        if path_err is not None or rt is None:
            raise ValueError(path_err or "Refiner path settings are incomplete for this scan.")

        watched_root = rt.watched_folder
        with session_factory() as manager_session:
            signals, signal_report = fetch_manager_queue_signals_for_scan(
                manager_session,
                settings,
                media_scope=media_scope,
            )

        with session_factory() as library_session:
            library = resolve_library(library_session, media_scope=media_scope)
            in_window = library_in_schedule_window(library_session, library) if library is not None else True

        watched_path = Path(watched_root)
        candidates = iter_watched_folder_media_candidates(
            watched_path,
            min_file_age_seconds=op_settings.min_file_age_seconds,
        )
        files = candidates.files

        sample_paths: list[str] = []
        upstream_block_reasons: list[str] = []
        summary: dict[str, Any] = {
            "job_id": ctx.id,
            "scan_trigger": scan_trigger,
            "media_scope": media_scope,
            "scan_result_label": "watched_folder_checked",
            "watched_folder_resolved": watched_root,
            "enqueue_remux_jobs": enqueue_remux_jobs,
            "min_file_age_seconds": op_settings.min_file_age_seconds,
            "minimum_input_file_size_mb": op_settings.refiner_min_input_file_size_mb,
            "managers_consulted": signal_report.consulted,
            "managers_reporting": signal_report.reported,
            "manager_queue_row_count": sum(len(s.rows) for s in signals if s.is_reported),
            "managers_without_queue_signal": list(signal_report.silent_labels),
            "manager_queue_signal_notes": list(signal_report.silent_details),
            "upstream_block_reasons": upstream_block_reasons,
            "media_candidates_seen": len(files),
            "ignored_unsupported_type": candidates.ignored_unsupported_type,
            "ignored_unsupported_extensions": list(candidates.ignored_unsupported_extensions),
            "media_extensions_applied": list(refiner_media_extensions_sorted()),
            "files_withheld": 0,
            "verdict_proceed": 0,
            "verdict_wait_upstream": 0,
            "verdict_not_held": 0,
            "remux_jobs_enqueued": 0,
            "skipped_duplicate_same_scan": 0,
            "skipped_duplicate_active_queue": 0,
            "skipped_existing_completed_output": 0,
            "completed_source_cleanup_retried": 0,
            "completed_source_cleanup_retry_deleted": 0,
            "completed_source_cleanup_retry_failed": 0,
            "skipped_below_minimum_file_size": 0,
            "user_message": "",
            "waiting_message": None,
            "enqueued_relative_paths_sample": sample_paths,
        }

        rel_this_run: set[str] = set()
        sample_cap = 32

        with session_factory() as session, session.begin():
            for file_path in files:
                min_size_mb = max(0, int(op_settings.refiner_min_input_file_size_mb))
                if min_size_mb > 0:
                    try:
                        size_bytes = int(file_path.stat().st_size)
                    except OSError:
                        logger.debug(
                            "Refiner scan skipped size check because file metadata could not be read: %s", file_path
                        )
                        continue
                    if size_bytes < min_size_mb * 1024 * 1024:
                        summary["skipped_below_minimum_file_size"] += 1
                        logger.debug(
                            "Refiner scan skipped %s because it is below the minimum input size (%s MB).",
                            file_path,
                            min_size_mb,
                        )
                        continue

                outcome = evaluate_watched_media_file_for_dispatch(
                    signals=signals,
                    media_scope=media_scope,
                    file_path=file_path,
                )
                # Record why this file is or is not being worked on. Until now the reason
                # existed only as a local variable and the operator saw nothing (#334).
                if library is not None:
                    rel_for_state = relative_posix_path_under_watched(watched_root=watched_path, file_path=file_path)
                    verdict = decide_file_state(
                        library=library,
                        in_schedule_window=in_window,
                        file_age_seconds=_file_age_seconds(file_path),
                        blocked_by_connection=outcome.blocked_connection,
                    )
                    record_file_state(
                        session,
                        library=library,
                        relative_path=rel_for_state,
                        verdict=verdict,
                        size_bytes=_file_size_bytes(file_path),
                    )
                    if not verdict.eligible:
                        summary["files_withheld"] += 1
                        continue
                if outcome.verdict == "proceed":
                    summary["verdict_proceed"] += 1
                elif outcome.verdict == "wait_upstream":
                    summary["verdict_wait_upstream"] += 1
                    if outcome.blocked_reason and outcome.blocked_reason not in upstream_block_reasons:
                        upstream_block_reasons.append(outcome.blocked_reason)
                else:
                    summary["verdict_not_held"] += 1

                if outcome.verdict != "proceed" or not enqueue_remux_jobs:
                    continue

                rel = relative_posix_path_under_watched(watched_root=watched_path, file_path=file_path)
                if rel in rel_this_run:
                    summary["skipped_duplicate_same_scan"] += 1
                    continue
                rel_this_run.add(rel)

                if refiner_active_remux_pass_exists_for_relative_path(
                    session,
                    relative_posix=rel,
                    media_scope=media_scope,
                ):
                    summary["skipped_duplicate_active_queue"] += 1
                    continue
                if refiner_completed_remux_output_exists_for_relative_path(
                    session,
                    relative_posix=rel,
                    media_scope=media_scope,
                    output_root=rt.output_folder,
                ):
                    summary["skipped_existing_completed_output"] += 1
                    if media_scope == "movie":
                        summary["completed_source_cleanup_retried"] += 1
                        cleanup_ok, _cleanup_reason = retry_completed_movie_source_cleanup(
                            watched_root=watched_path,
                            file_path=file_path,
                        )
                        if cleanup_ok:
                            summary["completed_source_cleanup_retry_deleted"] += 1
                        else:
                            summary["completed_source_cleanup_retry_failed"] += 1
                            logger.warning(
                                "Refiner completed-output source cleanup retry failed for %s",
                                file_path,
                            )
                    continue

                payload = json.dumps(
                    {
                        "relative_media_path": rel,
                        "media_scope": media_scope,
                    },
                    separators=(",", ":"),
                )
                dedupe = f"{REFINER_FILE_REMUX_PASS_JOB_KIND}:scan:{uuid.uuid4().hex}"
                refiner_enqueue_or_get_job(
                    session,
                    dedupe_key=dedupe,
                    job_kind=REFINER_FILE_REMUX_PASS_JOB_KIND,
                    payload_json=payload,
                )
                summary["remux_jobs_enqueued"] += 1
                if len(sample_paths) < sample_cap:
                    sample_paths.append(rel)

            queued = int(summary["remux_jobs_enqueued"])
            waiting = int(summary["verdict_wait_upstream"])
            seen = int(summary["media_candidates_seen"])
            duplicates = (
                int(summary["skipped_duplicate_same_scan"])
                + int(summary["skipped_duplicate_active_queue"])
                + int(summary["skipped_existing_completed_output"])
            )
            if queued:
                summary["scan_result_label"] = "files_queued"
                summary["user_message"] = (
                    f"{queued} file{' was' if queued == 1 else 's were'} added to Refiner for processing."
                )
            elif waiting:
                summary["scan_result_label"] = "waiting_for_files"
                # One reason names the connection holding the file; several are summarised,
                # because a per-file list does not fit one operator sentence.
                held_by = (
                    upstream_block_reasons[0]
                    if len(upstream_block_reasons) == 1
                    else (
                        f"{waiting} file{' looks' if waiting == 1 else 's look'} like they are still being copied "
                        "or imported, so MediaMop left them alone for now."
                    )
                )
                summary["user_message"] = held_by
                summary["waiting_message"] = "MediaMop will check again on the next scheduled scan."
            elif seen and not enqueue_remux_jobs:
                summary["scan_result_label"] = "check_only"
                summary["user_message"] = (
                    f"{seen} media file{' was' if seen == 1 else 's were'} found, but this scan was set to check only."
                )
            elif seen and duplicates:
                summary["scan_result_label"] = "already_queued"
                summary["user_message"] = (
                    "MediaMop found matching media files, but they were already waiting for Refiner."
                )
            elif seen:
                summary["scan_result_label"] = "nothing_new"
                summary["user_message"] = "MediaMop found media files, but there was nothing new to queue."
            else:
                summary["scan_result_label"] = "no_media_found"
                summary["user_message"] = "MediaMop did not find any media files in this watched folder."

            # Extension mismatch was the one admission decision that said nothing at all.
            ignored = int(summary["ignored_unsupported_type"])
            if ignored:
                kinds = ", ".join(summary["ignored_unsupported_extensions"])
                summary["user_message"] = (
                    f"{summary['user_message']} {ignored} file{'' if ignored == 1 else 's'} "
                    f"{'was' if ignored == 1 else 'were'} ignored because MediaMop does not process "
                    f"that kind of file ({kinds})."
                ).strip()

            # A manager that could not be reached must never read as "nothing is importing".
            # The scan still runs — the file-settling gates are the fallback — but the
            # operator is told which check was missing rather than being shown a clean pass.
            degraded_note = signal_report.note()
            if degraded_note:
                summary["user_message"] = f"{summary['user_message']} {degraded_note}".strip()

            # File-level processing events now tell the user what happened. Recording a scan
            # event here makes Activity look backwards when completed file events arrive first.

    return _run


def _file_age_seconds(path: Path) -> float | None:
    try:
        return max(0.0, time.time() - float(path.stat().st_mtime))
    except OSError:
        return None


def _file_size_bytes(path: Path) -> int:
    try:
        return int(path.stat().st_size)
    except OSError:
        return 0
