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
from mediamop.modules.refiner.file_remux_pass.job_kinds import REFINER_FILE_REMUX_PASS_JOB_KIND
from mediamop.modules.refiner.jobs_model import RefinerJob, RefinerJobStatus
from mediamop.modules.refiner.refiner_library_service import list_libraries, seeded_library_for_scope
from mediamop.modules.refiner.refiner_operator_settings_service import (
    ensure_refiner_operator_settings_row,
)
from mediamop.modules.refiner.refiner_path_settings_service import (
    effective_library_work_folder,
    resolved_default_refiner_tv_work_folder,
    resolved_default_refiner_work_folder,
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
    return ".refiner." in name


def _resolved_movie_and_tv_work_roots(*, session: Session, settings: MediaMopSettings) -> tuple[Path, Path]:
    """The work roots for the seeded Movies and TV libraries.

    The sweep is still per scope because a temp file's own scope is what decides whether
    an active pass may be using it; a library with a custom work folder is swept through
    :func:`resolved_library_work_roots`.
    """

    movie = seeded_library_for_scope(session, "movie")
    tv = seeded_library_for_scope(session, "tv")
    # A scope with no seeded library falls back to that scope's default work root rather
    # than to a table that no longer exists (#363). The default is where an unconfigured
    # install already puts its temp files, so the sweep still finds them.
    movie_work = (
        effective_library_work_folder(library=movie, mediamop_home=settings.mediamop_home)[0]
        if movie is not None
        else resolved_default_refiner_work_folder(mediamop_home=settings.mediamop_home)
    )
    tv_work = (
        effective_library_work_folder(library=tv, mediamop_home=settings.mediamop_home)[0]
        if tv is not None
        else resolved_default_refiner_tv_work_folder(mediamop_home=settings.mediamop_home)
    )
    return Path(movie_work).expanduser().resolve(), Path(tv_work).expanduser().resolve()


def resolved_library_work_roots(*, session: Session, settings: MediaMopSettings) -> dict[int, Path]:
    """Every library's work root, so a library with a custom one is not left unswept."""

    out: dict[int, Path] = {}
    for library in list_libraries(session):
        work, _ = effective_library_work_folder(library=library, mediamop_home=settings.mediamop_home)
        out[int(library.id)] = Path(work).expanduser().resolve()
    return out


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
    # "Keep failed work files" exists so a failed remux can be inspected. A sweep that
    # deleted them anyway would make the setting a lie, so it stops here and says why
    # rather than quietly skipping (#339).
    operator = ensure_refiner_operator_settings_row(session)
    if operator.keep_failed_work_files:
        out["temp_cleanup_ran"] = False
        out["temp_cleanup_skipped_reason"] = (
            f"{label} temp files were left alone because 'keep failed work files' is switched on, so a "
            "failed run can be inspected. Turn it off to let MediaMop reclaim them again."
        )
        return out

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
            human = f"{path} — could not remove this file because the system reported it is in use or locked ({exc})."
            out["temp_cleanup_files_skipped"].append(human)
            logger.warning("Refiner work temp sweep (%s): %s", ms, human)

    return out
