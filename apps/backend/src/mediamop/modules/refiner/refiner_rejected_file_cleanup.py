"""Narrow deletion primitive for files a library deliberately rejects."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class RejectedFileCleanupResult:
    deleted: bool
    detail: str


def cleanup_rejected_file(
    *,
    watched_root: Path,
    file_path: Path,
    action: str,
) -> RejectedFileCleanupResult:
    """Apply the saved rejection policy without ever deleting a populated folder."""

    if (action or "leave").strip().lower() != "delete_file":
        return RejectedFileCleanupResult(
            deleted=False,
            detail="MediaMop left the rejected file in place because this library's cleanup action is Leave in place.",
        )

    try:
        root = watched_root.expanduser().resolve(strict=True)
        source = file_path.expanduser().resolve(strict=True)
        source.relative_to(root)
    except (OSError, ValueError) as exc:
        return RejectedFileCleanupResult(
            deleted=False,
            detail=f"MediaMop did not delete the rejected file because it was not safely inside the watched folder ({exc}).",
        )
    if source == root or not source.is_file():
        return RejectedFileCleanupResult(
            deleted=False,
            detail="MediaMop did not delete the rejected path because it is not a regular file inside the watched folder.",
        )

    try:
        source.unlink()
    except OSError as exc:
        return RejectedFileCleanupResult(
            deleted=False,
            detail=f"MediaMop could not delete the rejected file because it is locked or unavailable ({exc}).",
        )

    parent = source.parent
    while parent != root:
        try:
            parent.rmdir()
        except OSError:
            break
        parent = parent.parent
    return RejectedFileCleanupResult(
        deleted=True,
        detail="MediaMop deleted the rejected file because this library's cleanup action is Delete rejected file.",
    )
