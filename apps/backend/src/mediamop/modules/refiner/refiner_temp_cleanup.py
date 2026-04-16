"""Stale Refiner-owned temp files under resolved work/temp roots (Pass 2).

Movies and TV are **separate logical sweeps**: distinct roots, gates, dedupe rows, and result payloads.
Does not touch watched folders, output folders, or non-Refiner filenames.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from mediamop.core.config import MediaMopSettings
from mediamop.modules.refiner.jobs_model import RefinerJob, RefinerJobStatus
from mediamop.modules.refiner.refiner_file_remux_pass_job_kinds import REFINER_FILE_REMUX_PASS_JOB_KIND
from mediamop.modules.refiner.refiner_path_settings_service import (
    effective_tv_work_folder,
    effective_work_folder,
    ensure_refiner_path_settings_row,
)

logger = logging.getLogger(__name__)

REFINER_DRY_RUN_FFMPEG_PLACEHOLDER_NAME = "dry-run-ffmpeg-destination-placeholder.mkv"

RefinerWorkTempSweepMediaScope = Literal["movie", "tv"]


def normalize_work_temp_sweep_media_scope(raw: str | None) -> RefinerWorkTempSweepMediaScope:
    """Normalize sweep / payload scope: only ``movie`` or ``tv``."""

    s = (raw or "movie").strip().lower()
    return "tv" if s == "tv" else "movie"


def is_refiner_owned_temp_work_file(path: Path) -> bool:
    """True only for filenames Refiner's remux pass stack creates under work folders."""

    if not path.is_file():
        return False
    name = path.name
    if name == REFINER_DRY_RUN_FFMPEG_PLACEHOLDER_NAME:
        return True
    if ".refiner." in name:
        return True
    return False


def _resolved_movie_and_tv_work_roots(*, session: Session, settings: MediaMopSettings) -> tuple[Path, Path]:
    row = ensure_refiner_path_settings_row(session)
    movie_work, _ = effective_work_folder(row=row, mediamop_home=settings.mediamop_home)
    tv_work, _ = effective_tv_work_folder(row=row, mediamop_home=settings.mediamop_home)
    return Path(movie_work).expanduser().resolve(), Path(tv_work).expanduser().resolve()


def refiner_file_remux_pass_job_active_for_scope(session: Session, *, media_scope: str) -> bool:
    """True when a ``refiner.file.remux_pass.v1`` row for this ``media_scope`` is pending or leased.

    Payload ``media_scope`` follows manual enqueue (``movie`` / ``tv``). Missing / invalid JSON or
    missing key is treated as **Movies**, matching legacy behavior.
    """

    want = normalize_work_temp_sweep_media_scope(media_scope)
    stmt = select(RefinerJob).where(
        RefinerJob.job_kind == REFINER_FILE_REMUX_PASS_JOB_KIND,
        RefinerJob.status.in_(
            (
                RefinerJobStatus.PENDING.value,
                RefinerJobStatus.LEASED.value,
            ),
        ),
    )
    for job in session.scalars(stmt):
        raw = job.payload_json
        job_scope: RefinerWorkTempSweepMediaScope = "movie"
        if raw and str(raw).strip():
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                job_scope = "movie"
            else:
                if isinstance(data, dict):
                    job_scope = normalize_work_temp_sweep_media_scope(data.get("media_scope"))
                else:
                    job_scope = "movie"
        if job_scope == want:
            return True
    return False


def run_refiner_work_temp_stale_sweep_for_scope(
    *,
    session: Session,
    settings: MediaMopSettings,
    media_scope: str,
    dry_run: bool | None = None,
) -> dict[str, Any]:
    """Sweep **one** scope's effective work root; never the other scope's folder.

    Returns JSON-serializable dict for Activity (bounded by caller).
    """

    ms = normalize_work_temp_sweep_media_scope(media_scope)
    movie_root, tv_root = _resolved_movie_and_tv_work_roots(session=session, settings=settings)
    shared_physical_root = movie_root == tv_root
    root = movie_root if ms == "movie" else tv_root

    label = "TV" if ms == "tv" else "Movies"
    out: dict[str, Any] = {
        "media_scope": ms,
        "temp_cleanup_dry_run": False,
        "temp_cleanup_root_paths": [str(root)],
        "temp_cleanup_candidates_found": 0,
        "temp_cleanup_files_deleted": [],
        "temp_cleanup_files_skipped": [],
        "temp_cleanup_skipped_reason": None,
        "temp_cleanup_ran": False,
        "temp_cleanup_shared_work_root_conflict": bool(shared_physical_root),
    }

    if refiner_file_remux_pass_job_active_for_scope(session, media_scope=ms):
        out["temp_cleanup_skipped_reason"] = (
            f"A {label} Refiner video pass is already waiting or running, so {label} work-folder temp cleanup "
            "was skipped to avoid touching files ffmpeg might still be using."
        )
        logger.info("Refiner work temp sweep skipped (%s): active remux pass for this scope.", ms)
        return out

    if shared_physical_root:
        out["temp_cleanup_skipped_reason"] = (
            f"{label} Refiner uses a work folder that is the same directory on disk as the other scope's "
            "saved work folder. Refiner cannot tell which temp files belong to Movies versus TV here, "
            "so automatic temp deletion for this scope is turned off for safety. "
            "Save **separate** Movies and TV work folders in Refiner path settings to enable cleanup, "
            "or remove temp files yourself if you are sure they are unused."
        )
        logger.warning(
            "Refiner work temp sweep skipped (%s): shared resolved work root %s.",
            ms,
            root,
        )
        return out

    stale_after = max(0, int(settings.refiner_work_temp_stale_sweep_min_stale_age_seconds))
    now = time.time()
    out["temp_cleanup_shared_work_root_conflict"] = False
    out["temp_cleanup_ran"] = True

    if not root.is_dir():
        msg = f"{root} — this {label} work folder is missing or not a directory."
        out["temp_cleanup_files_skipped"].append(msg)
        logger.warning("Refiner work temp sweep (%s): %s", ms, msg)
        return out

    try:
        names = sorted(root.iterdir(), key=lambda p: p.name.lower())
    except OSError as exc:
        msg = f"{root} — could not read this {label} work folder ({exc})."
        out["temp_cleanup_files_skipped"].append(msg)
        logger.warning("Refiner work temp sweep (%s): %s", ms, msg)
        return out

    for path in names:
        if not path.is_file():
            continue
        if not is_refiner_owned_temp_work_file(path):
            continue
        out["temp_cleanup_candidates_found"] += 1
        try:
            age_s = now - float(path.stat().st_mtime)
        except OSError as exc:
            out["temp_cleanup_files_skipped"].append(f"{path} — could not read the file age ({exc}).")
            continue
        if age_s < stale_after:
            out["temp_cleanup_files_skipped"].append(
                f"{path} — not stale enough yet (must be unchanged for at least {stale_after}s).",
            )
            continue
        try:
            path.unlink()
            out["temp_cleanup_files_deleted"].append(str(path))
        except OSError as exc:
            human = (
                f"{path} — could not remove this file because the system reported it is in use or locked ({exc})."
            )
            out["temp_cleanup_files_skipped"].append(human)
            logger.warning("Refiner work temp sweep (%s): %s", ms, human)

    return out
