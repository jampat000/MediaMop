"""Movies-only Refiner output-folder cleanup after a successful remux pass (Pass 3a).

Deletes the **immediate parent directory** of the movie file under the Movies output root when
Radarr library truth, minimum age, and active-job gates all pass. TV scope is never handled here.
"""

from __future__ import annotations

import json
import logging
import shutil
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from mediamop.core.config import MediaMopSettings
from mediamop.platform.arr_library import resolve_radarr_http_credentials
from mediamop.modules.refiner.jobs_model import RefinerJob, RefinerJobStatus
from mediamop.modules.refiner.refiner_file_remux_pass_job_kinds import REFINER_FILE_REMUX_PASS_JOB_KIND
from mediamop.modules.refiner.refiner_path_settings_service import RefinerPathRuntime
from mediamop.platform.outbound_http import normalize_local_service_base_url

logger = logging.getLogger(__name__)
_RADARR_PAGE_SIZE = 200_000


def _normalize_media_scope(raw: str | None) -> str:
    s = (raw or "movie").strip().lower()
    return "tv" if s == "tv" else "movie"


def normalize_relative_media_path_for_match(rel: str) -> str:
    """Stable posix-style path for comparing remux job payloads."""

    p = Path(rel.strip().replace("\\", "/"))
    parts = [x for x in p.parts if x not in (".", "")]
    return Path(*parts).as_posix() if parts else ""


def init_movie_output_cleanup_activity_fields(out: dict[str, Any]) -> None:
    out.setdefault("movie_output_folder_deleted", False)
    out.setdefault("movie_output_folder_path", None)
    out.setdefault("movie_output_folder_skip_reason", None)
    out.setdefault("movie_output_truth_check", None)
    out.setdefault("movie_output_truth_note", None)
    out.setdefault("movie_output_age_seconds", None)
    out.setdefault("movie_output_cascade_folders_deleted", [])
    out.setdefault("movie_output_dry_run", None)


def fetch_radarr_library_movies(
    *,
    base_url: str,
    api_key: str,
    timeout_seconds: float = 60.0,
) -> list[dict[str, Any]]:
    """GET ``/api/v3/movie`` (Refiner-owned stdlib HTTP; same style as queue fetch)."""

    base = normalize_local_service_base_url(base_url)
    # Radarr's movie endpoint effectively behaves as an unpaginated library listing; use a very high cap.
    url = f"{base}/api/v3/movie?pageSize={_RADARR_PAGE_SIZE}"
    req = urllib.request.Request(
        url,
        method="GET",
        headers={"X-Api-Key": api_key, "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        msg = f"Radarr library fetch failed: HTTP {e.code} for {url!r}"
        raise RuntimeError(msg) from e
    except OSError as e:
        msg = f"Radarr library fetch failed: could not reach Radarr ({e})."
        raise RuntimeError(msg) from e
    data = json.loads(raw)
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    return []


def radarr_library_moviefile_paths_under_folder(
    *,
    movies: list[dict[str, Any]],
    folder: Path,
) -> list[Path]:
    """Return Radarr ``movieFile.path`` values that resolve **inside** ``folder`` (inclusive)."""

    folder_r = folder.resolve()
    hits: list[Path] = []
    for m in movies:
        mf = m.get("movieFile")
        if not isinstance(mf, dict):
            continue
        raw_path = mf.get("path")
        if not isinstance(raw_path, str) or not raw_path.strip():
            continue
        try:
            pr = Path(raw_path.strip()).expanduser().resolve()
        except OSError:
            continue
        try:
            pr.relative_to(folder_r)
        except ValueError:
            continue
        hits.append(pr)
    return hits


def newest_mtime_seconds_under_tree(root: Path) -> float | None:
    """Newest ``st_mtime`` among all files under ``root`` (recursive). ``None`` if unreadable."""

    newest: float | None = None
    try:
        for p in root.rglob("*"):
            if not p.is_file():
                continue
            try:
                mt = float(p.stat().st_mtime)
            except OSError:
                continue
            newest = mt if newest is None else max(newest, mt)
    except OSError:
        return None
    return newest


def movie_remux_pass_active_blocking_same_relative_path(
    session: Session,
    *,
    relative_media_path_norm: str,
    exclude_job_id: int | None,
) -> bool:
    """Another Movies remux pass pending/leased for the same source relative path blocks output cleanup."""

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
        job_rel_norm = ""
        if raw and str(raw).strip():
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict):
                job_scope = _normalize_media_scope(data.get("media_scope"))
                jr = data.get("relative_media_path")
                if isinstance(jr, str) and jr.strip():
                    job_rel_norm = normalize_relative_media_path_for_match(jr)
        if job_scope == "tv":
            continue
        if job_rel_norm and job_rel_norm == relative_media_path_norm:
            return True
    return False


def _cascade_delete_empty_parents_under_output_root(
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
                "Refiner Movies output cleanup: stopped cascade because folder is outside the output root (%s).",
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
                "Refiner Movies output cleanup: could not remove an empty parent folder (%s): %s",
                cur,
                exc,
            )
            break
        cur = cur.parent


def maybe_run_movie_output_folder_cleanup_after_remux(
    *,
    session: Session | None,
    settings: MediaMopSettings,
    path_runtime: RefinerPathRuntime,
    watched_root: Path,
    src: Path,
    final_output_file: Path | None,
    dry_run: bool | None = None,
    relative_media_path: str,
    current_job_id: int | None,
    media_scope: str | None,
    out: dict[str, Any],
) -> None:
    """Populate ``movie_output_*`` fields; may delete the movie output folder when all gates pass."""

    init_movie_output_cleanup_activity_fields(out)
    out["movie_output_dry_run"] = False

    scope = _normalize_media_scope(media_scope)
    if scope != "movie":
        out["movie_output_folder_skip_reason"] = (
            "This cleanup step applies only to Movies. TV output cleanup is separate and was not run here."
        )
        out["movie_output_truth_check"] = "skipped"
        out["movie_output_truth_note"] = out["movie_output_folder_skip_reason"]
        return

    if session is None:
        out["movie_output_folder_skip_reason"] = (
            "Refiner could not run Movies output-folder cleanup because no database session was available (internal error)."
        )
        out["movie_output_truth_check"] = "skipped"
        out["movie_output_truth_note"] = out["movie_output_folder_skip_reason"]
        return

    out_root_raw = (path_runtime.output_folder or "").strip()
    if not out_root_raw:
        out["movie_output_folder_skip_reason"] = "No Movies output folder is configured, so Refiner did not evaluate output-folder cleanup."
        out["movie_output_truth_check"] = "skipped"
        out["movie_output_truth_note"] = out["movie_output_folder_skip_reason"]
        return

    try:
        output_root = Path(out_root_raw).expanduser().resolve()
    except OSError as exc:
        out["movie_output_folder_skip_reason"] = f"Refiner could not resolve the Movies output folder path ({exc})."
        out["movie_output_truth_check"] = "skipped"
        out["movie_output_truth_note"] = out["movie_output_folder_skip_reason"]
        return

    if not output_root.is_dir():
        out["movie_output_folder_skip_reason"] = "The Movies output folder is missing on disk, so output-folder cleanup was skipped."
        out["movie_output_truth_check"] = "skipped"
        out["movie_output_truth_note"] = out["movie_output_folder_skip_reason"]
        return

    watched_resolved = watched_root.resolve()
    src_resolved = src.resolve()
    try:
        rel_under_watched = src_resolved.relative_to(watched_resolved)
    except ValueError:
        out["movie_output_folder_skip_reason"] = (
            "The source file is not under the saved Movies watched folder, so output-folder cleanup was skipped."
        )
        out["movie_output_truth_check"] = "skipped"
        out["movie_output_truth_note"] = out["movie_output_folder_skip_reason"]
        return

    if final_output_file is not None:
        media_out = final_output_file.resolve()
    else:
        media_out = (output_root / rel_under_watched).resolve()

    try:
        media_out.relative_to(output_root)
    except ValueError:
        out["movie_output_folder_skip_reason"] = (
            "The expected movie file path would sit outside the Movies output folder, so output-folder cleanup was skipped."
        )
        out["movie_output_truth_check"] = "skipped"
        out["movie_output_truth_note"] = out["movie_output_folder_skip_reason"]
        return

    output_movie_folder = media_out.parent
    try:
        output_movie_folder.relative_to(output_root)
    except ValueError:
        out["movie_output_folder_skip_reason"] = (
            "The movie output folder would sit outside the Movies output root, so Refiner did not change it."
        )
        out["movie_output_truth_check"] = "skipped"
        out["movie_output_truth_note"] = out["movie_output_folder_skip_reason"]
        return

    if output_movie_folder.resolve() == output_root.resolve():
        out["movie_output_folder_skip_reason"] = (
            "The movie file sits directly in the Movies output folder root, so Refiner does not remove a per-title folder here."
        )
        out["movie_output_truth_check"] = "skipped"
        out["movie_output_truth_note"] = out["movie_output_folder_skip_reason"]
        return

    out["movie_output_folder_path"] = str(output_movie_folder)
    rel_norm = normalize_relative_media_path_for_match(relative_media_path)
    if rel_norm and movie_remux_pass_active_blocking_same_relative_path(
        session,
        relative_media_path_norm=rel_norm,
        exclude_job_id=current_job_id,
    ):
        out["movie_output_folder_skip_reason"] = (
            "Another Movies Refiner video pass is already waiting or running for this same watched file path, "
            "so output-folder cleanup was skipped to avoid racing another remux."
        )
        out["movie_output_truth_check"] = "skipped"
        out["movie_output_truth_note"] = out["movie_output_folder_skip_reason"]
        return

    min_age = max(0, int(settings.refiner_movie_output_cleanup_min_age_seconds))
    newest = newest_mtime_seconds_under_tree(output_movie_folder)
    if newest is None:
        out["movie_output_folder_skip_reason"] = (
            "Refiner could not read file timestamps under the movie output folder, so nothing was removed for safety."
        )
        out["movie_output_truth_check"] = "skipped"
        out["movie_output_truth_note"] = out["movie_output_folder_skip_reason"]
        return
    age_s = time.time() - newest
    out["movie_output_age_seconds"] = int(max(0.0, age_s))
    if age_s < min_age:
        out["movie_output_folder_skip_reason"] = (
            f"This movie output folder was changed too recently (everything under it must be at least {min_age}s old; "
            f"newest file age is about {int(max(0, age_s))}s)."
        )
        out["movie_output_truth_check"] = "skipped"
        out["movie_output_truth_note"] = out["movie_output_folder_skip_reason"]
        return

    base, key = resolve_radarr_http_credentials(session, settings)
    if not base or not key:
        out["movie_output_folder_skip_reason"] = (
            "Radarr URL or API key is not configured in MediaMop, so Refiner could not verify Radarr library paths. "
            "The movie output folder was left in place."
        )
        out["movie_output_truth_check"] = "skipped"
        out["movie_output_truth_note"] = out["movie_output_folder_skip_reason"]
        return

    try:
        movies = fetch_radarr_library_movies(base_url=base, api_key=key)
    except RuntimeError as exc:
        out["movie_output_folder_skip_reason"] = (
            f"Radarr could not be reached or returned an error while reading the movie library, so the output folder was not removed ({exc})."
        )
        out["movie_output_truth_check"] = "skipped"
        out["movie_output_truth_note"] = str(exc)
        logger.warning("Refiner Movies output cleanup: %s", exc)
        return

    hits = radarr_library_moviefile_paths_under_folder(movies=movies, folder=output_movie_folder)
    if hits:
        sample = "; ".join(str(p) for p in hits[:3])
        if len(hits) > 3:
            sample += f" (+{len(hits) - 3} more)"
        out["movie_output_truth_check"] = "failed"
        out["movie_output_truth_note"] = (
            "Radarr still reports at least one library movie file inside this output folder, so Refiner treats it as "
            f"the kept library location and will not delete it. Example path(s): {sample}"
        )
        out["movie_output_folder_skip_reason"] = out["movie_output_truth_note"]
        return

    out["movie_output_truth_check"] = "passed"
    out["movie_output_truth_note"] = (
        "Radarr reports no library movie file paths inside this folder, so Refiner treated it as safe to remove under the other gates."
    )

    cascade: list[str] = out["movie_output_cascade_folders_deleted"]  # type: ignore[assignment]

    try:
        shutil.rmtree(output_movie_folder)
    except OSError as exc:
        locked = getattr(exc, "filename", None)
        human = (
            f"Refiner could not remove the movie output folder because a file or folder was in use or blocked ({exc})."
        )
        if locked:
            human += f" Problem path reported by the system: {locked}."
        out["movie_output_folder_skip_reason"] = human
        out["movie_output_folder_deleted"] = False
        out["movie_output_truth_check"] = "skipped"
        out["movie_output_truth_note"] = human
        logger.warning("Refiner Movies output cleanup: %s", human)
        return

    out["movie_output_folder_deleted"] = True
    out["movie_output_folder_skip_reason"] = None
    _cascade_delete_empty_parents_under_output_root(
        first_parent=output_movie_folder.parent,
        output_root=output_root,
        cascade_folders_deleted=cascade,
    )
