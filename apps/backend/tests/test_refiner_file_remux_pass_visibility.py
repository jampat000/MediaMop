"""Refiner remux pass activity payload helpers (outcomes, titles, argv clipping)."""

from __future__ import annotations

from mediamop.modules.refiner.refiner_file_remux_pass_visibility import (
    REMUX_PASS_OUTCOME_LIVE_OUTPUT_WRITTEN,
    REMUX_PASS_OUTCOME_LIVE_SKIPPED_NOT_REQUIRED,
    clip_remux_pass_payload_for_activity,
    remux_pass_activity_title,
    remux_pass_result_to_activity_detail,
    summarize_remux_plan,
)
from mediamop.modules.refiner.refiner_remux_rules import PlannedTrack, RemuxPlan


def test_summarize_remux_plan_includes_streams() -> None:
    plan = RemuxPlan(
        video_indices=[0],
        audio=[
            PlannedTrack(
                input_index=1,
                lang_label="eng",
                kind="audio",
                channels=2,
                codec_name="aac",
            ),
        ],
        subtitles=[],
        removed_audio=["#2 commentary"],
    )
    s = summarize_remux_plan(plan)
    assert "video copy indices: [0]" in s
    assert "#1 eng" in s
    assert "commentary" in s


def test_activity_title_per_outcome() -> None:
    base = {"relative_media_path": "movies/foo.mkv"}
    assert "processed successfully" in remux_pass_activity_title(
        {**base, "outcome": REMUX_PASS_OUTCOME_LIVE_OUTPUT_WRITTEN},
    ).lower()
    assert "matched your refiner rules" in remux_pass_activity_title(
        {**base, "outcome": REMUX_PASS_OUTCOME_LIVE_SKIPPED_NOT_REQUIRED},
    ).lower()


def test_clip_argv_for_activity_truncates_long_lists() -> None:
    long_argv = [f"a{i}" for i in range(100)]
    clipped = clip_remux_pass_payload_for_activity({"ffmpeg_argv": long_argv})
    assert clipped["ffmpeg_argv_truncated"] is True
    assert len(clipped["ffmpeg_argv"]) < len(long_argv)


def test_remux_pass_result_to_activity_detail_is_valid_json() -> None:
    detail = remux_pass_result_to_activity_detail(
        {"ok": True, "outcome": REMUX_PASS_OUTCOME_LIVE_OUTPUT_WRITTEN, "relative_media_path": "x.mkv"},
    )
    assert '"outcome":"live_output_written"' in detail
