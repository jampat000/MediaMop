"""Translate a manager's absolute file path into a Refiner watched-folder-relative one.

A media manager knows where the file is on disk. Refiner works in paths relative to its
own watched folder, and refuses anything with ``..`` in it. Both machines have to agree
on the folder for a hand-off to mean anything, so a path outside it is a configuration
mistake worth naming plainly rather than a job worth enqueuing.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePath


@dataclass(frozen=True, slots=True)
class HandoffPathResult:
    """Either a relative path Refiner can use, or the reason it cannot be produced."""

    relative_media_path: str | None
    problem: str | None

    @property
    def ok(self) -> bool:
        return self.relative_media_path is not None


def _comparable(part: str) -> str:
    # Windows and SMB paths are case-insensitive, and a manager on another host may
    # spell the same share with different case or separators than MediaMop stores.
    return part.replace("\\", "/").strip().rstrip("/").lower()


def relative_media_path_for_handoff(*, watched_folder: str | None, file_path: str) -> HandoffPathResult:
    """Resolve ``file_path`` against ``watched_folder`` without touching the filesystem.

    Kept purely textual so it behaves the same on the API host as on the worker, and so
    a hand-off naming a path that is not mounted yet fails with a clear message rather
    than a stat error.
    """

    folder = (watched_folder or "").strip()
    if not folder:
        return HandoffPathResult(
            None,
            "Refiner's watched folder is not set for this media scope, so there is nowhere to resolve the hand-off against.",
        )

    target = (file_path or "").strip()
    if not target:
        return HandoffPathResult(None, "The hand-off did not name a file path.")

    folder_parts = [p for p in _comparable(folder).split("/") if p]
    target_parts_cmp = [p for p in _comparable(target).split("/") if p]
    # Keep the original spelling for the value handed to Refiner; only compare folded.
    target_parts_raw = [p for p in target.replace("\\", "/").strip().split("/") if p]

    if len(target_parts_cmp) <= len(folder_parts):
        return HandoffPathResult(None, _outside_message(folder, target))
    if target_parts_cmp[: len(folder_parts)] != folder_parts:
        return HandoffPathResult(None, _outside_message(folder, target))

    relative = PurePath(*target_parts_raw[len(folder_parts) :]).as_posix()
    if not relative or ".." in relative.split("/"):
        return HandoffPathResult(None, _outside_message(folder, target))
    return HandoffPathResult(relative, None)


def _outside_message(folder: str, target: str) -> str:
    return (
        f"The hand-off names {target!r}, which is not inside Refiner's watched folder {folder!r}. "
        "Point the media manager and Refiner at the same folder — both hosts have to see it at that path."
    )
