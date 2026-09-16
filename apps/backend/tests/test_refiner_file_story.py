"""A file's history told in plain language (#468)."""

from __future__ import annotations

from typing import Any

from mediamop.modules.refiner.refiner_file_story import narrate_pass


def _headings(steps: list[Any]) -> list[str]:
    return [step.heading for step in steps]


def _all_text(steps: list[Any]) -> str:
    return " ".join(f"{step.heading} {step.sentence}" for step in steps)


def _successful_remux(**over: Any) -> dict[str, Any]:
    detail: dict[str, Any] = {
        "ok": True,
        "media_scope": "movie",
        "stream_counts": {"video": 1, "audio": 3, "subtitle": 9},
        "audio_before": "English TrueHD 7.1 · English EAC3 5.1 · English AC3 2.0",
        "subs_before": "English · French · German",
        "remux_required": True,
        "removed_audio": ["#2 English TrueHD", "#3 English AC3"],
        "removed_subtitles": ["#4 French", "#5 German"],
        "audio_after": "English EAC3 5.1",
        "subs_after": "English",
        "ffmpeg_argv": ["ffmpeg", "-i", "in.mkv", "-map", "0:0", "-c", "copy", "out.mkv"],
        "elapsed_seconds": 372,
        "source_size_bytes": 61 * 1024**3,
        "output_size_bytes": 48 * 1024**3,
        "output_completeness_check": "passed",
        "output_file": "/refined/movies/Arrival (2016)/Arrival.mkv",
    }
    detail.update(over)
    return detail


def test_a_successful_pass_reads_as_a_sequence() -> None:
    steps = narrate_pass(_successful_remux(), library_name="Films 4K")
    assert _headings(steps) == ["Picked up", "Looked inside", "Planned", "Worked", "Checked", "Handed back"]


def test_it_names_the_library_and_kind() -> None:
    steps = narrate_pass(_successful_remux(), library_name="Films 4K")
    assert steps[0].sentence == "MediaMop took this file as a film in the Films 4K library."


def test_it_says_what_it_found_inside() -> None:
    text = _all_text(narrate_pass(_successful_remux()))
    assert "1 video track, 3 audio tracks and 9 subtitle tracks" in text
    assert "English TrueHD 7.1" in text


def test_it_says_what_it_removed_and_kept() -> None:
    text = _all_text(narrate_pass(_successful_remux()))
    assert "remove 2 audio tracks" in text
    assert "remove 2 subtitle tracks" in text
    assert "Audio kept: English EAC3 5.1" in text


def test_it_reports_time_and_space_saved() -> None:
    worked = next(s for s in narrate_pass(_successful_remux()) if s.heading == "Worked")
    assert "6 minutes" in worked.sentence
    assert "saving 13.0 GB" in worked.sentence
    assert worked.tone == "good"


# --- the reassurance must be earned ------------------------------------------------------------


def test_it_says_the_video_was_not_re_encoded_when_the_argv_proves_it() -> None:
    text = _all_text(narrate_pass(_successful_remux()))
    assert "copied, not re-encoded" in text


def test_it_does_not_claim_a_stream_copy_when_video_was_encoded() -> None:
    """The day encoding ships, an unconditional sentence would lie about someone's picture."""

    detail = _successful_remux(
        ffmpeg_argv=["ffmpeg", "-i", "in.mkv", "-c", "copy", "-c:v", "libx265", "out.mkv"],
    )
    assert "not re-encoded" not in _all_text(narrate_pass(detail))


def test_it_makes_no_claim_without_evidence() -> None:
    detail = _successful_remux()
    del detail["ffmpeg_argv"]
    assert "not re-encoded" not in _all_text(narrate_pass(detail))


def test_it_makes_no_claim_about_a_failed_pass() -> None:
    detail = _successful_remux(ok=False, reason="ffmpeg could not read the audio track.")
    assert "not re-encoded" not in _all_text(narrate_pass(detail))


# --- other outcomes -----------------------------------------------------------------------------


def test_a_file_that_needed_nothing_says_so_plainly() -> None:
    steps = narrate_pass({"ok": True, "remux_required": False})
    planned = next(s for s in steps if s.heading == "Planned")
    assert planned.sentence == "Everything already matched your settings, so there was nothing to change."
    assert planned.tone == "good"


def test_a_failure_says_why() -> None:
    steps = narrate_pass(
        {"ok": False, "reason": "No encoder is available for DTS-HD Master Audio."},
        library_name="Films 4K",
    )
    final = steps[-1]
    assert final.heading == "Could not finish"
    assert final.sentence == "No encoder is available for DTS-HD Master Audio."
    assert final.tone == "bad"
    assert "Handed back" not in _headings(steps)


def test_a_failure_with_no_reason_still_reads_as_a_sentence() -> None:
    final = narrate_pass({"ok": False})[-1]
    assert final.sentence.endswith(".")
    assert "does not say why" in final.sentence


def test_an_existing_output_is_explained() -> None:
    detail = _successful_remux(
        output_collision_action="skip",
        output_collision_reason="An output already exists at Arrival.mkv and this library leaves existing outputs alone.",
    )
    step = next(s for s in narrate_pass(detail) if s.heading == "An output already existed")
    assert step.tone == "warn"


def test_a_failed_completeness_check_is_bad_news() -> None:
    detail = _successful_remux(
        output_completeness_check="failed",
        output_completeness_note="The output file is empty (zero bytes).",
    )
    checked = next(s for s in narrate_pass(detail) if s.heading == "Checked")
    assert checked.tone == "bad"
    assert checked.sentence == "The output file is empty (zero bytes)."


# --- old and odd records ------------------------------------------------------------------------


def test_an_empty_record_never_raises() -> None:
    assert narrate_pass({}) is not None


def test_a_non_dict_record_yields_nothing() -> None:
    assert narrate_pass("not a record") == []  # type: ignore[arg-type]
    assert narrate_pass(None) == []  # type: ignore[arg-type]


def test_placeholder_track_lines_are_not_narrated_as_tracks() -> None:
    """The display helpers use '—' and 'None' for empty; neither is a track."""

    detail = {
        "ok": True,
        "stream_counts": {"video": 1, "audio": 1, "subtitle": 0},
        "subs_before": "—",
        "subs_after": "None",
    }
    text = _all_text(narrate_pass(detail))
    assert "Subtitles: —" not in text
    assert "Subtitles kept: None" not in text


def test_no_raw_field_names_leak_into_the_story() -> None:
    """Operator-facing text must never show a key like remux_required or ffmpeg_argv."""

    text = _all_text(narrate_pass(_successful_remux(), library_name="Films 4K"))
    for key in ("remux_required", "ffmpeg_argv", "stream_counts", "output_completeness_check", "_bytes", "None"):
        assert key not in text
