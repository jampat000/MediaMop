"""The gate in front of a delete: does any manager still keep a library file in here?

Cleanup used to ask exactly one product, over HTTP it built itself, and treated
"could not ask" as a skip. The skip was right; the single product was not. This asks
every manager that looks after the scope and keeps the same rule, stated once:

**Only a manager that actually answered can clear a folder.** Unreachable is not a
clearance, and "this kind of manager cannot tell you" is not one either. A folder is
removed when every manager that looks after the scope answered, and none of them
reported a library file inside it.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from mediamop.platform.media_managers.manager_port import ManagerLibraryTruth

TruthCheck = Literal["passed", "failed", "skipped"]

_SCOPE_WORDS: dict[str, str] = {"movie": "Movies", "tv": "TV episodes"}


@dataclass(frozen=True, slots=True)
class LibraryTruthVerdict:
    """Whether a folder is clear of every manager's library, and why."""

    check: TruthCheck
    note: str
    matched_paths: tuple[str, ...] = ()

    @property
    def clears_delete(self) -> bool:
        return self.check == "passed"


def _paths_inside(raw_paths: Sequence[str], folder: Path) -> list[str]:
    folder_resolved = folder.resolve()
    inside: list[str] = []
    for raw in raw_paths:
        try:
            resolved = Path(raw).expanduser().resolve()
        except OSError:
            continue
        try:
            resolved.relative_to(folder_resolved)
        except ValueError:
            continue
        inside.append(str(resolved))
    return inside


def _sample(paths: Sequence[str]) -> str:
    shown = "; ".join(paths[:3])
    return f"{shown} (+{len(paths) - 3} more)" if len(paths) > 3 else shown


def evaluate_library_truth_for_folder(
    answers: Sequence[ManagerLibraryTruth],
    *,
    folder: Path,
    media_scope: str,
) -> LibraryTruthVerdict:
    """Decide whether ``folder`` is clear of every manager's kept library files."""

    scope_word = _SCOPE_WORDS.get(media_scope, "Movies")
    if not answers:
        return LibraryTruthVerdict(
            check="skipped",
            note=(
                f"No media manager is connected for {scope_word}, so MediaMop could not check whether this "
                "folder still holds library files. It was left in place."
            ),
        )

    silent = [answer for answer in answers if not answer.is_reported]
    if silent:
        names = ", ".join(answer.connection.label for answer in silent)
        first_detail = next((answer.detail for answer in silent if answer.detail), None)
        note = (
            f"MediaMop could not confirm with {names} whether this folder still holds library files, "
            "so it was left in place."
        )
        if first_detail:
            note = f"{note} {first_detail}"
        return LibraryTruthVerdict(check="skipped", note=note)

    hits: list[str] = []
    holders: list[str] = []
    for answer in answers:
        inside = _paths_inside(answer.library_file_paths, folder)
        if inside:
            holders.append(answer.connection.label)
            hits.extend(inside)
    if hits:
        return LibraryTruthVerdict(
            check="failed",
            note=(
                f"{', '.join(holders)} still keeps at least one library file inside this folder, so MediaMop "
                f"treats it as the kept library location and will not delete it. Example path(s): {_sample(hits)}"
            ),
            matched_paths=tuple(hits),
        )

    names = ", ".join(answer.connection.label for answer in answers)
    return LibraryTruthVerdict(
        check="passed",
        note=(
            f"{names} reported no library files inside this folder, so MediaMop treated it as safe to remove "
            "under the other gates."
        ),
    )
