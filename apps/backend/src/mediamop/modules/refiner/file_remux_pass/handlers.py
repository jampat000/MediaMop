"""In-process Refiner worker handler for ``refiner.file.remux_pass.v1``."""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar

from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from mediamop.core.config import MediaMopSettings
from mediamop.modules.refiner.file_remux_pass.run import run_refiner_file_remux_pass
from mediamop.modules.refiner.file_remux_pass.visibility import (
    REMUX_PASS_OUTCOME_FAILED_BEFORE_EXECUTION,
    remux_pass_activity_title,
    remux_pass_result_to_activity_detail,
)
from mediamop.modules.refiner.refiner_failure_classes import classify_failure
from mediamop.modules.refiner.refiner_file_log_service import record_file_log
from mediamop.modules.refiner.refiner_file_remux_pass_activity import (
    complete_refiner_file_processing_activity,
    record_refiner_file_processing_started,
    record_refiner_file_remux_pass_completed,
    update_refiner_file_processing_progress,
)
from mediamop.modules.refiner.refiner_file_state_model import RefinerFileStatus
from mediamop.modules.refiner.refiner_file_state_service import mark_file_status
from mediamop.modules.refiner.refiner_library_service import resolve_library, rules_config_for
from mediamop.modules.refiner.refiner_operator_settings_service import ensure_refiner_operator_settings_row
from mediamop.modules.refiner.refiner_path_settings_service import resolve_refiner_path_runtime_for_remux
from mediamop.modules.refiner.refiner_rejected_file_cleanup import cleanup_rejected_file
from mediamop.modules.refiner.refiner_remux_rules_settings_service import load_refiner_remux_rules_config
from mediamop.modules.refiner.refiner_requeue_service import record_failure
from mediamop.modules.refiner.worker_loop import RefinerJobWorkContext
from mediamop.platform.media_managers.completion_callback import report_handoff_completion

logger = logging.getLogger(__name__)
_T = TypeVar("_T")
_LOCK_RETRY_ATTEMPTS = 4


def _is_sqlite_lock_error(exc: OperationalError) -> bool:
    text = str(exc).lower()
    return "database is locked" in text or "database table is locked" in text


def _retry_locked_write(operation: Callable[[], _T], *, label: str) -> _T:
    """Retry a short metadata transaction when another local writer briefly owns SQLite."""

    delay = 0.1
    for attempt in range(_LOCK_RETRY_ATTEMPTS):
        try:
            return operation()
        except OperationalError as exc:
            if not _is_sqlite_lock_error(exc) or attempt == _LOCK_RETRY_ATTEMPTS - 1:
                raise
            logger.warning(
                "Refiner metadata write is waiting for SQLite (%s; retry %s/%s).",
                label,
                attempt + 1,
                _LOCK_RETRY_ATTEMPTS - 1,
            )
            time.sleep(delay)
            delay *= 2
    raise AssertionError("unreachable")


def _commit_session_with_retry(
    session: Session,
    *,
    label: str,
    required: bool,
    retry_operation: Callable[[], None] | None = None,
) -> None:
    """Commit a worker-owned transaction without letting optional metadata poison a pass."""

    delay = 0.1
    for attempt in range(_LOCK_RETRY_ATTEMPTS):
        try:
            session.commit()
            return
        except OperationalError as exc:
            session.rollback()
            if not _is_sqlite_lock_error(exc) or attempt == _LOCK_RETRY_ATTEMPTS - 1:
                if required:
                    raise
                logger.warning("Refiner could not save optional metadata after the media pass.", exc_info=True)
                return
            logger.warning(
                "Refiner transaction is waiting for SQLite (%s; retry %s/%s).",
                label,
                attempt + 1,
                _LOCK_RETRY_ATTEMPTS - 1,
            )
            time.sleep(delay)
            delay *= 2
            if retry_operation is not None:
                retry_operation()
        except Exception:
            session.rollback()
            if required:
                raise
            logger.warning("Refiner could not save optional metadata after the media pass.", exc_info=True)
            return
    if required:
        raise RuntimeError(f"Refiner could not commit required transaction: {label}")


def _report_back(
    settings: MediaMopSettings,
    session_factory: sessionmaker[Session],
    *,
    payload_json: str | None,
    result: dict[str, Any],
) -> None:
    """Tell the originating media manager how the pass went, if it asked to be told.

    A hand-off is a loan: the manager is still holding the import open. Reporting is
    best-effort and never raises, so an unreachable manager cannot fail work that has
    already succeeded on disk.
    """

    try:
        with session_factory() as session:
            status = report_handoff_completion(
                session,
                settings,
                payload_json=payload_json,
                result=result,
            )
        if not status.startswith("skipped"):
            logger.info("Refiner hand-off callback: %s", status)
    except Exception:  # noqa: BLE001 - reporting must never break the job
        logger.exception("Refiner hand-off callback raised unexpectedly.")


def _record(session_factory: sessionmaker[Session], *, payload: dict[str, Any], activity_id: int | None = None) -> None:
    detail = remux_pass_result_to_activity_detail(payload)
    title = remux_pass_activity_title(payload)

    def write() -> None:
        with session_factory() as session, session.begin():
            # The durable per-file record is written here, beside the activity row, so the
            # two cannot disagree about what happened. It outlives the activity feed under
            # its own retention (#340).
            relative_path = payload.get("relative_media_path")
            if isinstance(relative_path, str) and relative_path.strip():
                try:
                    record_file_log(session, relative_path=relative_path, title=title, detail=payload)
                except OperationalError:
                    # Let the outer transaction retry with a fresh Session. Continuing
                    # inside a failed SQLAlchemy transaction would only hide the lock.
                    raise
                except Exception:
                    # A record that cannot be written must not fail the pass that produced
                    # it: the work is done either way, and losing the job is worse than
                    # losing the note about it.
                    logger.exception("Refiner could not write the processing record for %s.", relative_path)
            if activity_id is not None:
                updated = complete_refiner_file_processing_activity(
                    session,
                    activity_id=activity_id,
                    title=title,
                    detail=detail,
                )
                if updated:
                    return
            record_refiner_file_remux_pass_completed(session, title=title, detail=detail)

    try:
        _retry_locked_write(write, label="processing record")
    except Exception:
        # Activity is observability, never a prerequisite for a safe media mutation.
        logger.warning(
            "Refiner could not save the processing record; the pass result remains authoritative.", exc_info=True
        )


class RefinerActivityProgressReporter:
    def __init__(self, session_factory: sessionmaker[Session], *, job_id: int) -> None:
        self._session_factory = session_factory
        self._job_id = job_id
        self.activity_id: int | None = None

    def __call__(self, payload: dict[str, Any]) -> None:
        body = {"job_id": self._job_id, **payload}

        def write() -> None:
            with self._session_factory() as session, session.begin():
                if self.activity_id is None:
                    self.activity_id = record_refiner_file_processing_started(session, payload=body)
                else:
                    update_refiner_file_processing_progress(session, activity_id=self.activity_id, payload=body)

        try:
            _retry_locked_write(write, label="processing progress")
        except Exception:
            # A progress update must never interrupt ffprobe/ffmpeg. The final durable
            # processing record is attempted separately after the media work returns.
            logger.warning("Refiner could not save a progress update; continuing the media pass.", exc_info=True)


def _make_progress_reporter(session_factory: sessionmaker[Session], *, job_id: int) -> RefinerActivityProgressReporter:
    return RefinerActivityProgressReporter(session_factory, job_id=job_id)


def _apply_file_outcome_state(
    session_factory: sessionmaker[Session],
    *,
    result: dict[str, Any],
    library_id: int | None,
    media_scope: str,
) -> None:
    """Keep the durable Files row in step with the result shown in Activity."""

    relative_path = result.get("relative_media_path")
    if not isinstance(relative_path, str) or not relative_path.strip():
        return

    def write() -> None:
        with session_factory() as session, session.begin():
            library = resolve_library(session, library_id=library_id, media_scope=media_scope)
            if library is None:
                return
            if result.get("rejection_kind"):
                rejection_reason = " ".join(
                    str(result.get("reason") or "Refiner rejected this file before processing.").split()
                )[:1200]
                cleanup_detail = str(
                    result.get("rejected_cleanup_detail") or "The saved rejected-file action has not run yet."
                )
                row = mark_file_status(
                    session,
                    library_id=library.id,
                    relative_path=relative_path.strip(),
                    status=RefinerFileStatus.SKIPPED,
                    reason=f"{rejection_reason} {cleanup_detail}",
                )
                if row is not None:
                    row.failure_class = None
                    row.failure_attempts = 0
                    row.next_retry_at = None
                    row.hold_until = None
                result.update(
                    {
                        "retry_scheduled": False,
                        "quarantined": False,
                        "failure_next_retry_at": None,
                        "failure_operator_message": f"{rejection_reason} {cleanup_detail}",
                    }
                )
                return
            if result.get("retryable_wait") is True:
                reason = " ".join(
                    str(
                        result.get("reason") or "MediaMop is waiting until no other program is writing this file."
                    ).split()
                )[:1200]
                row = mark_file_status(
                    session,
                    library_id=library.id,
                    relative_path=relative_path.strip(),
                    status=RefinerFileStatus.ON_HOLD,
                    reason=reason,
                )
                if row is not None:
                    row.failure_class = None
                    row.failure_attempts = 0
                    row.next_retry_at = None
                    row.hold_until = None
                result.update(
                    {
                        "retry_scheduled": False,
                        "quarantined": False,
                        "failure_next_retry_at": None,
                        "failure_operator_message": reason,
                    }
                )
                return
            if result.get("ok") is False:
                outcome = str(result.get("outcome") or "")
                failure_class = classify_failure(outcome)
                reason = " ".join(str(result.get("reason") or "Refiner returned an unsuccessful result.").split())[
                    :1200
                ]
                decision = record_failure(
                    session,
                    library=library,
                    relative_path=relative_path.strip(),
                    failure_class=failure_class,
                    reason=reason,
                )
                result.update(
                    {
                        "failure_class": failure_class.value,
                        "retry_scheduled": decision.will_retry,
                        "quarantined": decision.quarantined,
                        "failure_next_retry_at": decision.next_retry_at.isoformat() if decision.next_retry_at else None,
                        "failure_operator_message": decision.reason,
                    }
                )
                return
            row = mark_file_status(
                session,
                library_id=library.id,
                relative_path=relative_path.strip(),
                status=RefinerFileStatus.PROCESSED,
                reason=(
                    "MediaMop passed this file through unchanged at the operator's request and placed it in the output folder."
                    if result.get("pass_through_unchanged") is True
                    else "Refiner checked this file and found that no changes were needed."
                    if result.get("outcome") == "live_skipped_not_required"
                    else "Refiner finished processing this file."
                ),
            )
            if row is not None:
                row.failure_class = None
                row.failure_attempts = 0
                row.next_retry_at = None
                row.hold_until = None

    try:
        _retry_locked_write(write, label="file outcome")
    except Exception:
        # The media pass (and its job result) remains the source of truth. Keep a
        # visible log entry rather than replacing a completed file with a false failure.
        logger.warning("Refiner could not save the durable Files state; inspect the processing record.", exc_info=True)


def _record_failed_result(
    session_factory: sessionmaker[Session],
    *,
    payload: dict[str, Any],
    library_id: int | None,
    media_scope: str,
) -> None:
    """Record preflight failures through the same Files/Activity contract as a run result."""

    _apply_file_outcome_state(
        session_factory,
        result=payload,
        library_id=library_id,
        media_scope=media_scope,
    )
    _record(session_factory, payload=payload)


def _finish_rejected_input_cleanup(
    session_factory: sessionmaker[Session],
    *,
    result: dict[str, Any],
    library_id: int | None,
    media_scope: str,
) -> None:
    """Apply an already-recorded opt-in rejection deletion and append its final record."""

    if not result.get("rejection_kind") or result.get("rejected_file_action") != "delete_file":
        return
    watched_root = result.get("refiner_watched_folder_resolved")
    inspected_source = result.get("inspected_source_path")
    if not isinstance(watched_root, str) or not isinstance(inspected_source, str):
        result["rejected_cleanup_status"] = "not_deleted"
        result["rejected_cleanup_detail"] = (
            "MediaMop did not delete the rejected file because its verified watched-folder path was unavailable."
        )
    else:
        cleanup = cleanup_rejected_file(
            watched_root=Path(watched_root),
            file_path=Path(inspected_source),
            action="delete_file",
        )
        result["rejected_cleanup_status"] = "deleted" if cleanup.deleted else "not_deleted"
        result["rejected_cleanup_detail"] = cleanup.detail

    _apply_file_outcome_state(
        session_factory,
        result=result,
        library_id=library_id,
        media_scope=media_scope,
    )

    def write_log() -> None:
        relative_path = result.get("relative_media_path")
        if not isinstance(relative_path, str) or not relative_path.strip():
            return
        with session_factory() as session, session.begin():
            record_file_log(
                session,
                relative_path=relative_path,
                title="Rejected file cleanup finished",
                detail=result,
            )

    _retry_locked_write(write_log, label="rejected file cleanup record")


def make_refiner_file_remux_pass_handler(
    settings: MediaMopSettings,
    session_factory: sessionmaker[Session],
) -> Callable[[RefinerJobWorkContext], None]:
    """One per-file probe/plan/remux pass (live-only contract)."""

    def _run(ctx: RefinerJobWorkContext) -> None:
        raw = (ctx.payload_json or "").strip()
        if not raw:
            _record(
                session_factory,
                payload={
                    "job_id": ctx.id,
                    "ok": False,
                    "outcome": REMUX_PASS_OUTCOME_FAILED_BEFORE_EXECUTION,
                    "reason": "missing payload_json",
                },
            )
            return

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            _record(
                session_factory,
                payload={
                    "job_id": ctx.id,
                    "ok": False,
                    "outcome": REMUX_PASS_OUTCOME_FAILED_BEFORE_EXECUTION,
                    "reason": f"invalid json: {exc}",
                },
            )
            return

        if not isinstance(data, dict):
            _record(
                session_factory,
                payload={
                    "job_id": ctx.id,
                    "ok": False,
                    "outcome": REMUX_PASS_OUTCOME_FAILED_BEFORE_EXECUTION,
                    "reason": "payload must be a JSON object",
                },
            )
            return

        rel = data.get("relative_media_path")
        if not isinstance(rel, str) or not rel.strip():
            _record(
                session_factory,
                payload={
                    "job_id": ctx.id,
                    "ok": False,
                    "outcome": REMUX_PASS_OUTCOME_FAILED_BEFORE_EXECUTION,
                    "reason": "relative_media_path is required",
                },
            )
            return

        legacy_dry_run = data.get("dry_run", None)
        if legacy_dry_run is not None:
            _record_failed_result(
                session_factory,
                payload={
                    "job_id": ctx.id,
                    "ok": False,
                    "outcome": REMUX_PASS_OUTCOME_FAILED_BEFORE_EXECUTION,
                    "reason": (
                        "This job payload uses legacy Refiner dry_run, which is no longer supported. "
                        "Re-enqueue without dry_run."
                    ),
                    "relative_media_path": rel.strip(),
                },
                library_id=None,
                media_scope="movie",
            )
            return

        media_scope = data.get("media_scope", "movie")
        if not isinstance(media_scope, str) or media_scope not in ("movie", "tv"):
            media_scope = "movie"
        # Additive, never a new job kind: a payload queued before the upgrade has no
        # library_id and resolves to the seeded library for its scope (ADR-0014 §5).
        raw_library_id = data.get("library_id")
        library_id = (
            raw_library_id if isinstance(raw_library_id, int) and not isinstance(raw_library_id, bool) else None
        )
        pass_through_unchanged = data.get("pass_through_unchanged") is True

        failure_payload: dict[str, Any] | None = None
        result: dict[str, Any] | None = None
        progress_reporter: RefinerActivityProgressReporter | None = None
        with session_factory() as session:
            op_settings = ensure_refiner_operator_settings_row(session)
            library = resolve_library(session, library_id=library_id, media_scope=media_scope)
            rules_cfg = rules_config_for(session, library) if library is not None else None
            if rules_cfg is None:
                rules_cfg = load_refiner_remux_rules_config(session, media_scope=media_scope)
            path_runtime, path_err = resolve_refiner_path_runtime_for_remux(
                session,
                settings,
                media_scope=media_scope,
                library_id=library_id,
            )
            if path_err is not None:
                failure_payload = {
                    "job_id": ctx.id,
                    "ok": False,
                    "outcome": REMUX_PASS_OUTCOME_FAILED_BEFORE_EXECUTION,
                    "reason": path_err,
                    "relative_media_path": rel.strip(),
                    "library_id": int(library.id) if library is not None else library_id,
                }
            else:
                assert path_runtime is not None
                if library is not None:
                    mark_file_status(
                        session,
                        library_id=library.id,
                        relative_path=rel.strip(),
                        status=RefinerFileStatus.PROCESSING,
                        reason="Refiner has claimed this file and is checking it now.",
                    )
                # No ffprobe/ffmpeg work is allowed while the worker holds a DB
                # transaction. This boundary is what prevents long media operations
                # from blocking the progress/activity writers.
                _commit_session_with_retry(
                    session,
                    label="claim processing file",
                    required=True,
                    retry_operation=(
                        lambda: (
                            mark_file_status(
                                session,
                                library_id=library.id,
                                relative_path=rel.strip(),
                                status=RefinerFileStatus.PROCESSING,
                                reason="Refiner has claimed this file and is checking it now.",
                            )
                            if library is not None
                            else None
                        )
                    ),
                )

                progress_reporter = _make_progress_reporter(session_factory, job_id=ctx.id)
                result = run_refiner_file_remux_pass(
                    settings=settings,
                    path_runtime=path_runtime,
                    relative_media_path=rel.strip(),
                    rules_config=rules_cfg,
                    min_file_age_seconds=op_settings.min_file_age_seconds,
                    refiner_min_input_file_size_mb=max(
                        int(op_settings.refiner_min_input_file_size_mb),
                        int(library.min_file_size_mb) if library is not None else 0,
                    ),
                    minimum_free_disk_space_mb=op_settings.minimum_free_disk_space_mb,
                    media_scope=media_scope,
                    cleanup_session=session,
                    current_job_id=ctx.id,
                    progress_reporter=progress_reporter,
                    pass_through_unchanged=pass_through_unchanged,
                )
                result["job_id"] = ctx.id
                result["library_id"] = int(library.id) if library is not None else library_id
                if result.get("rejection_kind") and library is not None:
                    rejected_action = (
                        "delete_file"
                        if (library.rejected_file_action or "").strip().lower() == "delete_file"
                        else "leave"
                    )
                    result["rejected_file_action"] = rejected_action
                    if rejected_action == "delete_file":
                        result["rejected_cleanup_status"] = "pending"
                        result["rejected_cleanup_detail"] = (
                            "This library is set to delete rejected files. MediaMop recorded the rejection and will now remove only this file."
                        )
                    else:
                        result["rejected_cleanup_status"] = "left_in_place"
                        result["rejected_cleanup_detail"] = (
                            "MediaMop left the rejected file in place because this library's cleanup action is Leave in place."
                        )
                _commit_session_with_retry(session, label="finalize Refiner metadata", required=False)
        if failure_payload is not None:
            _record_failed_result(
                session_factory,
                payload=failure_payload,
                library_id=library_id,
                media_scope=media_scope,
            )
            _report_back(
                settings,
                session_factory,
                payload_json=ctx.payload_json,
                result=failure_payload,
            )
            return
        assert result is not None
        _apply_file_outcome_state(
            session_factory,
            result=result,
            library_id=library_id,
            media_scope=media_scope,
        )
        _record(
            session_factory, payload=result, activity_id=progress_reporter.activity_id if progress_reporter else None
        )
        _finish_rejected_input_cleanup(
            session_factory,
            result=result,
            library_id=library_id,
            media_scope=media_scope,
        )
        _report_back(settings, session_factory, payload_json=ctx.payload_json, result=result)

    return _run
