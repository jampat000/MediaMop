"""Carry sidecar files to the output before the source folder is deleted.

Refiner mirrored the watched-relative path under the output root and moved the video.
Nothing beside it came across — no ``.srt``, no ``.nfo``, no artwork, no ``.idx``/``.sub``
pair. Then Movies cleanup ran ``rmtree`` on the whole release folder, and TV did the same
to a season folder. So sidecars next to the source were **destroyed rather than migrated**,
and there was no setting that changed it.

Two rules make this safe rather than merely useful:

**A sidecar that is not there is not a failure.** The common case is a release with no
sidecars at all, and treating "nothing to migrate" as a problem would block source
deletion on every file and quietly fill the watched folder.

**A sidecar that exists and could not be copied blocks the deletion.** That is the whole
point of doing this before the cleanup gate: the alternative is deleting the only copy of
a file MediaMop was asked to keep.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from mediamop.platform.file_lifecycle.mutations import FileLifecycleError, safe_copy_to_final

#: Offered as the starting list. Chosen for what actually travels in a release bundle:
#: subtitle formats including the ``.idx``/``.sub`` pair, the metadata file, and artwork.
DEFAULT_SIDECAR_PATTERNS: tuple[str, ...] = (
    ".srt",
    ".ass",
    ".ssa",
    ".sub",
    ".idx",
    ".vtt",
    ".nfo",
    ".jpg",
    ".png",
)


def parse_sidecar_patterns(csv: str | None) -> tuple[str, ...]:
    """Normalise a stored pattern list. Empty means "migrate nothing", which is the
    behaviour every install has today."""

    out: list[str] = []
    for raw in (csv or "").split(","):
        text = raw.strip().lower()
        if not text:
            continue
        if not text.startswith("."):
            text = f".{text}"
        if text not in out:
            out.append(text)
    return tuple(out)


@dataclass(frozen=True, slots=True)
class MigratedSidecar:
    source: Path
    destination: Path


@dataclass(slots=True)
class SidecarMigrationResult:
    """What travelled, what did not, and whether deletion may proceed."""

    migrated: list[MigratedSidecar] = field(default_factory=list)
    #: Sidecars that exist and could not be copied. Non-empty means the source folder
    #: must not be deleted.
    failures: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)

    @property
    def blocks_source_deletion(self) -> bool:
        return bool(self.failures)

    @property
    def blocking_reason(self) -> str:
        if not self.failures:
            return ""
        return (
            "MediaMop did not remove the source folder because it could not copy "
            f"{len(self.failures)} file(s) that were set to travel with the video: "
            f"{'; '.join(self.failures)}. The source is left in place so nothing is lost."
        )


def find_sidecars(source_media: Path, patterns: tuple[str, ...]) -> list[Path]:
    """Files beside the video that match the configured patterns.

    Matched against the video's own stem, so a release folder holding two films does not
    hand one film's subtitles to the other. A multi-part suffix like ``.en.srt`` is
    matched too, because that is how subtitle files are actually named.
    """

    if not patterns:
        return []
    folder = source_media.parent
    stem = source_media.stem.lower()
    found: list[Path] = []
    try:
        entries = sorted(folder.iterdir(), key=lambda p: p.name.lower())
    except OSError:
        return []
    for entry in entries:
        if not entry.is_file() or entry == source_media:
            continue
        name = entry.name.lower()
        if not name.startswith(stem):
            continue
        if not any(name.endswith(pattern) for pattern in patterns):
            continue
        found.append(entry)
    return found


def destination_for_sidecar(*, sidecar: Path, source_media: Path, output_media: Path) -> Path:
    """The sidecar's new name, rewritten to the output video's stem.

    ``Film.2001.1080p.en.srt`` beside ``Film.2001.1080p.mkv`` becomes ``<output stem>.en.srt``,
    so the pair still matches after a rename. Keeping the original name would leave a
    subtitle no player would associate with the video.
    """

    trailing = sidecar.name[len(source_media.stem) :]
    return output_media.parent / f"{output_media.stem}{trailing}"


def migrate_sidecars(
    *,
    source_media: Path,
    output_media: Path,
    patterns: tuple[str, ...],
    preserve_timestamps: bool = False,
) -> SidecarMigrationResult:
    """Copy configured sidecars beside the output, renamed to its stem.

    Copy rather than move: the source folder is deleted by a later gate that has its own
    conditions, and a moved sidecar whose deletion is then refused would have been taken
    out of a folder the operator still has.
    """

    result = SidecarMigrationResult()
    if not patterns:
        return result

    for sidecar in find_sidecars(source_media, patterns):
        destination = destination_for_sidecar(sidecar=sidecar, source_media=source_media, output_media=output_media)
        if destination.is_file():
            # Already there from an earlier pass. Overwriting could replace an edited
            # subtitle with the release's original, so it is left alone and reported.
            result.skipped.append(f"{destination.name} was already in the output folder, so it was not replaced.")
            continue
        if destination.exists():
            # Something that is not a file is in the way — a directory with that name,
            # most likely. That is not "already migrated", and treating it as such would
            # clear the way for the source to be deleted while the sidecar never arrived.
            result.failures.append(f"{sidecar.name} (something else already exists at {destination})")
            continue
        try:
            safe_copy_to_final(
                source=sidecar,
                final=destination,
                preserve_metadata=preserve_timestamps,
            )
        except (FileLifecycleError, OSError) as exc:
            result.failures.append(f"{sidecar.name} ({exc})")
            continue
        result.migrated.append(MigratedSidecar(source=sidecar, destination=destination))
    return result


def apply_original_timestamps(*, source_media: Path, output_media: Path) -> str | None:
    """Give the output the source's modification time. Returns a problem, or None.

    Never fatal: the output is correct either way, and refusing a finished remux over a
    timestamp would be the wrong trade.
    """

    try:
        stat = source_media.stat()
    except OSError as exc:
        return f"MediaMop could not read the original file's timestamps ({exc})."
    try:
        import os

        os.utime(output_media, (stat.st_atime, stat.st_mtime))
    except OSError as exc:
        return f"MediaMop could not apply the original timestamps to the output ({exc})."
    return None
