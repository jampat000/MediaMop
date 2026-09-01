"""In-process Refiner worker handler for ``refiner.watched_folder.remux_scan_dispatch.v1``."""

from __future__ import annotations

import json
import logging
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from fnmatch import fnmatchcase
from pathlib import Path, PurePosixPath
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from mediamop.core.config import MediaMopSettings
from mediamop.modules.refiner.file_remux_pass.job_kinds import REFINER_FILE_REMUX_PASS_JOB_KIND
from mediamop.modules.refiner.jobs_ops import refiner_enqueue_or_get_job
from mediamop.modules.refiner.refiner_file_settling import (
    AccessCheck,
    check_file_access,
    observe_size_settling,
)
from mediamop.modules.refiner.refiner_file_state_model import RefinerFileRow, RefinerFileStatus
from mediamop.modules.refiner.refiner_file_state_service import (
    FileStateVerdict,
    decide_file_state,
    existing_file_row,
    mark_file_status,
    record_file_state,
)
from mediamop.modules.refiner.refiner_library_service import (
    admission_rules_for,
    manager_connection_ids_for,
    resolve_library,
)
from mediamop.modules.refiner.refiner_operator_settings_service import ensure_refiner_operator_settings_row
from mediamop.modules.refiner.refiner_path_settings_service import resolve_refiner_path_runtime_for_remux
from mediamop.modules.refiner.refiner_rejected_file_cleanup import cleanup_rejected_file
from mediamop.modules.refiner.refiner_remux_rules import refiner_media_extensions_sorted
from mediamop.modules.refiner.refiner_requeue_service import requeue_file
from mediamop.modules.refiner.refiner_runner_units import (
    budget_from_settings,
    resolution_class_for_dimensions,
)
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
from mediamop.modules.refiner.refiner_work_admission import (
    evaluate_work_admission,
    library_window_open,
    library_window_reopens_at,
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
        if scan_trigger not in ("manual", "periodic", "filesystem_event"):
            scan_trigger = "manual"
        media_scope_raw = body.get("media_scope", "movie")
        media_scope: MediaScope = "tv" if media_scope_raw == "tv" else "movie"
        library_id_raw = body.get("library_id")
        library_id = int(library_id_raw) if isinstance(library_id_raw, int) and library_id_raw > 0 else None

        with session_factory() as session:
            op_settings = ensure_refiner_operator_settings_row(session)
            rt, path_err = resolve_refiner_path_runtime_for_remux(
                session,
                settings,
                media_scope=media_scope,
                library_id=library_id,
            )
        if path_err is not None or rt is None:
            raise ValueError(path_err or "Refiner path settings are incomplete for this scan.")

        watched_root = rt.watched_folder
        with session_factory() as manager_session:
            manager_library = resolve_library(manager_session, library_id=library_id, media_scope=media_scope)
            connection_ids = (
                manager_connection_ids_for(manager_session, manager_library) if manager_library is not None else None
            )
            signals, signal_report = fetch_manager_queue_signals_for_scan(
                manager_session,
                settings,
                media_scope=media_scope,
                connection_ids=connection_ids,
            )

        with session_factory() as library_session:
            runner_budget = budget_from_settings(ensure_refiner_operator_settings_row(library_session))
            library = resolve_library(library_session, library_id=library_id, media_scope=media_scope)
            admission = evaluate_work_admission(library_session)
            pause_reason = admission.pause.reason if admission.pause.paused else None
            pause_until = admission.pause.paused_until if admission.pause.paused else None
            if library is not None:
                in_window = library_window_open(library, timezone_name=admission.timezone_name)
                reopens_at = (
                    None if in_window else library_window_reopens_at(library, timezone_name=admission.timezone_name)
                )
            else:
                in_window = True
                reopens_at = None

        watched_path = Path(watched_root)
        rules = admission_rules_for(library) if library is not None else None
        effective_min_age_seconds = max(
            int(op_settings.min_file_age_seconds),
            int(rules.min_file_age_seconds) if rules is not None else 0,
        )
        candidates = iter_watched_folder_media_candidates(
            watched_path,
            min_file_age_seconds=0,
            media_extensions=rules.media_extensions if rules is not None else None,
            exclude_markers=rules.exclude_markers if rules is not None else None,
            exclude_hidden=rules.exclude_hidden if rules is not None else False,
            top_level_only=rules.top_level_only if rules is not None else False,
        )
        files = candidates.files

        sample_paths: list[str] = []
        upstream_block_reasons: list[str] = []
        summary: dict[str, Any] = {
            "job_id": ctx.id,
            "scan_trigger": scan_trigger,
            "media_scope": media_scope,
            "library_id": int(library.id) if library is not None else None,
            "library_name": library.name if library is not None else None,
            "scan_result_label": "watched_folder_checked",
            "watched_folder_resolved": watched_root,
            "enqueue_remux_jobs": enqueue_remux_jobs,
            "min_file_age_seconds": effective_min_age_seconds,
            "minimum_input_file_size_mb": max(
                int(op_settings.refiner_min_input_file_size_mb),
                int(rules.min_file_size_mb) if rules is not None else 0,
            ),
            "maximum_input_file_size_mb": int(rules.max_file_size_mb) if rules is not None else 0,
            "managers_consulted": signal_report.consulted,
            "managers_reporting": signal_report.reported,
            "manager_queue_row_count": sum(len(s.rows) for s in signals if s.is_reported),
            "managers_without_queue_signal": list(signal_report.silent_labels),
            "manager_queue_signal_notes": list(signal_report.silent_details),
            "upstream_block_reasons": upstream_block_reasons,
            "media_candidates_seen": len(files),
            "ignored_unsupported_type": candidates.ignored_unsupported_type,
            "ignored_unsupported_extensions": list(candidates.ignored_unsupported_extensions),
            "media_extensions_applied": (
                sorted(rules.media_extensions)
                if rules is not None and rules.media_extensions
                else list(refiner_media_extensions_sorted())
            ),
            "files_withheld": 0,
            "files_quarantined": 0,
            "files_waiting_for_retry": 0,
            "automatic_retries_requeued": 0,
            "files_still_settling": 0,
            "files_failing_access_test": 0,
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
            "skipped_above_maximum_file_size": 0,
            "skipped_before_created_window": 0,
            "skipped_after_created_window": 0,
            "skipped_before_modified_window": 0,
            "skipped_after_modified_window": 0,
            "skipped_by_include_pattern": 0,
            "skipped_by_exclude_pattern": 0,
            "rejected_files_deleted": 0,
            "rejected_file_cleanup_failed": 0,
            "user_message": "",
            "waiting_message": None,
            "enqueued_relative_paths_sample": sample_paths,
        }

        rel_this_run: set[str] = set()
        sample_cap = 32
        pending_rejected_cleanups: list[tuple[int, str, Path, str, str]] = []

        with session_factory() as session, session.begin():
            for file_path in files:
                # A successful Movies cleanup can remove a release folder while this
                # scan still holds candidate Path objects for its extras. Do not turn
                # those stale entries into new states or jobs.
                if not file_path.is_file():
                    continue
                rel = relative_posix_path_under_watched(watched_root=watched_path, file_path=file_path)
                outcome = evaluate_watched_media_file_for_dispatch(
                    signals=signals,
                    media_scope=media_scope,
                    file_path=file_path,
                )
                # Record why this file is or is not being worked on. Until now the reason
                # existed only as a local variable and the operator saw nothing (#334).
                if library is not None:
                    rel_for_state = rel
                    observed_size = _file_size_bytes(file_path)
                    # Read the previous observation before recording this one — the whole
                    # settling decision is the comparison between the two (#335).
                    previous = existing_file_row(session, library_id=library.id, relative_path=rel_for_state)
                    if previous is not None and previous.size_bytes != observed_size:
                        # A changed source is a new processing opportunity. Do not carry a
                        # failure/quarantine counter from the old bytes into the new file.
                        previous.failure_class = None
                        previous.failure_attempts = 0
                        previous.next_retry_at = None
                        if previous.status in {
                            RefinerFileStatus.PROCESSING_FAILED.value,
                            RefinerFileStatus.ON_HOLD.value,
                        }:
                            previous.status = RefinerFileStatus.UNPROCESSED.value
                            previous.status_reason = "The source changed; Refiner will evaluate it again."
                    # A failed file must not be turned back into fresh work by every
                    # periodic scan. Preserve the failure while the source is unchanged;
                    # a manual requeue or changed file is the explicit retry signal (#402).
                    if previous is not None and previous.size_bytes == observed_size:
                        if previous.status == RefinerFileStatus.PROCESSING_FAILED.value:
                            retry_at = previous.next_retry_at
                            if retry_at is not None:
                                retry_at = retry_at.replace(tzinfo=retry_at.tzinfo or UTC)
                            if retry_at is not None and retry_at <= datetime.now(UTC):
                                retry = requeue_file(session, row=previous, manual=False)
                                if retry.requeued:
                                    summary["automatic_retries_requeued"] += 1
                                    continue
                            summary["files_waiting_for_retry"] += 1
                            summary["files_withheld"] += 1
                            previous.last_seen_at = datetime.now(UTC)
                            continue
                        if (
                            previous.status == RefinerFileStatus.ON_HOLD.value
                            and int(previous.failure_attempts or 0) >= 3
                        ):
                            summary["files_quarantined"] += 1
                            summary["files_withheld"] += 1
                            previous.last_seen_at = datetime.now(UTC)
                            continue
                    settling = observe_size_settling(
                        library=library,
                        previous=previous,
                        current_size_bytes=observed_size,
                    )
                    # Only probe access once the file has stopped moving. A file mid-write
                    # is normally locked as well, and "still being written to" is the
                    # cause an operator can act on.
                    access = (
                        AccessCheck(ok=True)
                        if settling.is_settling
                        else check_file_access(
                            library=library,
                            file_path=file_path,
                            output_folder=Path(rt.output_folder) if rt.output_folder else None,
                        )
                    )
                    verdict = decide_file_state(
                        library=library,
                        in_schedule_window=in_window,
                        file_age_seconds=_file_age_seconds(file_path),
                        paused_reason=pause_reason,
                        paused_until=pause_until,
                        window_reopens_at=reopens_at,
                        size_is_settling=settling.is_settling,
                        settling_reason=settling.reason,
                        settling_stable_at=settling.stable_at,
                        access_problem=access.problem,
                        blocked_by_connection=outcome.blocked_connection,
                        minimum_age_seconds=effective_min_age_seconds,
                    )
                    record_file_state(
                        session,
                        library=library,
                        relative_path=rel_for_state,
                        verdict=verdict,
                        size_bytes=observed_size,
                        size_changed_at=settling.size_changed_at,
                    )
                    # Finishing cleanup for a successfully written output is part of
                    # that completed pass, not new processing. It must be able to finish
                    # after a temporary Windows/NAS lock clears even when Refiner is
                    # paused or the processing schedule is closed.
                    cleanup_retry_ready = not settling.is_settling and not access.problem
                    cleanup_retry_has_no_active_pass = not refiner_active_remux_pass_exists_for_relative_path(
                        session,
                        relative_posix=rel,
                        media_scope=media_scope,
                        library_id=int(library.id),
                    )
                    if (
                        media_scope == "movie"
                        and cleanup_retry_ready
                        and cleanup_retry_has_no_active_pass
                        and refiner_completed_remux_output_exists_for_relative_path(
                            session,
                            relative_posix=rel,
                            media_scope=media_scope,
                            library_id=int(library.id),
                            output_root=rt.output_folder,
                            source_path=file_path,
                        )
                    ):
                        summary["skipped_existing_completed_output"] += 1
                        if media_scope == "movie":
                            summary["completed_source_cleanup_retried"] += 1
                            cleanup_ok, cleanup_reason = retry_completed_movie_source_cleanup(
                                watched_root=watched_path,
                                file_path=file_path,
                            )
                            if cleanup_ok:
                                summary["completed_source_cleanup_retry_deleted"] += 1
                                release_parent = PurePosixPath(rel).parent
                                sibling_rows = session.scalars(
                                    select(RefinerFileRow).where(RefinerFileRow.library_id == library.id)
                                ).all()
                                for sibling_row in sibling_rows:
                                    if PurePosixPath(sibling_row.relative_path).parent != release_parent:
                                        continue
                                    sibling_row.status = RefinerFileStatus.PROCESSED.value
                                    sibling_row.status_reason = "MediaMop removed this file with its release folder after the validated movie output completed. No separate output was created for this extra file."
                                    sibling_row.blocked_by_connection = None
                                    sibling_row.hold_until = None
                                record_file_state(
                                    session,
                                    library=library,
                                    relative_path=rel,
                                    verdict=FileStateVerdict(
                                        RefinerFileStatus.PROCESSED,
                                        "The output was already complete. The temporary lock cleared, so MediaMop finished removing the source release folder.",
                                    ),
                                    size_bytes=observed_size,
                                    size_changed_at=settling.size_changed_at,
                                )
                            else:
                                summary["completed_source_cleanup_retry_failed"] += 1
                                retry_reason = cleanup_reason or "The source release folder is still locked."
                                record_file_state(
                                    session,
                                    library=library,
                                    relative_path=rel,
                                    verdict=FileStateVerdict(
                                        RefinerFileStatus.ON_HOLD,
                                        f"The output is complete, but source cleanup is waiting: {retry_reason} MediaMop will try again automatically.",
                                    ),
                                    size_bytes=observed_size,
                                    size_changed_at=settling.size_changed_at,
                                )
                                logger.warning(
                                    "Refiner completed-output source cleanup retry failed for %s: %s",
                                    file_path,
                                    retry_reason,
                                )
                        continue
                    if not verdict.eligible:
                        summary["files_withheld"] += 1
                        if settling.is_settling:
                            summary["files_still_settling"] += 1
                        elif access.problem:
                            summary["files_failing_access_test"] += 1
                        continue
                    rejection = _library_admission_rejection(
                        file_path=file_path,
                        relative_path=rel_for_state,
                        size_bytes=observed_size,
                        minimum_size_mb=max(
                            int(op_settings.refiner_min_input_file_size_mb),
                            int(rules.min_file_size_mb) if rules is not None else 0,
                        ),
                        maximum_size_mb=int(rules.max_file_size_mb) if rules is not None else 0,
                        include_patterns=rules.include_patterns if rules is not None else (),
                        exclude_patterns=rules.exclude_patterns if rules is not None else (),
                        created_after=rules.created_after if rules is not None else None,
                        created_before=rules.created_before if rules is not None else None,
                        modified_after=rules.modified_after if rules is not None else None,
                        modified_before=rules.modified_before if rules is not None else None,
                    )
                    if rejection is not None:
                        reason, counter = rejection
                        cleanup_action = rules.rejected_file_action if rules is not None else "leave"
                        if cleanup_action == "delete_file":
                            pending_rejected_cleanups.append(
                                (int(library.id), rel_for_state, file_path, reason, cleanup_action)
                            )
                            reason = (
                                f"{reason} This library is set to delete rejected files; "
                                "MediaMop will record this decision before removing only this file."
                            )
                        record_file_state(
                            session,
                            library=library,
                            relative_path=rel_for_state,
                            verdict=FileStateVerdict(RefinerFileStatus.SKIPPED, reason),
                            size_bytes=observed_size,
                            size_changed_at=settling.size_changed_at,
                        )
                        summary[counter] += 1
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

                if rel in rel_this_run:
                    summary["skipped_duplicate_same_scan"] += 1
                    continue
                rel_this_run.add(rel)

                if refiner_active_remux_pass_exists_for_relative_path(
                    session,
                    relative_posix=rel,
                    media_scope=media_scope,
                    library_id=int(library.id) if library is not None else None,
                ):
                    summary["skipped_duplicate_active_queue"] += 1
                    continue
                if refiner_completed_remux_output_exists_for_relative_path(
                    session,
                    relative_posix=rel,
                    media_scope=media_scope,
                    library_id=int(library.id) if library is not None else None,
                    output_root=rt.output_folder,
                    source_path=file_path,
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

                payload_body: dict[str, Any] = {
                    "relative_media_path": rel,
                    "media_scope": media_scope,
                }
                # The library id travels with the job so the per-library cap and the
                # schedule window can be applied at lease time without re-deriving it.
                if library is not None:
                    payload_body["library_id"] = library.id
                payload = json.dumps(payload_body, separators=(",", ":"))
                dedupe = f"{REFINER_FILE_REMUX_PASS_JOB_KIND}:scan:{uuid.uuid4().hex}"
                # Weighted from the height this file was measured at on a previous pass.
                # A file MediaMop has not processed before costs the "undetermined"
                # weight rather than a guess, and is measured for next time.
                previous_row = (
                    existing_file_row(session, library_id=library.id, relative_path=rel)
                    if library is not None
                    else None
                )
                refiner_enqueue_or_get_job(
                    session,
                    dedupe_key=dedupe,
                    job_kind=REFINER_FILE_REMUX_PASS_JOB_KIND,
                    payload_json=payload,
                    runner_cost=runner_budget.cost_for(
                        resolution_class_for_dimensions(
                            width=previous_row.video_width if previous_row else None,
                            height=previous_row.video_height if previous_row else None,
                        )
                    ),
                    priority=int(library.priority) if library is not None else 0,
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

        # The SKIPPED decision above commits before this mutation. If the process stops
        # between the two, the source remains and the next scan safely retries.
        for (
            cleanup_library_id,
            cleanup_relative_path,
            cleanup_path,
            rejection_reason,
            cleanup_action,
        ) in pending_rejected_cleanups:
            cleanup_result = cleanup_rejected_file(
                watched_root=watched_path,
                file_path=cleanup_path,
                action=cleanup_action,
            )
            if cleanup_result.deleted:
                summary["rejected_files_deleted"] += 1
            else:
                summary["rejected_file_cleanup_failed"] += 1
            with session_factory() as cleanup_session, cleanup_session.begin():
                mark_file_status(
                    cleanup_session,
                    library_id=cleanup_library_id,
                    relative_path=cleanup_relative_path,
                    status=RefinerFileStatus.SKIPPED,
                    reason=f"{rejection_reason} {cleanup_result.detail}",
                )

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


def _library_admission_rejection(
    *,
    file_path: Path,
    relative_path: str,
    size_bytes: int,
    minimum_size_mb: int,
    maximum_size_mb: int,
    include_patterns: tuple[str, ...],
    exclude_patterns: tuple[str, ...],
    created_after: datetime | None,
    created_before: datetime | None,
    modified_after: datetime | None,
    modified_before: datetime | None,
) -> tuple[str, str] | None:
    """Return plain-language reason and summary counter for a settled file to skip."""

    size_mb = max(0, int(size_bytes)) / (1024 * 1024)
    if minimum_size_mb > 0 and size_bytes < minimum_size_mb * 1024 * 1024:
        return (
            f"Skipped because this file is {size_mb:.1f} MB and the {minimum_size_mb} MB library minimum is not met.",
            "skipped_below_minimum_file_size",
        )
    if maximum_size_mb > 0 and size_bytes > maximum_size_mb * 1024 * 1024:
        return (
            f"Skipped because this file is {size_mb:.1f} MB and exceeds the {maximum_size_mb} MB library maximum.",
            "skipped_above_maximum_file_size",
        )

    try:
        stat = file_path.stat()
    except OSError:
        stat = None
    if stat is not None:
        # Windows st_ctime is the creation time. BSD/macOS expose st_birthtime;
        # Linux containers do not consistently expose birth time through Python,
        # so st_ctime is the portable metadata-change fallback there.
        creation_epoch = float(getattr(stat, "st_birthtime", stat.st_ctime))
        created_at = datetime.fromtimestamp(creation_epoch, tz=UTC)
        modified_at = datetime.fromtimestamp(float(stat.st_mtime), tz=UTC)

        if created_after is not None and created_at < created_after:
            return (
                f"Skipped because its filesystem creation time ({created_at.isoformat()}) is before this library's allowed window.",
                "skipped_before_created_window",
            )
        if created_before is not None and created_at >= created_before:
            return (
                f"Skipped because its filesystem creation time ({created_at.isoformat()}) is after this library's allowed window.",
                "skipped_after_created_window",
            )
        if modified_after is not None and modified_at < modified_after:
            return (
                f"Skipped because its last-modified time ({modified_at.isoformat()}) is before this library's allowed window.",
                "skipped_before_modified_window",
            )
        if modified_before is not None and modified_at >= modified_before:
            return (
                f"Skipped because its last-modified time ({modified_at.isoformat()}) is after this library's allowed window.",
                "skipped_after_modified_window",
            )

    path_values = (relative_path.lower(), file_path.name.lower())
    normalized_includes = tuple(pattern.strip().lower() for pattern in include_patterns if pattern.strip())
    if normalized_includes and not any(
        fnmatchcase(value, pattern) for value in path_values for pattern in normalized_includes
    ):
        return (
            "Skipped because its path does not match this library's include patterns.",
            "skipped_by_include_pattern",
        )
    normalized_excludes = tuple(pattern.strip().lower() for pattern in exclude_patterns if pattern.strip())
    if any(fnmatchcase(value, pattern) for value in path_values for pattern in normalized_excludes):
        return (
            "Skipped because its path matches this library's exclude patterns.",
            "skipped_by_exclude_pattern",
        )
    return None
