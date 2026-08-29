"""Carrying sidecars to the output before the source folder is deleted.

Refiner moved the video and nothing beside it, then ran ``rmtree`` on the release folder.
So a ``.srt`` or ``.nfo`` next to the source was **destroyed rather than migrated**, with
no setting that changed it (#344).

Two rules carry the safety here, and both have their own tests:

- A sidecar that is **not there** is not a failure. The common case is a release with
  none, and treating that as a problem would block source deletion on every file.
- A sidecar that **exists and could not be copied** blocks the deletion, because
  proceeding would destroy the only copy of a file MediaMop was asked to keep.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from mediamop.modules.refiner.refiner_sidecar_migration import (
    DEFAULT_SIDECAR_PATTERNS,
    apply_original_timestamps,
    destination_for_sidecar,
    find_sidecars,
    migrate_sidecars,
    parse_sidecar_patterns,
)


@pytest.fixture
def tree(tmp_path: Path) -> tuple[Path, Path]:
    """A release folder with a video, and an output folder with the renamed video."""

    source_folder = tmp_path / "watched" / "Film.2001.1080p.BluRay"
    source_folder.mkdir(parents=True)
    source = source_folder / "Film.2001.1080p.BluRay.mkv"
    source.write_bytes(b"video")

    output_folder = tmp_path / "out" / "Film (2001)"
    output_folder.mkdir(parents=True)
    output = output_folder / "Film (2001).mkv"
    output.write_bytes(b"video")
    return source, output


# --- the pattern list ----------------------------------------------------------------


def test_patterns_are_normalised_and_deduplicated() -> None:
    assert parse_sidecar_patterns("srt, .NFO ,srt, ") == (".srt", ".nfo")


def test_an_empty_list_migrates_nothing_which_is_the_old_behaviour() -> None:
    assert parse_sidecar_patterns("") == ()
    assert parse_sidecar_patterns(None) == ()


def test_the_offered_list_covers_what_travels_in_a_release_bundle() -> None:
    # The .idx/.sub pair matters: migrating one without the other leaves a broken pair.
    assert ".idx" in DEFAULT_SIDECAR_PATTERNS
    assert ".sub" in DEFAULT_SIDECAR_PATTERNS
    assert ".nfo" in DEFAULT_SIDECAR_PATTERNS


# --- finding ------------------------------------------------------------------------


def test_only_files_matching_the_video_stem_are_found(tree: tuple[Path, Path]) -> None:
    """A release folder holding two films must not hand one film's subtitles to the other."""

    source, _ = tree
    (source.parent / "Film.2001.1080p.BluRay.srt").write_text("mine")
    (source.parent / "Other.Film.srt").write_text("not mine")

    found = find_sidecars(source, (".srt",))

    assert [p.name for p in found] == ["Film.2001.1080p.BluRay.srt"]


def test_a_multi_part_suffix_is_matched(tree: tuple[Path, Path]) -> None:
    """``.en.srt`` is how subtitle files are actually named."""

    source, _ = tree
    (source.parent / "Film.2001.1080p.BluRay.en.srt").write_text("subs")

    assert [p.name for p in find_sidecars(source, (".srt",))] == ["Film.2001.1080p.BluRay.en.srt"]


def test_the_video_itself_is_never_a_sidecar(tree: tuple[Path, Path]) -> None:
    source, _ = tree

    assert find_sidecars(source, (".mkv",)) == []


def test_nothing_is_found_when_no_patterns_are_configured(tree: tuple[Path, Path]) -> None:
    source, _ = tree
    (source.parent / "Film.2001.1080p.BluRay.srt").write_text("subs")

    assert find_sidecars(source, ()) == []


def test_a_missing_folder_yields_nothing_rather_than_raising(tmp_path: Path) -> None:
    assert find_sidecars(tmp_path / "gone" / "film.mkv", (".srt",)) == []


# --- renaming ------------------------------------------------------------------------


def test_a_sidecar_is_renamed_to_the_output_stem(tree: tuple[Path, Path]) -> None:
    """Keeping the original name would leave a subtitle no player associates with the video."""

    source, output = tree
    sidecar = source.parent / "Film.2001.1080p.BluRay.en.srt"

    destination = destination_for_sidecar(sidecar=sidecar, source_media=source, output_media=output)

    assert destination.name == "Film (2001).en.srt"
    assert destination.parent == output.parent


# --- migrating -----------------------------------------------------------------------


def test_a_sidecar_is_migrated_and_renamed(tree: tuple[Path, Path]) -> None:
    source, output = tree
    (source.parent / "Film.2001.1080p.BluRay.srt").write_text("subs")

    result = migrate_sidecars(source_media=source, output_media=output, patterns=(".srt",))

    assert result.blocks_source_deletion is False
    assert [m.destination.name for m in result.migrated] == ["Film (2001).srt"]
    assert (output.parent / "Film (2001).srt").read_text() == "subs"
    # Copied, not moved: the deletion gate has its own conditions and may still refuse.
    assert (source.parent / "Film.2001.1080p.BluRay.srt").exists()


def test_a_release_with_no_sidecars_migrates_nothing_and_blocks_nothing(tree: tuple[Path, Path]) -> None:
    """The common case. Treating "nothing to migrate" as a failure would block every file."""

    source, output = tree

    result = migrate_sidecars(source_media=source, output_media=output, patterns=DEFAULT_SIDECAR_PATTERNS)

    assert result.migrated == []
    assert result.blocks_source_deletion is False


def test_an_empty_pattern_list_leaves_everything_exactly_as_before(tree: tuple[Path, Path]) -> None:
    source, output = tree
    (source.parent / "Film.2001.1080p.BluRay.srt").write_text("subs")

    result = migrate_sidecars(source_media=source, output_media=output, patterns=())

    assert result.migrated == []
    assert result.blocks_source_deletion is False
    assert not (output.parent / "Film (2001).srt").exists()


def test_an_existing_destination_is_left_alone_and_reported(tree: tuple[Path, Path]) -> None:
    """Overwriting could replace an edited subtitle with the release's original."""

    source, output = tree
    (source.parent / "Film.2001.1080p.BluRay.srt").write_text("release version")
    (output.parent / "Film (2001).srt").write_text("my edited version")

    result = migrate_sidecars(source_media=source, output_media=output, patterns=(".srt",))

    assert result.migrated == []
    assert any("already in the output folder" in s for s in result.skipped)
    assert (output.parent / "Film (2001).srt").read_text() == "my edited version"
    # Not a failure: nothing was lost, so the deletion may still proceed.
    assert result.blocks_source_deletion is False


def test_a_failed_copy_blocks_the_source_deletion_and_says_why(tree: tuple[Path, Path]) -> None:
    """The rule that makes this safe rather than merely useful.

    A destination whose parent is a *file* cannot be created on any platform, which
    produces a real copy failure without needing permission games.
    """

    source, output = tree
    (source.parent / "Film.2001.1080p.BluRay.srt").write_text("subs")
    blocker = output.parent / "Film (2001).srt"
    blocker.parent.mkdir(parents=True, exist_ok=True)
    # Make the destination path unusable: a directory where the file must go.
    blocker.mkdir()

    result = migrate_sidecars(source_media=source, output_media=output, patterns=(".srt",))

    assert result.blocks_source_deletion is True
    assert result.migrated == []
    assert "did not remove the source folder" in result.blocking_reason
    assert "nothing is lost" in result.blocking_reason


def test_a_directory_in_the_way_is_a_failure_not_an_already_migrated_sidecar(tree: tuple[Path, Path]) -> None:
    """Reading it as "already there" would clear the way for the source to be deleted
    while the sidecar never arrived."""

    source, output = tree
    (source.parent / "Film.2001.1080p.BluRay.srt").write_text("subs")
    (output.parent / "Film (2001).srt").mkdir(parents=True)

    result = migrate_sidecars(source_media=source, output_media=output, patterns=(".srt",))

    assert result.skipped == []
    assert result.blocks_source_deletion is True


def test_several_sidecars_travel_together(tree: tuple[Path, Path]) -> None:
    """An .idx without its .sub is a broken pair."""

    source, output = tree
    for suffix in (".idx", ".sub", ".nfo"):
        (source.parent / f"Film.2001.1080p.BluRay{suffix}").write_text(suffix)

    result = migrate_sidecars(source_media=source, output_media=output, patterns=DEFAULT_SIDECAR_PATTERNS)

    assert sorted(m.destination.suffix for m in result.migrated) == [".idx", ".nfo", ".sub"]


# --- timestamps ----------------------------------------------------------------------


def test_original_timestamps_can_be_applied_to_the_output(tree: tuple[Path, Path]) -> None:
    source, output = tree
    old = 1_000_000_000
    os.utime(source, (old, old))

    problem = apply_original_timestamps(source_media=source, output_media=output)

    assert problem is None
    assert int(output.stat().st_mtime) == old


def test_a_timestamp_problem_is_reported_rather_than_raised(tmp_path: Path) -> None:
    """Refusing a finished remux over a timestamp would be the wrong trade."""

    problem = apply_original_timestamps(source_media=tmp_path / "gone.mkv", output_media=tmp_path / "also-gone.mkv")

    assert problem is not None
    assert "timestamps" in problem


def test_preserving_timestamps_carries_them_onto_a_migrated_sidecar(tree: tuple[Path, Path]) -> None:
    source, output = tree
    sidecar = source.parent / "Film.2001.1080p.BluRay.srt"
    sidecar.write_text("subs")
    old = 1_000_000_000
    os.utime(sidecar, (old, old))

    result = migrate_sidecars(source_media=source, output_media=output, patterns=(".srt",), preserve_timestamps=True)

    assert len(result.migrated) == 1
    assert int(result.migrated[0].destination.stat().st_mtime) == old
