"""What to do when an output already exists at the path Refiner is about to write.

There was exactly one behaviour: overwrite. The activity note even called it the
"default Refiner output collision policy", implying there were others. There were not.

The reason this matters more than it sounds is that a collision is **silent**. Re-running
a library overwrites good outputs with fresh ones, which is usually harmless. Two sources
normalising to one output path — a repack alongside the original, or the same title in two
release folders — means the second file destroys the first output, and the only trace was
a note in an activity row that may already have aged out.

``replace`` stays the default, so an upgrade changes nothing. Every other policy exists
because somebody's library has a shape where overwriting is wrong, and none of them can be
guessed from the file.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

CollisionPolicy = Literal["replace", "skip", "keep_both", "replace_if_larger", "replace_if_newer"]

COLLISION_POLICIES: tuple[str, ...] = ("replace", "skip", "keep_both", "replace_if_larger", "replace_if_newer")

#: The behaviour every install has today.
DEFAULT_COLLISION_POLICY: CollisionPolicy = "replace"


def normalize_collision_policy(raw: str | None) -> CollisionPolicy:
    """Canonical policy name. Anything unrecognised is the current behaviour.

    Falling back to ``replace`` rather than to the most cautious option is deliberate: an
    unreadable setting should behave the way the system always has, not silently start
    declining to write outputs.
    """

    value = (raw or "").strip().lower()
    return value if value in COLLISION_POLICIES else DEFAULT_COLLISION_POLICY  # type: ignore[return-value]


@dataclass(frozen=True, slots=True)
class CollisionDecision:
    """What to do, where to write, and the sentence explaining it."""

    policy: CollisionPolicy
    #: ``write`` proceeds to ``destination``; ``skip`` leaves the existing output alone.
    action: Literal["write", "skip"]
    destination: Path
    replaced_existing: bool
    reason: str

    @property
    def wrote(self) -> bool:
        return self.action == "write"


def _next_free_path(final: Path, *, limit: int = 999) -> Path:
    """``Film (2001).mkv`` → ``Film (2001) (2).mkv``, then ``(3)``, and so on.

    Deterministic and bounded. An unbounded search would spin forever on a directory
    MediaMop cannot read, and a random suffix would produce a different name every run
    for the same collision.
    """

    for attempt in range(2, limit + 1):
        candidate = final.with_name(f"{final.stem} ({attempt}){final.suffix}")
        if not candidate.exists():
            return candidate
    return final.with_name(f"{final.stem} ({limit}){final.suffix}")


def decide_output_collision(
    *,
    final: Path,
    source: Path | None = None,
    staged: Path | None = None,
    policy: str | None = None,
) -> CollisionDecision:
    """Apply the library's policy to a path that already exists.

    ``staged`` is the finished file waiting to be moved into place, used by
    ``replace_if_larger``; ``source`` is the original, used by ``replace_if_newer``. When
    the comparison cannot be made — an unreadable file, a missing staged path — the
    policies fall back to **not replacing**, because the whole point of choosing them is
    to protect the existing output, and a failed check is not evidence that replacing is
    safe.
    """

    chosen = normalize_collision_policy(policy)

    if not final.exists():
        return CollisionDecision(
            policy=chosen,
            action="write",
            destination=final,
            replaced_existing=False,
            reason="No file existed at the output path, so MediaMop wrote it there.",
        )

    if chosen == "skip":
        return CollisionDecision(
            policy=chosen,
            action="skip",
            destination=final,
            replaced_existing=False,
            reason=(
                f"An output already exists at {final.name} and this library is set to leave existing outputs "
                "alone, so MediaMop kept the one that was already there."
            ),
        )

    if chosen == "keep_both":
        destination = _next_free_path(final)
        return CollisionDecision(
            policy=chosen,
            action="write",
            destination=destination,
            replaced_existing=False,
            reason=(
                f"An output already exists at {final.name}, so MediaMop wrote this one alongside it as "
                f"{destination.name}."
            ),
        )

    if chosen == "replace_if_larger":
        existing_size = _size_of(final)
        new_size = _size_of(staged) if staged is not None else None
        if existing_size is None or new_size is None:
            return CollisionDecision(
                policy=chosen,
                action="skip",
                destination=final,
                replaced_existing=False,
                reason=(
                    f"MediaMop could not compare the new output with the existing {final.name}, so it kept the "
                    "existing one rather than replacing a file it could not measure."
                ),
            )
        if new_size > existing_size:
            return CollisionDecision(
                policy=chosen,
                action="write",
                destination=final,
                replaced_existing=True,
                reason=(
                    f"The new output is larger than the existing {final.name} "
                    f"({new_size} bytes against {existing_size}), so MediaMop replaced it."
                ),
            )
        return CollisionDecision(
            policy=chosen,
            action="skip",
            destination=final,
            replaced_existing=False,
            reason=(
                f"The new output is not larger than the existing {final.name} "
                f"({new_size} bytes against {existing_size}), so MediaMop kept the existing one."
            ),
        )

    if chosen == "replace_if_newer":
        existing_mtime = _mtime_of(final)
        source_mtime = _mtime_of(source) if source is not None else None
        if existing_mtime is None or source_mtime is None:
            return CollisionDecision(
                policy=chosen,
                action="skip",
                destination=final,
                replaced_existing=False,
                reason=(
                    f"MediaMop could not compare timestamps with the existing {final.name}, so it kept the "
                    "existing one rather than replacing a file it could not date."
                ),
            )
        if source_mtime > existing_mtime:
            return CollisionDecision(
                policy=chosen,
                action="write",
                destination=final,
                replaced_existing=True,
                reason=(f"The source is newer than the existing output at {final.name}, so MediaMop replaced it."),
            )
        return CollisionDecision(
            policy=chosen,
            action="skip",
            destination=final,
            replaced_existing=False,
            reason=(
                f"The source is not newer than the existing output at {final.name}, so MediaMop kept the existing one."
            ),
        )

    return CollisionDecision(
        policy="replace",
        action="write",
        destination=final,
        replaced_existing=True,
        reason=f"An existing output at {final.name} was replaced, which is this library's collision policy.",
    )


def _size_of(path: Path) -> int | None:
    try:
        return int(path.stat().st_size)
    except OSError:
        return None


def _mtime_of(path: Path) -> float | None:
    try:
        return float(path.stat().st_mtime)
    except OSError:
        return None
