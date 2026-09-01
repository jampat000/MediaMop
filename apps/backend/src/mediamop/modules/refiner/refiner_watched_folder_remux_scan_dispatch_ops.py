"""Filesystem scan helpers and duplicate guards for watched-folder remux scan dispatch."""

from __future__ import annotations

import json
import re
import shutil
import time
from collections.abc import Collection
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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


def is_transient_download_artifact_media_path(
    path: Path,
    *,
    exclude_markers: Collection[str] | None = None,
) -> bool:
    """True for media-shaped files that are still downloader staging artifacts."""

    stem = path.stem.strip()
    if _HASH_ARTIFACT_STEM_RE.fullmatch(stem):
        return True

    parts = {part.strip().lower() for part in path.parts}
    markers = (
        {part.strip().lower() for part in exclude_markers if part.strip()}
        if exclude_markers is not None
        else _TRANSIENT_DOWNLOAD_DIR_MARKERS
    )
    return bool(parts.intersection(markers))


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
    media_extensions: Collection[str] | None = None,
    exclude_markers: Collection[str] | None = None,
    exclude_hidden: bool = False,
    top_level_only: bool = False,
) -> WatchedFolderScanCandidates:
    """Candidate files under ``watched_root``, plus a count of what the allowlist rejected."""

    root = watched_root.resolve()
    now = time.time()
    min_age = max(0, int(min_file_age_seconds))
    found: list[Path] = []
    rejected = 0
    rejected_suffixes: set[str] = set()
    configured_extensions = (
        {
            value.strip().lower() if value.strip().startswith(".") else f".{value.strip().lower()}"
            for value in media_extensions
            if value.strip()
        }
        if media_extensions is not None
        else None
    )
    paths = root.glob("*") if top_level_only else root.rglob("*")
    for p in sorted(paths):
        if not p.is_file():
            continue
        try:
            relative = p.resolve().relative_to(root)
        except ValueError:
            continue
        if exclude_hidden and any(part.startswith(".") for part in relative.parts):
            continue
        if is_transient_download_artifact_media_path(p, exclude_markers=exclude_markers):
            # A part-file is not an unsupported type; it is the same file mid-copy.
            continue
        accepted_extension = (
            p.suffix.lower() in configured_extensions
            if configured_extensions is not None and configured_extensions
            else is_refiner_media_candidate(p)
        )
        if not accepted_extension:
            suffix = p.suffix.lower()
            # Only count things that look like an attempt at media. Counting every
            # .nfo and .srt beside a film would bury the signal this exists to give.
            if suffix and suffix not in _NON_MEDIA_COMPANION_SUFFIXES:
                rejected += 1
                rejected_suffixes.add(suffix)
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
    library_id: int | None = None,
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
        job_library_id = data.get("library_id")
        job_scope = data.get("media_scope", "movie")
        if not isinstance(job_scope, str) or job_scope not in ("movie", "tv"):
            job_scope = "movie"
        same_library = library_id is None or job_library_id == library_id
        if isinstance(rel, str) and rel.strip() == relative_posix and job_scope == want_scope and same_library:
            return True
    return False


def refiner_completed_remux_output_exists_for_relative_path(
    session: Session,
    *,
    relative_posix: str,
    media_scope: str = "movie",
    library_id: int | None = None,
    output_root: Path | str | None = None,
    source_path: Path | None = None,
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
        if data.get("ok") is not True or data.get("source_deleted_after_success") is not False:
            continue
        if data.get("relative_media_path") != relative_posix:
            continue
        event_library_id = data.get("library_id")
        if library_id is not None and event_library_id is not None and event_library_id != library_id:
            continue
        job_scope = data.get("media_scope", "movie")
        if not isinstance(job_scope, str) or job_scope not in ("movie", "tv"):
            job_scope = "movie"
        if job_scope != want_scope:
            continue
        if source_path is not None and not _completed_event_matches_current_source(data=data, source_path=source_path):
            continue
        output_file = data.get("output_file")
        if not isinstance(output_file, str) or not output_file.strip():
            continue
        try:
            if _existing_completed_output_path_is_safe(Path(output_file)):
                return True
        except OSError:
            continue
    # An output file by itself is enough to prevent an accidental duplicate remux, but
    # it is not enough evidence to delete a source that may have been replaced since the
    # history row expired. Cleanup callers provide ``source_path`` and therefore require
    # a matching completion record above.
    if output_root is not None and source_path is None:
        expected = _expected_output_file_for_relative_path(output_root=Path(output_root), relative_posix=relative_posix)
        if expected is not None and _existing_completed_output_path_is_safe(expected):
            return True
    return False


def _completed_event_matches_current_source(*, data: dict[str, Any], source_path: Path) -> bool:
    """Require the completed event to describe the source that is still on disk."""

    try:
        current = source_path.resolve()
        stat = current.stat()
    except OSError:
        return False

    fingerprint = data.get("source_fingerprint")
    if isinstance(fingerprint, dict):
        expected = (
            fingerprint.get("device"),
            fingerprint.get("inode"),
            fingerprint.get("size_bytes"),
            fingerprint.get("modified_time_ns"),
        )
        actual = (int(stat.st_dev), int(stat.st_ino), int(stat.st_size), int(stat.st_mtime_ns))
        return expected == actual

    # Private builds before source fingerprints were persisted still recorded the
    # resolved source path and byte count. This safely repairs their lock-delayed
    # cleanup without treating an unrelated output file as deletion authority.
    inspected = data.get("inspected_source_path")
    recorded_size = data.get("source_size_bytes")
    if not isinstance(inspected, str) or isinstance(recorded_size, bool) or not isinstance(recorded_size, int):
        return False
    try:
        same_path = Path(inspected).resolve() == current
    except OSError:
        return False
    return same_path and recorded_size == int(stat.st_size)


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
