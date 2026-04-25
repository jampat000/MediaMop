"""In-process Refiner worker handler for ``refiner.watched_folder.remux_scan_dispatch.v1``."""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from mediamop.core.config import MediaMopSettings
from mediamop.modules.refiner.jobs_ops import refiner_enqueue_or_get_job
from mediamop.modules.refiner.refiner_file_remux_pass_job_kinds import REFINER_FILE_REMUX_PASS_JOB_KIND
from mediamop.modules.refiner.refiner_path_settings_service import resolve_refiner_path_runtime_for_remux
from mediamop.modules.refiner.refiner_operator_settings_service import ensure_refiner_operator_settings_row
from mediamop.modules.refiner.refiner_watched_folder_remux_scan_dispatch_activity import (
    record_refiner_watched_folder_remux_scan_dispatch_completed,
)
from mediamop.modules.refiner.refiner_watched_folder_remux_scan_dispatch_evaluate import (
    evaluate_watched_media_file_for_dispatch,
    fetch_radarr_and_sonarr_queue_rows_for_scan,
    format_scan_summary_for_activity,
)
from mediamop.modules.refiner.refiner_watched_folder_remux_scan_dispatch_ops import (
    iter_watched_folder_media_candidate_files,
    refiner_active_remux_pass_exists_for_relative_path,
    relative_posix_path_under_watched,
)
from mediamop.modules.refiner.worker_loop import RefinerJobWorkContext


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
    """Scan saved watched folder, classify each media file with merged *arr queue domain rules, optionally enqueue remux."""

    def _run(ctx: RefinerJobWorkContext) -> None:
        body = _parse_job_payload(ctx.payload_json)
        enqueue_remux_jobs = bool(body.get("enqueue_remux_jobs", False))
        scan_trigger = body.get("scan_trigger", "manual")
        if scan_trigger not in ("manual", "periodic"):
            scan_trigger = "manual"
        media_scope_raw = body.get("media_scope", "movie")
        media_scope = media_scope_raw if media_scope_raw in ("movie", "tv") else "movie"

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
        with session_factory() as arr_session:
            rad_rows, son_rows, rad_err, son_err = fetch_radarr_and_sonarr_queue_rows_for_scan(arr_session, settings)

        watched_path = Path(watched_root)
        files = iter_watched_folder_media_candidate_files(
            watched_path,
            min_file_age_seconds=op_settings.min_file_age_seconds,
        )

        sample_paths: list[str] = []
        summary: dict[str, Any] = {
            "job_id": ctx.id,
            "scan_trigger": scan_trigger,
            "media_scope": media_scope,
            "scan_result_label": "Watched folder checked",
            "watched_folder_resolved": watched_root,
            "enqueue_remux_jobs": enqueue_remux_jobs,
            "min_file_age_seconds": op_settings.min_file_age_seconds,
            "radarr_queue_row_count": len(rad_rows),
            "sonarr_queue_row_count": len(son_rows),
            "radarr_queue_fetch_error": rad_err,
            "sonarr_queue_fetch_error": son_err,
            "media_candidates_seen": len(files),
            "verdict_proceed": 0,
            "verdict_wait_upstream": 0,
            "verdict_not_held": 0,
            "remux_jobs_enqueued": 0,
            "skipped_duplicate_same_scan": 0,
            "skipped_duplicate_active_queue": 0,
            "user_message": "",
            "waiting_message": None,
            "enqueued_relative_paths_sample": sample_paths,
        }

        rel_this_run: set[str] = set()
        sample_cap = 32

        with session_factory() as session:
            with session.begin():
                for file_path in files:
                    verdict = evaluate_watched_media_file_for_dispatch(
                        radarr_rows=rad_rows,
                        sonarr_rows=son_rows,
                        file_path=file_path,
                    )
                    if verdict == "proceed":
                        summary["verdict_proceed"] += 1
                    elif verdict == "wait_upstream":
                        summary["verdict_wait_upstream"] += 1
                    else:
                        summary["verdict_not_held"] += 1

                    if verdict != "proceed" or not enqueue_remux_jobs:
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
                duplicates = int(summary["skipped_duplicate_same_scan"]) + int(summary["skipped_duplicate_active_queue"])
                if queued:
                    summary["scan_result_label"] = "Files added to Refiner"
                    summary["user_message"] = (
                        f"{queued} file{' was' if queued == 1 else 's were'} added to Refiner for processing."
                    )
                elif waiting:
                    summary["scan_result_label"] = "Waiting for files to finish"
                    summary["user_message"] = (
                        f"{waiting} file{' looks' if waiting == 1 else 's look'} like it is still being copied or imported, "
                        "so MediaMop left it alone for now."
                    )
                    summary["waiting_message"] = "MediaMop will check again on the next scheduled scan."
                elif seen and not enqueue_remux_jobs:
                    summary["scan_result_label"] = "Folder checked only"
                    summary["user_message"] = (
                        f"{seen} media file{' was' if seen == 1 else 's were'} found, but this scan was set to check only."
                    )
                elif seen and duplicates:
                    summary["scan_result_label"] = "Already queued"
                    summary["user_message"] = (
                        "MediaMop found matching media files, but they were already waiting for Refiner."
                    )
                elif seen:
                    summary["scan_result_label"] = "No new Refiner work"
                    summary["user_message"] = "MediaMop found media files, but there was nothing new to queue."
                else:
                    summary["scan_result_label"] = "No media found"
                    summary["user_message"] = "MediaMop did not find any media files in this watched folder."

                if int(summary["remux_jobs_enqueued"]) > 0:
                    detail = format_scan_summary_for_activity(summary)
                    record_refiner_watched_folder_remux_scan_dispatch_completed(session, detail=detail)

    return _run
