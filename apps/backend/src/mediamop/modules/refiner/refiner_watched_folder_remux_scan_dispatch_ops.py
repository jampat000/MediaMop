"""Filesystem scan helpers and duplicate guards for watched-folder remux scan dispatch."""

from __future__ import annotations

import json
import re
import shutil
import time
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from mediamop.modules.refiner.file_remux_pass.job_kinds import REFINER_FILE_REMUX_PASS_JOB_KIND
from mediamop.modules.refiner.jobs_model import RefinerJob, RefinerJobStatus
from mediamop.modules.refiner.refiner_remux_rules import is_refiner_media_candidate
from mediamop.platform.activity.models import ActivityEvent

# Files that legitimately sit beside media and are not a failed attempt at it. Counting
# these as "unsupported type" would bury the signal in subtitles and artwork.
_NON_MEDIA_COMPANION_SUFFIXES: frozenset[str] = frozenset(
    {
        ".srt",
        ".sub",
        ".idx",
        ".ass",
        ".ssa",
        ".vtt",
        ".sup",
        ".nfo",
        ".txt",
        ".md",
        ".log",
        ".xml",
        ".json",
        ".yml",
        ".yaml",
        ".jpg",
        ".jpeg",
        ".png",
        ".gif",
        ".webp",
        ".tbn",
        ".bmp",
        ".par2",
        ".sfv",
        ".nzb",
        ".torrent",
        ".url",
        ".db",
        ".ini",
        ".bak",
        ".mp3",
        ".flac",
        ".m4a",
        ".aac",
        ".ac3",
        ".dts",
        ".ogg",
        ".wav",
        # In-progress downloads. The same file is admitted under its real name once the
        # client renames it, so reporting it as an unsupported type would put a message
        # on screen for every active download.
        ".part",
        ".partial",
        ".crdownload",
        ".downloading",
        ".tmp",
        ".!ut",
        ".!qb",
    }
)

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


@dataclass(frozen=True, slots=True)
class WatchedFolderScanCandidates:
    """What a watched-folder walk found, and what it decided not to look at.

    ``ignored_unsupported_type`` is the point of this type. Extension mismatch used to be
    the one admission decision that produced no counter, no reason and no activity row —
    a ``.mov`` in a watched folder simply never appeared, and nothing said why (#348).
    Every other guardrail alongside it reports itself.
    """

    files: list[Path]
    ignored_unsupported_type: int = 0
    ignored_unsupported_extensions: tuple[str, ...] = ()


def iter_watched_folder_media_candidates(
    watched_root: Path,
    *,
    min_file_age_seconds: int = 0,
) -> WatchedFolderScanCandidates:
    """Candidate files under ``watched_root``, plus a count of what the allowlist rejected."""

    root = watched_root.resolve()
    now = time.time()
    min_age = max(0, int(min_file_age_seconds))
    found: list[Path] = []
    rejected = 0
    rejected_suffixes: set[str] = set()
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        if is_transient_download_artifact_media_path(p):
            # A part-file is not an unsupported type; it is the same file mid-copy.
            continue
        if not is_refiner_media_candidate(p):
            suffix = p.suffix.lower()
            # Only count things that look like an attempt at media. Counting every
            # .nfo and .srt beside a film would bury the signal this exists to give.
            if suffix and suffix not in _NON_MEDIA_COMPANION_SUFFIXES:
                rejected += 1
                rejected_suffixes.add(suffix)
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
    return WatchedFolderScanCandidates(
        files=found,
        ignored_unsupported_type=rejected,
        ignored_unsupported_extensions=tuple(sorted(rejected_suffixes)),
    )


def iter_watched_folder_media_candidate_files(watched_root: Path, *, min_file_age_seconds: int = 0) -> list[Path]:
    """Files only. Kept for callers that do not report on what was skipped."""

    return iter_watched_folder_media_candidates(watched_root, min_file_age_seconds=min_file_age_seconds).files


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
            return (
                False,
                f"Source cleanup retry could not remove the release folder because this path is still locked: {locked}.",
            )
        return (
            False,
            f"Source cleanup retry could not remove the release folder because it is still locked or blocked ({exc}).",
        )
    return True, None
