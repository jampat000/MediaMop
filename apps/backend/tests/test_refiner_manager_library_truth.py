"""The gate in front of a delete: only a manager that answered can clear a folder."""

from __future__ import annotations

from pathlib import Path

from mediamop.modules.refiner.manager_library_truth import evaluate_library_truth_for_folder
from tests.manager_signal_helpers import truth_no_signal, truth_reported, truth_unreachable


def test_no_manager_connected_never_clears_a_delete(tmp_path: Path) -> None:
    verdict = evaluate_library_truth_for_folder([], folder=tmp_path, media_scope="movie")
    assert verdict.check == "skipped"
    assert verdict.clears_delete is False
    assert "No media manager is connected for Movies" in verdict.note


def test_every_manager_reporting_nothing_inside_the_folder_clears_it(tmp_path: Path) -> None:
    answers = [
        truth_reported([str(tmp_path.parent / "elsewhere" / "f.mkv")], name="1080p", connection_id=1),
        truth_reported([], kind="sonarr", name="Main", connection_id=2),
    ]
    verdict = evaluate_library_truth_for_folder(answers, folder=tmp_path, media_scope="movie")
    assert verdict.check == "passed"
    assert verdict.clears_delete is True
    assert "Radarr (1080p), Sonarr (Main)" in verdict.note


def test_one_manager_keeping_a_file_inside_the_folder_blocks_the_delete(tmp_path: Path) -> None:
    kept = tmp_path / "Title" / "f.mkv"
    kept.parent.mkdir(parents=True)
    kept.write_bytes(b"x")
    answers = [
        truth_reported([], name="1080p", connection_id=1),
        truth_reported([str(kept)], name="4K", connection_id=2),
    ]
    verdict = evaluate_library_truth_for_folder(answers, folder=tmp_path, media_scope="movie")
    assert verdict.check == "failed"
    assert verdict.clears_delete is False
    assert "Radarr (4K) still keeps at least one library file" in verdict.note
    assert verdict.matched_paths == (str(kept.resolve()),)


def test_an_unreachable_manager_blocks_the_delete_and_is_named(tmp_path: Path) -> None:
    answers = [
        truth_reported([], name="1080p", connection_id=1),
        truth_unreachable(name="4K", connection_id=2, detail="MediaMop could not reach Radarr (4K)."),
    ]
    verdict = evaluate_library_truth_for_folder(answers, folder=tmp_path, media_scope="movie")
    assert verdict.check == "skipped"
    assert verdict.clears_delete is False
    assert "could not confirm with Radarr (4K)" in verdict.note
    assert "MediaMop could not reach Radarr (4K)." in verdict.note


def test_a_manager_that_cannot_report_library_truth_also_blocks_the_delete(tmp_path: Path) -> None:
    """Deluno answers the queue question but not this one; unknown is not a clearance."""

    answers = [truth_reported([], name="1080p", connection_id=1), truth_no_signal(name="Main", connection_id=2)]
    verdict = evaluate_library_truth_for_folder(answers, folder=tmp_path, media_scope="movie")
    assert verdict.check == "skipped"
    assert "could not confirm with Deluno (Main)" in verdict.note


def test_an_unreadable_path_is_ignored_rather_than_crashing_the_gate(tmp_path: Path) -> None:
    verdict = evaluate_library_truth_for_folder(
        [truth_reported(["", "   ", "relative/but/elsewhere.mkv"])],
        folder=tmp_path,
        media_scope="tv",
    )
    assert verdict.check == "passed"
