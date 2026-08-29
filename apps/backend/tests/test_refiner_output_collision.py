"""What happens when an output already exists where Refiner is about to write.

There was exactly one behaviour — overwrite — and it was **silent**. Two sources
normalising to one output path, a repack alongside the original, the same title in two
release folders: the second destroyed the first output, and the only trace was a note in
an activity row that may already have aged out (#349).

``replace`` stays the default, and there is a test asserting that, because an upgrade
must not start declining to write outputs.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from mediamop.modules.refiner.refiner_output_collision import (
    COLLISION_POLICIES,
    DEFAULT_COLLISION_POLICY,
    decide_output_collision,
    normalize_collision_policy,
)


@pytest.fixture
def paths(tmp_path: Path) -> tuple[Path, Path, Path]:
    """``(source, staged, final)`` with the final already occupied."""

    source = tmp_path / "src" / "Film.mkv"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"s" * 100)

    staged = tmp_path / "work" / "Film.staged.mkv"
    staged.parent.mkdir(parents=True)
    staged.write_bytes(b"n" * 200)

    final = tmp_path / "out" / "Film (2001).mkv"
    final.parent.mkdir(parents=True)
    final.write_bytes(b"o" * 150)
    return source, staged, final


# --- the default ---------------------------------------------------------------------


def test_replace_is_the_default_and_every_policy_is_known() -> None:
    assert DEFAULT_COLLISION_POLICY == "replace"
    assert set(COLLISION_POLICIES) == {
        "replace",
        "skip",
        "keep_both",
        "replace_if_larger",
        "replace_if_newer",
    }


def test_an_unreadable_setting_behaves_the_way_the_system_always_has() -> None:
    """Not the most cautious option: an unreadable value must not silently start
    declining to write outputs."""

    assert normalize_collision_policy(None) == "replace"
    assert normalize_collision_policy("") == "replace"
    assert normalize_collision_policy("something-invented") == "replace"


def test_no_existing_file_is_never_a_collision(tmp_path: Path) -> None:
    final = tmp_path / "out" / "Film.mkv"

    decision = decide_output_collision(final=final, policy="skip")

    assert decision.wrote is True
    assert decision.replaced_existing is False
    assert decision.destination == final


# --- each policy ---------------------------------------------------------------------


def test_replace_overwrites_and_says_so(paths: tuple[Path, Path, Path]) -> None:
    source, staged, final = paths

    decision = decide_output_collision(final=final, source=source, staged=staged, policy="replace")

    assert decision.wrote is True
    assert decision.replaced_existing is True
    assert decision.destination == final
    assert "was replaced" in decision.reason


def test_skip_leaves_the_existing_output_alone(paths: tuple[Path, Path, Path]) -> None:
    source, staged, final = paths

    decision = decide_output_collision(final=final, source=source, staged=staged, policy="skip")

    assert decision.wrote is False
    assert decision.replaced_existing is False
    assert "kept the one that was already there" in decision.reason


def test_keep_both_writes_alongside_with_a_deterministic_suffix(paths: tuple[Path, Path, Path]) -> None:
    source, staged, final = paths

    decision = decide_output_collision(final=final, source=source, staged=staged, policy="keep_both")

    assert decision.wrote is True
    assert decision.replaced_existing is False
    assert decision.destination.name == "Film (2001) (2).mkv"


def test_keep_both_keeps_counting_past_an_existing_suffix(paths: tuple[Path, Path, Path]) -> None:
    """Deterministic, so the same collision produces the same name every run."""

    source, staged, final = paths
    (final.parent / "Film (2001) (2).mkv").write_bytes(b"x")

    decision = decide_output_collision(final=final, source=source, staged=staged, policy="keep_both")

    assert decision.destination.name == "Film (2001) (3).mkv"


def test_replace_if_larger_replaces_a_smaller_existing_output(paths: tuple[Path, Path, Path]) -> None:
    source, staged, final = paths  # staged is 200 bytes, final is 150

    decision = decide_output_collision(final=final, source=source, staged=staged, policy="replace_if_larger")

    assert decision.wrote is True
    assert decision.replaced_existing is True
    assert "200 bytes against 150" in decision.reason


def test_replace_if_larger_keeps_a_bigger_existing_output(paths: tuple[Path, Path, Path]) -> None:
    source, staged, final = paths
    final.write_bytes(b"o" * 500)

    decision = decide_output_collision(final=final, source=source, staged=staged, policy="replace_if_larger")

    assert decision.wrote is False
    assert "kept the existing one" in decision.reason


def test_replace_if_larger_keeps_the_existing_output_when_it_cannot_compare(
    paths: tuple[Path, Path, Path],
) -> None:
    """A failed check is not evidence that replacing is safe."""

    source, _staged, final = paths

    decision = decide_output_collision(final=final, source=source, staged=None, policy="replace_if_larger")

    assert decision.wrote is False
    assert "could not compare" in decision.reason


def test_replace_if_newer_replaces_when_the_source_is_newer(paths: tuple[Path, Path, Path]) -> None:
    source, staged, final = paths
    os.utime(final, (1_000_000_000, 1_000_000_000))
    os.utime(source, (2_000_000_000, 2_000_000_000))

    decision = decide_output_collision(final=final, source=source, staged=staged, policy="replace_if_newer")

    assert decision.wrote is True
    assert decision.replaced_existing is True


def test_replace_if_newer_keeps_the_existing_output_when_the_source_is_older(
    paths: tuple[Path, Path, Path],
) -> None:
    source, staged, final = paths
    os.utime(final, (2_000_000_000, 2_000_000_000))
    os.utime(source, (1_000_000_000, 1_000_000_000))

    decision = decide_output_collision(final=final, source=source, staged=staged, policy="replace_if_newer")

    assert decision.wrote is False
    assert "not newer" in decision.reason


def test_replace_if_newer_keeps_the_existing_output_when_it_cannot_compare(
    paths: tuple[Path, Path, Path],
) -> None:
    _source, staged, final = paths

    decision = decide_output_collision(final=final, source=None, staged=staged, policy="replace_if_newer")

    assert decision.wrote is False
    assert "could not compare timestamps" in decision.reason


# --- the scenario the issue is actually about ---------------------------------------


def test_two_sources_colliding_on_one_output_path(tmp_path: Path) -> None:
    """A repack alongside the original, or the same title in two release folders.

    Under 'replace' the second destroys the first — the current behaviour, now explicit.
    Under 'keep_both' they coexist, which is the whole reason the policy exists.
    """

    out = tmp_path / "out"
    out.mkdir()
    final = out / "Film (2001).mkv"

    first_source = tmp_path / "release-a" / "Film.mkv"
    first_source.parent.mkdir()
    first_source.write_bytes(b"first")
    second_source = tmp_path / "release-b" / "Film.REPACK.mkv"
    second_source.parent.mkdir()
    second_source.write_bytes(b"second")

    # First file lands with nothing in the way.
    first = decide_output_collision(final=final, source=first_source, staged=first_source, policy="keep_both")
    assert first.destination == final
    final.write_bytes(b"first")

    # Second file finds it occupied.
    second = decide_output_collision(final=final, source=second_source, staged=second_source, policy="keep_both")

    assert second.destination.name == "Film (2001) (2).mkv"
    assert second.replaced_existing is False
    # The first output is untouched, which is the outcome 'replace' could not give.
    assert final.read_bytes() == b"first"


def test_the_same_collision_under_replace_destroys_the_first_output(tmp_path: Path) -> None:
    out = tmp_path / "out"
    out.mkdir()
    final = out / "Film (2001).mkv"
    final.write_bytes(b"first")
    second_source = tmp_path / "Film.REPACK.mkv"
    second_source.write_bytes(b"second")

    decision = decide_output_collision(final=final, source=second_source, staged=second_source, policy="replace")

    # Explicit now, and recorded — which is the difference from a silent overwrite.
    assert decision.wrote is True
    assert decision.replaced_existing is True
    assert decision.policy == "replace"


def test_every_decision_carries_a_reason_and_its_policy(paths: tuple[Path, Path, Path]) -> None:
    """ "Why is there no new output for this file" has to be answerable."""

    source, staged, final = paths
    for policy in COLLISION_POLICIES:
        decision = decide_output_collision(final=final, source=source, staged=staged, policy=policy)
        assert decision.reason.strip()
        assert decision.policy == policy
