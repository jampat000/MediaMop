"""TV-only Refiner output-folder cleanup after a successful remux pass (Pass 3b).

Deletes the **season output folder** (immediate parent of the episode file under the TV output root) when
media manager library truth, minimum age (direct-child episode media only), and active TV remux gates pass.
Movies scope is never handled here — do not import Movies output cleanup helpers.

Library truth comes from the media manager port, so every manager looking after TV is asked
and any one of them keeping a file inside the season folder stops the delete. A manager that
cannot answer stops it too — see :mod:`mediamop.modules.refiner.manager_library_truth`.
"""

from __future__ import annotations

import json
import logging
import shutil
import time
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from mediamop.core.config import MediaMopSettings
from mediamop.modules.refiner.file_remux_pass.job_kinds import REFINER_FILE_REMUX_PASS_JOB_KIND
from mediamop.modules.refiner.jobs_model import RefinerJob, RefinerJobStatus
from mediamop.modules.refiner.manager_library_truth import evaluate_library_truth_for_folder
from mediamop.modules.refiner.refiner_path_settings_service import RefinerPathRuntime
from mediamop.modules.refiner.refiner_remux_rules import is_refiner_media_candidate
from mediamop.platform.media_managers.manager_binding import collect_library_truth

logger = logging.getLogger(__name__)


def _normalize_media_scope(raw: str | None) -> str:
    s = (raw or "movie").strip().lower()
    return "tv" if s == "tv" else "movie"


def normalize_relative_media_path_for_match(rel: str) -> str:
    """Stable posix-style path for comparing remux job payloads (TV Pass 3b; matches Pass 3a normalization)."""

    p = Path(rel.strip().replace("\\", "/"))
    parts = [x for x in p.parts if x not in (".", "")]
    return Path(*parts).as_posix() if parts else ""


def init_tv_output_cleanup_activity_fields(out: dict[str, Any]) -> None:
    out.setdefault("tv_output_season_folder_deleted", False)
    out.setdefault("tv_output_season_folder_path", None)
    out.setdefault("tv_output_season_folder_skip_reason", None)
    out.setdefault("tv_output_truth_check", None)
    out.setdefault("tv_output_truth_note", None)
    out.setdefault("tv_output_age_seconds", None)
    out.setdefault("tv_output_cascade_folders_deleted", [])
    out.setdefault("tv_output_dry_run", None)


def iter_direct_child_refiner_media_candidates(season_folder: Path) -> list[Path]:
    """Episode decision set: supported media files that are **direct children** of the season folder only."""

    root = season_folder.resolve()
    found: list[Path] = []
    try:
        for p in sorted(root.iterdir()):
            if not p.is_file():
                continue
            if not is_refiner_media_candidate(p):
                continue
            found.append(p)
    except OSError:
        return []
    return found


def newest_mtime_direct_child_media_candidates(season_folder: Path) -> float | None:
    """Newest ``st_mtime`` among direct-child Refiner media candidates. ``None`` if none or unreadable."""

    newest: float | None = None
    for p in iter_direct_child_refiner_media_candidates(season_folder):
        try:
            mt = float(p.stat().st_mtime)
        except OSError:
            continue
        newest = mt if newest is None else max(newest, mt)
    return newest


def _expected_tv_output_file_path(*, output_root: Path, relative_media_path: str) -> Path | None:
    rel_norm = normalize_relative_media_path_for_match(relative_media_path)
    if not rel_norm:
        return None
    try:
        return (output_root / Path(rel_norm)).resolve()
    except OSError:
        return None


def tv_remux_pass_active_blocking_same_season_output_folder(
    session: Session,
    *,
    output_root: Path,
    candidate_season_folder: Path,
    exclude_job_id: int | None,
) -> bool:
    """Another **TV** remux pass pending/leased whose expected output maps to the same season folder blocks cleanup."""

    out_r = output_root.resolve()
    cand = candidate_season_folder.resolve()

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
        if exclude_job_id is not None and int(job.id) == int(exclude_job_id):
            continue
        raw = job.payload_json
        job_scope = "movie"
        job_rel = ""
        if raw and str(raw).strip():
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict):
                js = data.get("media_scope")
                if isinstance(js, str) and js.strip().lower() == "tv":
                    job_scope = "tv"
                elif isinstance(js, str) and js.strip().lower() == "movie":
                    job_scope = "movie"
                else:
                    job_scope = "movie"
                jr = data.get("relative_media_path")
                if isinstance(jr, str) and jr.strip():
                    job_rel = jr.strip()
        if job_scope != "tv":
            continue
        expected = _expected_tv_output_file_path(output_root=out_r, relative_media_path=job_rel)
        if expected is None:
            continue
        try:
            expected.relative_to(out_r)
        except ValueError:
            continue
        job_season = expected.parent.resolve()
        if job_season == cand:
            return True
    return False


def _cascade_delete_empty_parents_under_tv_output_root(
    *,
    first_parent: Path,
    output_root: Path,
    cascade_folders_deleted: list[str],
) -> None:
    """Remove empty parents up to but not including ``output_root``."""

    root = output_root.resolve()
    cur = first_parent.resolve()
    while cur != root:
        try:
            cur.relative_to(root)
        except ValueError:
            logger.warning(
                "Refiner TV output cleanup: stopped cascade because folder is outside the TV output root (%s).",
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
                "Refiner TV output cleanup: could not remove an empty parent folder (%s): %s",
                cur,
                exc,
            )
            break
        cur = cur.parent


def maybe_run_tv_output_season_folder_cleanup_after_remux(
    *,
    session: Session | None,
    settings: MediaMopSettings,
    path_runtime: RefinerPathRuntime,
    watched_root: Path,
    src: Path,
    final_output_file: Path | None,
    relative_media_path: str,
    current_job_id: int | None,
    media_scope: str | None,
    out: dict[str, Any],
) -> None:
    """Populate ``tv_output_*`` fields; may delete the TV season output folder when all gates pass."""

    init_tv_output_cleanup_activity_fields(out)
    out["tv_output_dry_run"] = False

    scope = _normalize_media_scope(media_scope)
    if scope != "tv":
        out["tv_output_season_folder_skip_reason"] = (
            "This cleanup step applies only to TV. Movies output-folder cleanup is separate and was not run here."
        )
        out["tv_output_truth_check"] = "skipped"
        out["tv_output_truth_note"] = out["tv_output_season_folder_skip_reason"]
        return

    if session is None:
        out["tv_output_season_folder_skip_reason"] = (
            "Refiner could not run TV output-folder cleanup because no database session was available (internal error)."
        )
        out["tv_output_truth_check"] = "skipped"
        out["tv_output_truth_note"] = out["tv_output_season_folder_skip_reason"]
        return

    out_root_raw = (path_runtime.output_folder or "").strip()
    if not out_root_raw:
        out["tv_output_season_folder_skip_reason"] = (
            "No TV output folder is configured, so Refiner did not evaluate TV output-folder cleanup."
        )
        out["tv_output_truth_check"] = "skipped"
        out["tv_output_truth_note"] = out["tv_output_season_folder_skip_reason"]
        return

    try:
        output_root = Path(out_root_raw).expanduser().resolve()
    except OSError as exc:
        out["tv_output_season_folder_skip_reason"] = f"Refiner could not resolve the TV output folder path ({exc})."
        out["tv_output_truth_check"] = "skipped"
        out["tv_output_truth_note"] = out["tv_output_season_folder_skip_reason"]
        return

    if not output_root.is_dir():
        out["tv_output_season_folder_skip_reason"] = (
            "The TV output folder is missing on disk, so TV output-folder cleanup was skipped."
        )
        out["tv_output_truth_check"] = "skipped"
        out["tv_output_truth_note"] = out["tv_output_season_folder_skip_reason"]
        return

    watched_resolved = watched_root.resolve()
    src_resolved = src.resolve()
    try:
        rel_under_watched = src_resolved.relative_to(watched_resolved)
    except ValueError:
        out["tv_output_season_folder_skip_reason"] = (
            "The source file is not under the saved TV watched folder, so TV output-folder cleanup was skipped."
        )
        out["tv_output_truth_check"] = "skipped"
        out["tv_output_truth_note"] = out["tv_output_season_folder_skip_reason"]
        return

    if final_output_file is not None:
        media_out = final_output_file.resolve()
    else:
        media_out = (output_root / rel_under_watched).resolve()

    try:
        media_out.relative_to(output_root)
    except ValueError:
        out["tv_output_season_folder_skip_reason"] = (
            "The expected TV episode file path would sit outside the TV output folder, so TV output-folder cleanup was skipped."
        )
        out["tv_output_truth_check"] = "skipped"
        out["tv_output_truth_note"] = out["tv_output_season_folder_skip_reason"]
        return

    output_season_folder = media_out.parent
    try:
        output_season_folder.relative_to(output_root)
    except ValueError:
        out["tv_output_season_folder_skip_reason"] = (
            "The TV season output folder would sit outside the TV output root, so Refiner did not change it."
        )
        out["tv_output_truth_check"] = "skipped"
        out["tv_output_truth_note"] = out["tv_output_season_folder_skip_reason"]
        return

    if output_season_folder.resolve() == output_root.resolve():
        out["tv_output_season_folder_skip_reason"] = (
            "The episode file sits directly in the TV output folder root, so Refiner does not remove a season folder here."
        )
        out["tv_output_truth_check"] = "skipped"
        out["tv_output_truth_note"] = out["tv_output_season_folder_skip_reason"]
        return

    out["tv_output_season_folder_path"] = str(output_season_folder)

    if tv_remux_pass_active_blocking_same_season_output_folder(
        session,
        output_root=output_root,
        candidate_season_folder=output_season_folder,
        exclude_job_id=current_job_id,
    ):
        out["tv_output_season_folder_skip_reason"] = (
            "Another TV Refiner video pass is already waiting or running for an episode whose output maps to this same "
            "season folder under your TV output library, so TV output-folder cleanup was skipped to avoid racing another remux."
        )
        out["tv_output_truth_check"] = "skipped"
        out["tv_output_truth_note"] = out["tv_output_season_folder_skip_reason"]
        return

    direct_eps = iter_direct_child_refiner_media_candidates(output_season_folder)
    if not direct_eps:
        out["tv_output_season_folder_skip_reason"] = (
            "Refiner did not find any supported episode media file as a direct child of this season output folder, "
            "so it could not apply the minimum-age gate for TV output cleanup. The folder was left in place."
        )
        out["tv_output_truth_check"] = "skipped"
        out["tv_output_truth_note"] = out["tv_output_season_folder_skip_reason"]
        return

    min_age = max(0, int(settings.refiner_tv_output_cleanup_min_age_seconds))
    newest = newest_mtime_direct_child_media_candidates(output_season_folder)
    if newest is None:
        out["tv_output_season_folder_skip_reason"] = (
            "Refiner could not read timestamps for direct-child episode files in this season output folder, so nothing was removed for safety."
        )
        out["tv_output_truth_check"] = "skipped"
        out["tv_output_truth_note"] = out["tv_output_season_folder_skip_reason"]
        return
    age_s = time.time() - newest
    out["tv_output_age_seconds"] = int(max(0.0, age_s))
    if age_s < min_age:
        out["tv_output_season_folder_skip_reason"] = (
            f"Direct-child episode media in this TV season output folder was modified too recently "
            f"(each must be at least {min_age}s old by newest file; newest is about {int(max(0, age_s))}s)."
        )
        out["tv_output_truth_check"] = "skipped"
        out["tv_output_truth_note"] = out["tv_output_season_folder_skip_reason"]
        return

    truth = evaluate_library_truth_for_folder(
        collect_library_truth(session, settings, media_scope="tv"),
        folder=output_season_folder,
        media_scope="tv",
    )
    out["tv_output_truth_check"] = truth.check
    out["tv_output_truth_note"] = truth.note
    if not truth.clears_delete:
        out["tv_output_season_folder_skip_reason"] = truth.note
        if truth.check == "skipped":
            logger.warning("Refiner TV output cleanup: %s", truth.note)
        return

    cascade: list[str] = out["tv_output_cascade_folders_deleted"]

    try:
        shutil.rmtree(output_season_folder)
    except OSError as exc:
        locked = getattr(exc, "filename", None)
        human = f"Refiner could not remove the TV season output folder because a file or folder was in use or blocked ({exc})."
        if locked:
            human += f" Problem path reported by the system: {locked}."
        out["tv_output_season_folder_skip_reason"] = human
        out["tv_output_season_folder_deleted"] = False
        out["tv_output_truth_check"] = "skipped"
        out["tv_output_truth_note"] = human
        logger.warning("Refiner TV output cleanup: %s", human)
        return

    out["tv_output_season_folder_deleted"] = True
    out["tv_output_season_folder_skip_reason"] = None
    _cascade_delete_empty_parents_under_tv_output_root(
        first_parent=output_season_folder.parent,
        output_root=output_root,
        cascade_folders_deleted=cascade,
    )
