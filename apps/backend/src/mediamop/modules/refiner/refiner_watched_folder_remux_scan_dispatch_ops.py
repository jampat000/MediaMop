"""Filesystem scan helpers and duplicate guards for watched-folder remux scan dispatch."""

from __future__ import annotations

import json
import re
import shutil
import time
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from mediamop.modules.refiner.jobs_model import RefinerJob, RefinerJobStatus
from mediamop.modules.refiner.refiner_file_remux_pass_job_kinds import REFINER_FILE_REMUX_PASS_JOB_KIND
from mediamop.modules.refiner.refiner_remux_rules import is_refiner_media_candidate
from mediamop.platform.activity.models import ActivityEvent

_HASH_ARTIFACT_STEM_RE = re.compile(r"^[a-fA-F0-9]{32,64}$")
_TRANSIENT_DOWNLOAD_DIR_MARKERS = {
    ".sabnzbd",
    "__admin__",
    "_failed_",
    "_unpack_",
    "_repair_",
    "incomplete",
}


def is_transient_download_artifact_media_path(path: Path) -> bool:
    """True for media-shaped files that are still downloader staging artifacts."""

    stem = path.stem.strip()
    if _HASH_ARTIFACT_STEM_RE.fullmatch(stem):
        return True

    parts = {part.strip().lower() for part in path.parts}
    return bool(parts.intersection(_TRANSIENT_DOWNLOAD_DIR_MARKERS))


def _expected_output_file_for_relative_path(*, output_root: Path, relative_posix: str) -> Path | None:
    root = output_root.expanduser().resolve()
    parts = [part for part in relative_posix.split("/") if part and part not in {".", ".."}]
    if not parts:
        return None
    candidate = root.joinpath(*parts).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    return candidate


def _existing_completed_output_path_is_safe(path: Path) -> bool:
    try:
        return path.is_file() and path.stat().st_size > 0
    except OSError:
        return False


def iter_watched_folder_media_candidate_files(watched_root: Path, *, min_file_age_seconds: int = 0) -> list[Path]:
    """Sorted candidate files under ``watched_root`` honoring optional minimum file-age guardrail."""

    root = watched_root.resolve()
    now = time.time()
    min_age = max(0, int(min_file_age_seconds))
    found: list[Path] = []
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        if not is_refiner_media_candidate(p):
            continue
        if is_transient_download_artifact_media_path(p):
            continue
        try:
            p.resolve().relative_to(root)
        except ValueError:
            continue
        if min_age > 0:
            try:
                age_s = now - float(p.stat().st_mtime)
            except OSError:
                continue
            if age_s < min_age:
                continue
        found.append(p)
    return found


def relative_posix_path_under_watched(*, watched_root: Path, file_path: Path) -> str:
    return file_path.resolve().relative_to(watched_root.resolve()).as_posix()


def refiner_active_remux_pass_exists_for_relative_path(
    session: Session,
    *,
    relative_posix: str,
    media_scope: str = "movie",
    exclude_job_id: int | None = None,
) -> bool:
    """True when a pending or leased ``refiner.file.remux_pass.v1`` row already carries this relative path + scope."""

    want_scope = media_scope if media_scope in ("movie", "tv") else "movie"
    rows = session.scalars(
        select(RefinerJob).where(
            RefinerJob.job_kind == REFINER_FILE_REMUX_PASS_JOB_KIND,
            RefinerJob.status.in_(
                (
                    RefinerJobStatus.PENDING.value,
                    RefinerJobStatus.LEASED.value,
                ),
            ),
        ),
    ).all()
    for job in rows:
        if exclude_job_id is not None and int(job.id) == int(exclude_job_id):
            continue
        raw = (job.payload_json or "").strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(data, dict):
            continue
        rel = data.get("relative_media_path")
        job_scope = data.get("media_scope", "movie")
        if not isinstance(job_scope, str) or job_scope not in ("movie", "tv"):
            job_scope = "movie"
        if isinstance(rel, str) and rel.strip() == relative_posix and job_scope == want_scope:
            return True
    return False


def refiner_completed_remux_output_exists_for_relative_path(
    session: Session,
    *,
    relative_posix: str,
    media_scope: str = "movie",
    output_root: Path | str | None = None,
) -> bool:
    """True when this file already completed successfully and its output still exists.

    This prevents a watched-folder loop when a successful remux writes output but
    Windows/NAS locking stops MediaMop from deleting the source folder. The source
    remains visible to the next scan, but the successful output is the lifecycle
    truth and the file should not be remuxed again unless that output disappears.
    """

    want_scope = media_scope if media_scope in ("movie", "tv") else "movie"
    rows = session.scalars(
        select(ActivityEvent)
        .where(
            ActivityEvent.module == "refiner",
            ActivityEvent.event_type == "refiner.file_remux_pass_completed",
            func.instr(ActivityEvent.detail, relative_posix) > 0,
        )
        .order_by(ActivityEvent.id.desc())
        .limit(50),
    ).all()
    for row in rows:
        raw = (row.detail or "").strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(data, dict):
            continue
        if data.get("ok") is not True:
            continue
        if data.get("relative_media_path") != relative_posix:
            continue
        job_scope = data.get("media_scope", "movie")
        if not isinstance(job_scope, str) or job_scope not in ("movie", "tv"):
            job_scope = "movie"
        if job_scope != want_scope:
            continue
        output_file = data.get("output_file")
        if not isinstance(output_file, str) or not output_file.strip():
            continue
        try:
            if _existing_completed_output_path_is_safe(Path(output_file)):
                return True
        except OSError:
            continue
    if output_root is not None:
        expected = _expected_output_file_for_relative_path(output_root=Path(output_root), relative_posix=relative_posix)
        if expected is not None and _existing_completed_output_path_is_safe(expected):
            return True
    return False


def retry_completed_movie_source_cleanup(
    *,
    watched_root: Path,
    file_path: Path,
) -> tuple[bool, str | None]:
    """Retry deleting a completed Movies source release folder.

    This is intentionally conservative: it only removes the immediate parent
    folder for a candidate file under the watched root, and never removes the
    watched root itself.
    """

    try:
        root = watched_root.resolve()
        src = file_path.resolve()
        src.relative_to(root)
    except (OSError, ValueError) as exc:
        return False, f"Source cleanup retry skipped because the path was not safely under the watched folder ({exc})."

    movie_folder = src.parent
    if movie_folder == root:
        return False, "Source cleanup retry skipped because the file sits directly in the watched folder root."
    try:
        movie_folder.relative_to(root)
    except ValueError:
        return False, "Source cleanup retry skipped because the release folder is outside the watched folder."
    try:
        shutil.rmtree(movie_folder)
    except FileNotFoundError:
        return True, None
    except OSError as exc:
        locked = getattr(exc, "filename", None)
        if locked:
            return False, f"Source cleanup retry could not remove the release folder because this path is still locked: {locked}."
        return False, f"Source cleanup retry could not remove the release folder because it is still locked or blocked ({exc})."
    return True, None
