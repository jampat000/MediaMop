"""Persist Activity rows for Fetcher failed-import download-queue passes (operator-facing trail).

Execution is still driven by refiner job rows; summaries are attributed to module ``fetcher``.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

from sqlalchemy.orm import Session

from mediamop.platform.activity import constants as C
from mediamop.platform.activity.service import record_activity_event


def _drive_summary_title_detail(*, movies: bool, outcome_values: Sequence[str]) -> tuple[str, str | None]:
    """Build plain title/detail from per-row execution outcome values (``no_op``, etc.)."""

    app = "Radarr" if movies else "Sonarr"
    media = "movie" if movies else "TV show"
    n = len(outcome_values)
    removed = sum(1 for v in outcome_values if v == "removed_queue_item")
    skipped_rules = sum(1 for v in outcome_values if v == "no_op")
    skipped_id = sum(1 for v in outcome_values if v == "skipped_missing_queue_item_id")

    if n == 0:
        return (
            f"Fetcher checked {media} failed imports; the {app} download queue had no rows to review.",
            None,
        )

    if removed > 0:
        item_word = "item" if removed == 1 else "items"
        title = f"Fetcher checked {media} failed imports and removed {removed} eligible queue {item_word}."
        parts: list[str] = []
        if n > removed:
            parts.append(f"Reviewed {n} queue row(s).")
        if skipped_rules:
            w = "row was" if skipped_rules == 1 else "rows were"
            parts.append(
                f"{skipped_rules} queue {w} not eligible to remove under the current cleanup rules.",
            )
        if skipped_id:
            w = "row was" if skipped_id == 1 else "rows were"
            parts.append(f"{skipped_id} queue {w} marked for removal but had no queue id.")
        return title, " ".join(parts) if parts else None

    # Reviewed at least one row; nothing removed.
    if skipped_id == n and skipped_rules == 0:
        w = "row" if n == 1 else "rows"
        return (
            f"Fetcher checked {media} failed imports but could not remove {n} queue {w} "
            "because queue identifiers were missing.",
            None,
        )

    title = (
        f"Fetcher checked {media} failed imports, reviewed {n} queue row(s), "
        "and did not remove anything eligible under the current cleanup rules."
    )
    if skipped_id:
        w = "row was" if skipped_id == 1 else "rows were"
        detail = f"{skipped_id} queue {w} marked for removal but had no queue id."
        return title, detail
    return title, None


def record_fetcher_failed_import_run_started(db: Session, *, movies: bool) -> None:
    """Persist when the in-process worker actually begins a download-queue pass (after config is present)."""

    media = "movie" if movies else "TV show"
    app = "Radarr" if movies else "Sonarr"
    record_activity_event(
        db,
        event_type=C.FETCHER_FAILED_IMPORT_RUN_STARTED,
        module="fetcher",
        title=f"Fetcher started checking {media} failed imports ({app} download queue).",
        detail=None,
    )


def record_fetcher_failed_import_pass_queued(
    db: Session,
    *,
    movies: bool,
    source: Literal["manual", "timed_schedule"],
    queue_outcome: Literal["created", "already_present"] | None = None,
) -> None:
    """Persist queue/scheduling intent — not claim that the pass has already executed."""

    media = "movie" if movies else "TV show"
    app = "Radarr" if movies else "Sonarr"

    if source == "manual":
        if queue_outcome is None:
            msg = "queue_outcome is required when source is manual"
            raise TypeError(msg)
        if queue_outcome == "created":
            title = f"Fetcher added a {media} failed-import download-queue pass to the work queue."
            detail = f"The {app} pass is waiting for the worker; it does not run in the browser."
        else:
            title = (
                f"Fetcher recorded a manual request for the {media} failed-import pass; "
                "that pass was already waiting or still in progress."
            )
            detail = None
    else:
        title = (
            f"Fetcher timed schedule added a {media} failed-import download-queue pass to the work queue."
        )
        detail = f"Uses the configured {app} interval; the pass runs when the worker picks it up."

    record_activity_event(
        db,
        event_type=C.FETCHER_FAILED_IMPORT_PASS_QUEUED,
        module="fetcher",
        title=title,
        detail=detail,
    )


def record_fetcher_failed_import_drive_finished(
    db: Session,
    *,
    movies: bool,
    outcome_values: Sequence[str],
) -> None:
    title, detail = _drive_summary_title_detail(movies=movies, outcome_values=outcome_values)
    record_activity_event(
        db,
        event_type=C.FETCHER_FAILED_IMPORT_RUN_SUMMARY,
        module="fetcher",
        title=title,
        detail=detail,
    )


def record_fetcher_failed_import_drive_failed(
    db: Session,
    *,
    movies: bool,
    exc: Exception,
) -> None:
    media = "movie" if movies else "TV show"
    msg = str(exc).strip() or exc.__class__.__name__
    record_activity_event(
        db,
        event_type=C.FETCHER_FAILED_IMPORT_RUN_FAILED,
        module="fetcher",
        title=f"Fetcher {media} failed-import run stopped because of an error.",
        detail=msg[:4000],
    )


def record_fetcher_failed_import_recovered(
    db: Session,
    *,
    job_id: int,
    job_kind: str,
) -> None:
    from mediamop.modules.fetcher.radarr_failed_import_cleanup_job import (
        REFINER_JOB_KIND_RADARR_FAILED_IMPORT_CLEANUP_DRIVE,
    )
    from mediamop.modules.fetcher.sonarr_failed_import_cleanup_job import (
        REFINER_JOB_KIND_SONARR_FAILED_IMPORT_CLEANUP_DRIVE,
    )

    if job_kind == REFINER_JOB_KIND_RADARR_FAILED_IMPORT_CLEANUP_DRIVE:
        scope = "movies (Radarr)"
    elif job_kind == REFINER_JOB_KIND_SONARR_FAILED_IMPORT_CLEANUP_DRIVE:
        scope = "TV (Sonarr)"
    else:
        scope = "download queue pass"

    record_activity_event(
        db,
        event_type=C.FETCHER_FAILED_IMPORT_RECOVERED,
        module="fetcher",
        title="Fetcher recovery marked a failed-import task completed (the download pass was not re-run).",
        detail=f"Task {job_id} — {scope}.",
    )
