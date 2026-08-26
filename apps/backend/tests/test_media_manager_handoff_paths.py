"""Absolute hand-off path -> Refiner watched-folder-relative path.

Two hosts rarely spell the same folder identically, so the comparison folds case and
separators. Anything that lands outside the watched folder is a configuration mistake,
not a job.
"""

from __future__ import annotations

import pytest

from mediamop.platform.media_managers import relative_media_path_for_handoff


@pytest.mark.parametrize(
    ("watched", "file_path", "expected"),
    [
        ("/srv/handoff", "/srv/handoff/Film/film.mkv", "Film/film.mkv"),
        ("/srv/handoff/", "/srv/handoff/film.mkv", "film.mkv"),
        ("D:\\Handoff", "D:\\Handoff\\Film\\film.mkv", "Film/film.mkv"),
        ("D:/Handoff", "D:\\Handoff\\Film\\film.mkv", "Film/film.mkv"),
        # Case folds: the manager may report a different case than MediaMop stored.
        ("D:\\handoff", "D:\\HANDOFF\\Film\\film.mkv", "Film/film.mkv"),
        # A UNC share both hosts mount.
        (r"\\storage-city\Data\Media\Handoff", r"\\storage-city\data\media\handoff\a\b.mkv", "a/b.mkv"),
        # Deep nesting is preserved verbatim.
        ("/w", "/w/a/b/c/d.mkv", "a/b/c/d.mkv"),
    ],
)
def test_paths_inside_the_watched_folder_resolve(watched: str, file_path: str, expected: str) -> None:
    result = relative_media_path_for_handoff(watched_folder=watched, file_path=file_path)
    assert result.ok
    assert result.relative_media_path == expected
    assert result.problem is None


def test_original_case_is_preserved_in_the_relative_path() -> None:
    """Comparison folds case; the value handed to Refiner must not."""
    result = relative_media_path_for_handoff(
        watched_folder="/srv/handoff",
        file_path="/SRV/HANDOFF/Blade.Runner.2049/Film.MKV",
    )
    assert result.relative_media_path == "Blade.Runner.2049/Film.MKV"


@pytest.mark.parametrize(
    ("watched", "file_path"),
    [
        ("/srv/handoff", "/somewhere/else/film.mkv"),
        # A sibling that merely shares a prefix string must not match.
        ("/srv/handoff", "/srv/handoff-other/film.mkv"),
        # The folder itself is not a file within it.
        ("/srv/handoff", "/srv/handoff"),
        ("/srv/handoff", "/srv"),
    ],
)
def test_paths_outside_the_watched_folder_are_refused(watched: str, file_path: str) -> None:
    result = relative_media_path_for_handoff(watched_folder=watched, file_path=file_path)
    assert not result.ok
    assert result.problem is not None
    assert "watched folder" in result.problem


def test_missing_watched_folder_is_named_as_the_problem() -> None:
    for empty in (None, "", "   "):
        result = relative_media_path_for_handoff(watched_folder=empty, file_path="/a/b.mkv")
        assert not result.ok
        assert "watched folder is not set" in (result.problem or "")


def test_missing_file_path_is_named_as_the_problem() -> None:
    result = relative_media_path_for_handoff(watched_folder="/srv/handoff", file_path="  ")
    assert not result.ok
    assert "did not name a file path" in (result.problem or "")


def test_parent_traversal_cannot_escape_the_watched_folder() -> None:
    """Refiner refuses ``..`` segments, so they must never reach it."""
    result = relative_media_path_for_handoff(
        watched_folder="/srv/handoff",
        file_path="/srv/handoff/../../etc/passwd",
    )
    assert not result.ok
