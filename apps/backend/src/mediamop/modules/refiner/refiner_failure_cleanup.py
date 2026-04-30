"""Refiner Pass 4: periodic cleanup sweep for terminal failed remux jobs."""

from __future__ import annotations

import json
import logging
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from mediamop.core.config import MediaMopSettings
from mediamop.modules.refiner.jobs_model import RefinerJob, RefinerJobStatus
from mediamop.modules.refiner.refiner_candidate_gate_queue_fetch import fetch_arr_v3_queue_rows
from mediamop.modules.refiner.refiner_file_remux_pass_job_kinds import REFINER_FILE_REMUX_PASS_JOB_KIND
from mediamop.modules.refiner.refiner_path_settings_service import (
    effective_tv_work_folder,
    effective_work_folder,
    ensure_refiner_path_settings_row,
)
from mediamop.modules.refiner.refiner_remux_rules import is_refiner_media_candidate
from mediamop.modules.refiner.refiner_watched_folder_remux_scan_dispatch_ops import (
    refiner_active_remux_pass_exists_for_relative_path,
    relative_posix_path_under_watched,
)
from mediamop.platform.arr_library import resolve_radarr_http_credentials, resolve_sonarr_http_credentials

logger = logging.getLogger(__name__)

Scope = Literal["movie", "tv"]


def _scope(raw: str | None) -> Scope:
    return "tv" if (raw or "").strip().lower() == "tv" else "movie"


def _norm_rel(raw: str) -> str:
    p = Path(raw.strip().replace("\\", "/"))
    parts = [x for x in p.parts if x not in (".", "")]
    return Path(*parts).as_posix() if parts else ""


def _parse_payload(payload_json: str | None) -> tuple[str, Scope, bool]:
    if not payload_json or not payload_json.strip():
        raise ValueError("missing payload_json")
    data = json.loads(payload_json)
    if not isinstance(data, dict):
        raise ValueError("payload_json must be object")
    rel = data.get("relative_media_path")
    if not isinstance(rel, str) or not rel.strip():
        raise ValueError("payload missing relative_media_path")
    # Compatibility only: tolerate historic payloads that still carried dry_run.
    return _norm_rel(rel), _scope(data.get("media_scope")), bool(data.get("dry_run"))


def _safe_rmtree(path: Path) -> tuple[bool, str | None]:
    try:
        shutil.rmtree(path)
        return True, None
    except (PermissionError, OSError) as exc:
        msg = f"Could not remove {path} because it is in use or blocked ({exc})."
        logger.warning("Refiner failure cleanup: %s", msg)
        return False, msg


def _safe_unlink(path: Path) -> tuple[bool, str | None]:
    try:
        path.unlink()
        return True, None
    except (PermissionError, OSError) as exc:
        msg = f"Could not remove temp file {path} because it is in use or blocked ({exc})."
        logger.warning("Refiner failure cleanup: %s", msg)
        return False, msg


def _cascade_under_root(*, first_parent: Path, root: Path, out: list[str]) -> None:
    cur = first_parent.resolve()
    rr = root.resolve()
    while cur != rr:
        try:
            cur.relative_to(rr)
        except ValueError:
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
            out.append(str(cur))
        except (PermissionError, OSError):
            break
        cur = cur.parent


def _job_temp_candidates(*, work_root: Path, rel_norm: str) -> list[Path]:
    stem = Path(rel_norm).stem.lower()
    out: list[Path] = []
    if not work_root.is_dir():
        return out
    for child in sorted(work_root.iterdir(), key=lambda p: p.name.lower()):
        if not child.is_file():
            continue
        name = child.name.lower()
        if ".refiner." not in name:
            continue
        if stem and stem in name:
            out.append(child)
    return out


def _movie_queue_contains(*, radarr_rows: list[dict[str, Any]], src_file: Path) -> bool:
    sp = str(src_file.resolve())
    for row in radarr_rows:
        path = row.get("outputPath")
        if isinstance(path, str) and path.strip():
            try:
                if Path(path.strip()).expanduser().resolve() == Path(sp):
                    return True
            except OSError:
                continue
    return False


def _tv_queue_contains(*, sonarr_rows: list[dict[str, Any]], episode: Path) -> bool:
    ep = episode.resolve()
    for row in sonarr_rows:
        path = row.get("outputPath")
        if isinstance(path, str) and path.strip():
            try:
                if Path(path.strip()).expanduser().resolve() == ep:
                    return True
            except OSError:
                continue
    return False


def _failed_jobs_for_scope(
    *,
    session: Session,
    media_scope: Scope,
    older_than: datetime,
) -> list[tuple[RefinerJob, str, bool]]:
    rows = session.scalars(
        select(RefinerJob).where(
            RefinerJob.job_kind == REFINER_FILE_REMUX_PASS_JOB_KIND,
            RefinerJob.status == RefinerJobStatus.FAILED.value,
        )
    ).all()
    out: list[tuple[RefinerJob, str, bool]] = []
    for row in rows:
        row_updated = row.updated_at
        if row_updated.tzinfo is None:
            row_updated = row_updated.replace(tzinfo=UTC)
        if row_updated >= older_than:
            continue
        try:
            rel, scope, legacy_dry_run = _parse_payload(row.payload_json)
        except (ValueError, json.JSONDecodeError):
            logger.debug("Refiner failure cleanup ignored malformed failed-job payload job_id=%s", row.id, exc_info=True)
            continue
        if scope != media_scope:
            continue
        out.append((row, rel, legacy_dry_run))
    return out


def _tv_has_terminal_failed_remux_for_relative_path(session: Session, *, relative_posix: str) -> bool:
    stmt = select(RefinerJob).where(
        RefinerJob.job_kind == REFINER_FILE_REMUX_PASS_JOB_KIND,
        RefinerJob.status == RefinerJobStatus.FAILED.value,
    )
    want = _norm_rel(relative_posix)
    for row in session.scalars(stmt):
        try:
            rel_norm, scope, _dry_run = _parse_payload(row.payload_json)
        except (ValueError, json.JSONDecodeError):
            continue
        if scope != "tv":
            continue
        if rel_norm == want:
            return True
    return False


def run_refiner_failure_cleanup_sweep_for_scope(
    *,
    session: Session,
    settings: MediaMopSettings,
    media_scope: str,
) -> dict[str, Any]:
    ms = _scope(media_scope)
    now = datetime.now(UTC)
    grace = (
        int(settings.refiner_tv_failure_cleanup_grace_period_seconds)
        if ms == "tv"
        else int(settings.refiner_movie_failure_cleanup_grace_period_seconds)
    )
    older_than = now - timedelta(seconds=max(0, grace))
    row = ensure_refiner_path_settings_row(session)
    work_root = Path(
        effective_tv_work_folder(row=row, mediamop_home=settings.mediamop_home)[0]
        if ms == "tv"
        else effective_work_folder(row=row, mediamop_home=settings.mediamop_home)[0]
    ).expanduser().resolve()
    watched_raw = (row.refiner_tv_watched_folder if ms == "tv" else row.refiner_watched_folder) or ""
    output_raw = (row.refiner_tv_output_folder if ms == "tv" else row.refiner_output_folder) or ""
    out: dict[str, Any] = {
        "media_scope": ms,
        "cleanup_run_status": "started",
        "grace_period_seconds": int(grace),
        "eligible_failed_jobs": 0,
        "processed_failed_jobs": 0,
        "skip_reason": None,
        "jobs": [],
    }
    if not watched_raw.strip() or not output_raw.strip():
        out["cleanup_run_status"] = "skipped"
        out["skip_reason"] = (
            "Saved watched/output paths are not configured for this scope, so failure cleanup was skipped safely."
        )
        return out
    watched_root = Path(watched_raw).expanduser().resolve()
    output_root = Path(output_raw).expanduser().resolve()
    failed_rows = _failed_jobs_for_scope(session=session, media_scope=ms, older_than=older_than)
    out["eligible_failed_jobs"] = len(failed_rows)
    if not failed_rows:
        out["cleanup_run_status"] = "no_eligible_files"
        out["skip_reason"] = "No eligible failed Refiner jobs were old enough for cleanup."
        return out

    radarr_rows: list[dict[str, Any]] = []
    sonarr_rows: list[dict[str, Any]] = []
    queue_unreachable: str | None = None
    if ms == "movie":
        base, key = resolve_radarr_http_credentials(session, settings)
        if not base or not key:
            queue_unreachable = "Radarr URL/API key is not configured."
        else:
            try:
                radarr_rows = fetch_arr_v3_queue_rows(base_url=base, api_key=key, app="radarr")
            except RuntimeError as exc:
                queue_unreachable = str(exc)
    else:
        base, key = resolve_sonarr_http_credentials(session, settings)
        if not base or not key:
            queue_unreachable = "Sonarr URL/API key is not configured."
        else:
            try:
                sonarr_rows = fetch_arr_v3_queue_rows(base_url=base, api_key=key, app="sonarr")
            except RuntimeError as exc:
                queue_unreachable = str(exc)

    for job, rel_norm, legacy_dry_run in failed_rows:
        detail: dict[str, Any] = {
            "job_id": int(job.id),
            "relative_media_path": rel_norm,
            f"{'tv' if ms=='tv' else 'movie'}_failure_cleanup_ran": False,
            f"{'tv' if ms=='tv' else 'movie'}_failure_cleanup_skip_reason": None,
            f"{'tv' if ms=='tv' else 'movie'}_failure_cleanup_dry_run": bool(legacy_dry_run),
            f"{'tv' if ms=='tv' else 'movie'}_failure_cleanup_queue_check": "skipped",
            f"{'tv' if ms=='tv' else 'movie'}_failure_cleanup_temp_files_deleted": [],
            f"{'tv' if ms=='tv' else 'movie'}_failure_cleanup_cascade_folders_deleted": [],
        }
        out["processed_failed_jobs"] += 1
        out["jobs"].append(detail)
        if legacy_dry_run:
            logger.debug(
                "Refiner failure cleanup skipped legacy dry-run payload job_id=%s relative_media_path=%s",
                job.id,
                rel_norm,
            )
            detail[f"{'tv' if ms=='tv' else 'movie'}_failure_cleanup_skip_reason"] = (
                "Skipped for compatibility: this failed remux row uses legacy dry_run payload format, "
                "which is not a current Refiner mode."
            )
            continue
        if queue_unreachable:
            detail[f"{'tv' if ms=='tv' else 'movie'}_failure_cleanup_skip_reason"] = (
                f"ARR queue check was unavailable ({queue_unreachable}), so nothing was removed."
            )
            continue
        src_file = (watched_root / Path(rel_norm)).resolve()
        src_folder = src_file.parent
        if ms == "movie":
            detail["movie_failure_cleanup_source_folder_deleted"] = False
            detail["movie_failure_cleanup_source_folder_path"] = str(src_folder)
            detail["movie_failure_cleanup_output_folder_deleted"] = False
            out_folder = (output_root / Path(rel_norm)).resolve().parent
            detail["movie_failure_cleanup_output_folder_path"] = str(out_folder)
            if _movie_queue_contains(radarr_rows=radarr_rows, src_file=src_file):
                detail["movie_failure_cleanup_queue_check"] = "blocked_in_queue"
                detail["movie_failure_cleanup_skip_reason"] = "File is still in Radarr queue, so failure cleanup skipped."
                continue
            detail["movie_failure_cleanup_queue_check"] = "passed_not_in_queue"
            detail["movie_failure_cleanup_ran"] = True
            try:
                src_folder.relative_to(watched_root)
                if src_folder != watched_root and src_folder.is_dir():
                    ok, _ = _safe_rmtree(src_folder)
                    detail["movie_failure_cleanup_source_folder_deleted"] = ok
                    if ok:
                        _cascade_under_root(
                            first_parent=src_folder.parent,
                            root=watched_root,
                            out=detail["movie_failure_cleanup_cascade_folders_deleted"],
                        )
            except ValueError:
                logger.warning(
                    "Refiner movie failure cleanup skipped source folder outside watched root job_id=%s path=%s",
                    job.id,
                    src_folder,
                )
                pass
            try:
                out_folder.relative_to(output_root)
                if out_folder != output_root and out_folder.is_dir():
                    ok, _ = _safe_rmtree(out_folder)
                    detail["movie_failure_cleanup_output_folder_deleted"] = ok
                    if ok:
                        _cascade_under_root(
                            first_parent=out_folder.parent,
                            root=output_root,
                            out=detail["movie_failure_cleanup_cascade_folders_deleted"],
                        )
            except ValueError:
                logger.warning(
                    "Refiner movie failure cleanup skipped output folder outside output root job_id=%s path=%s",
                    job.id,
                    out_folder,
                )
                pass
            for temp in _job_temp_candidates(work_root=work_root, rel_norm=rel_norm):
                ok, _ = _safe_unlink(temp)
                if ok:
                    detail["movie_failure_cleanup_temp_files_deleted"].append(str(temp))
        else:
            detail["tv_failure_cleanup_season_folder_deleted"] = False
            detail["tv_failure_cleanup_output_season_deleted"] = False
            src_season = src_folder
            detail["tv_failure_cleanup_season_folder_path"] = str(src_season)
            out_season = (output_root / Path(rel_norm).parent).resolve()
            detail["tv_failure_cleanup_output_season_path"] = str(out_season)
            episodes = []
            if src_season.is_dir():
                for child in sorted(src_season.iterdir(), key=lambda p: p.name.lower()):
                    if child.is_file() and is_refiner_media_candidate(child):
                        episodes.append(child)
            if not episodes:
                detail["tv_failure_cleanup_skip_reason"] = (
                    "No direct-child episode media files were found in this season folder, so Refiner skipped season cleanup."
                )
                continue
            blocked = False
            for ep in episodes:
                if _tv_queue_contains(sonarr_rows=sonarr_rows, episode=ep):
                    blocked = True
                    break
                try:
                    rel = relative_posix_path_under_watched(watched_root=watched_root, file_path=ep)
                except ValueError:
                    logger.warning(
                        "Refiner TV failure cleanup skipped episode outside watched root job_id=%s path=%s",
                        job.id,
                        ep,
                    )
                    continue
                if refiner_active_remux_pass_exists_for_relative_path(
                    session,
                    relative_posix=rel,
                    media_scope="tv",
                    exclude_job_id=None,
                ):
                    blocked = True
                    break
                if not _tv_has_terminal_failed_remux_for_relative_path(session, relative_posix=rel):
                    blocked = True
                    break
            if blocked:
                detail["tv_failure_cleanup_queue_check"] = "blocked_in_queue_or_active_job"
                detail["tv_failure_cleanup_skip_reason"] = (
                    "TV season is not clear yet (episode still queued, active TV remux exists, or not every direct-child episode has a terminal failed TV remux outcome), so cleanup skipped."
                )
                continue
            detail["tv_failure_cleanup_queue_check"] = "passed_not_in_queue"
            detail["tv_failure_cleanup_ran"] = True
            try:
                src_season.relative_to(watched_root)
                if src_season != watched_root and src_season.is_dir():
                    ok, _ = _safe_rmtree(src_season)
                    detail["tv_failure_cleanup_season_folder_deleted"] = ok
                    if ok:
                        _cascade_under_root(
                            first_parent=src_season.parent,
                            root=watched_root,
                            out=detail["tv_failure_cleanup_cascade_folders_deleted"],
                        )
            except ValueError:
                logger.warning(
                    "Refiner TV failure cleanup skipped season folder outside watched root job_id=%s path=%s",
                    job.id,
                    src_season,
                )
                pass
            try:
                out_season.relative_to(output_root)
                if out_season != output_root and out_season.is_dir():
                    ok, _ = _safe_rmtree(out_season)
                    detail["tv_failure_cleanup_output_season_deleted"] = ok
                    if ok:
                        _cascade_under_root(
                            first_parent=out_season.parent,
                            root=output_root,
                            out=detail["tv_failure_cleanup_cascade_folders_deleted"],
                        )
            except ValueError:
                logger.warning(
                    "Refiner TV failure cleanup skipped output season outside output root job_id=%s path=%s",
                    job.id,
                    out_season,
                )
                pass
            for temp in _job_temp_candidates(work_root=work_root, rel_norm=rel_norm):
                ok, _ = _safe_unlink(temp)
                if ok:
                    detail["tv_failure_cleanup_temp_files_deleted"].append(str(temp))
    out["cleanup_run_status"] = "completed"
    return out

