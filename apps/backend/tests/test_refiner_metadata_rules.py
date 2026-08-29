"""Embedded images, attachments and container metadata.

Refiner had no metadata handling: it planned video, audio and subtitle streams and copied
everything else through untouched. The case with teeth is cover art — **an embedded poster
is an mjpeg video stream**, and the plan kept every video stream it found, so the poster
came through and was counted as video (#342).

Every option defaults off, and there is a test asserting that a default configuration
changes nothing, because an upgrade that started stripping titles would be changing files
nobody asked it to change.
"""

from __future__ import annotations

from mediamop.modules.refiner.refiner_metadata_rules import (
    MetadataRules,
    is_attachment_stream,
    is_image_stream,
    metadata_argv_flags,
    metadata_removal_notes,
    split_video_and_images,
)
from mediamop.modules.refiner.refiner_remux_mux import build_ffmpeg_argv
from mediamop.modules.refiner.refiner_remux_rules import (
    attachment_streams,
    default_refiner_remux_rules_config,
    is_remux_required,
    plan_remux,
    split_streams,
)


def _video(index: int = 0) -> dict:
    return {
        "index": index,
        "codec_type": "video",
        "codec_name": "h264",
        "width": 1920,
        "height": 1080,
        "avg_frame_rate": "24000/1001",
        "nb_frames": "150000",
    }


def _cover_art(index: int = 1, *, attached_pic: bool = True) -> dict:
    """An embedded poster, exactly as ffprobe reports one."""

    stream = {
        "index": index,
        "codec_type": "video",
        "codec_name": "mjpeg",
        "width": 600,
        "height": 900,
        "avg_frame_rate": "0/0",
        "nb_frames": "1",
    }
    if attached_pic:
        stream["disposition"] = {"attached_pic": 1, "default": 0}
    return stream


def _audio(index: int = 2) -> dict:
    return {
        "index": index,
        "codec_type": "audio",
        "codec_name": "eac3",
        "channels": 6,
        "bit_rate": "640000",
        "tags": {"language": "eng"},
        "disposition": {"default": 1},
    }


def _attachment(index: int = 3, name: str = "Arial.ttf") -> dict:
    return {
        "index": index,
        "codec_type": "attachment",
        "codec_name": "ttf",
        "tags": {"filename": name},
    }


def _probe(*streams: dict) -> dict:
    return {"streams": list(streams)}


def _config(**over) -> object:
    from dataclasses import replace

    base = default_refiner_remux_rules_config()
    return replace(base, metadata=MetadataRules(**over)) if over else base


# --- recognising a poster ------------------------------------------------------------


def test_an_attached_pic_is_recognised_as_an_image() -> None:
    assert is_image_stream(_cover_art()) is True


def test_a_single_frame_mjpeg_with_no_disposition_is_still_recognised() -> None:
    """Common in output from older tools, which omit the attached_pic flag."""

    assert is_image_stream(_cover_art(attached_pic=False)) is True


def test_real_video_is_not_mistaken_for_a_poster() -> None:
    assert is_image_stream(_video()) is False


def test_genuine_mjpeg_video_is_not_mistaken_for_a_poster() -> None:
    """A codec alone is not proof: some real video is mjpeg."""

    stream = {
        "index": 0,
        "codec_type": "video",
        "codec_name": "mjpeg",
        "avg_frame_rate": "25/1",
        "nb_frames": "50000",
    }

    assert is_image_stream(stream) is False


def test_an_attachment_is_recognised() -> None:
    assert is_attachment_stream(_attachment()) is True
    assert is_attachment_stream(_audio()) is False


def test_video_and_images_are_always_separated_even_when_kept() -> None:
    """So the plan knows which stream is the picture even when the poster stays."""

    real, images = split_video_and_images([_video(0), _cover_art(1)])

    assert [s["index"] for s in real] == [0]
    assert [s["index"] for s in images] == [1]


def test_a_file_of_nothing_but_images_keeps_one_rather_than_planning_no_picture() -> None:
    """An ambiguous probe must not produce an output with no video at all."""

    real, images = split_video_and_images([_cover_art(0), _cover_art(1)])

    assert len(real) == 1
    assert len(images) == 1


# --- the default changes nothing -----------------------------------------------------


def test_by_default_a_poster_is_carried_through_exactly_as_before() -> None:
    """An upgrade must not start changing files nobody asked it to change."""

    video, audio, subs = split_streams(_probe(_video(0), _cover_art(1), _audio(2)))
    plan = plan_remux(video=video, audio=audio, subtitles=subs, config=_config())

    assert plan is not None
    assert plan.video_indices == [0, 1]
    assert plan.removed_images == []
    assert plan.metadata_notes == []


def test_by_default_no_metadata_flags_reach_ffmpeg() -> None:
    assert metadata_argv_flags(MetadataRules()) == []


def test_by_default_a_file_needing_nothing_else_is_not_remuxed() -> None:
    video, audio, subs = split_streams(_probe(_video(0), _cover_art(1), _audio(2)))
    plan = plan_remux(video=video, audio=audio, subtitles=subs, config=_config())

    assert plan is not None
    assert is_remux_required(plan, audio, subs) is False


# --- removing --------------------------------------------------------------------


def test_removing_images_drops_the_poster_from_the_planned_streams() -> None:
    """The whole point: the poster stops being carried and stops counting as video."""

    video, audio, subs = split_streams(_probe(_video(0), _cover_art(1), _audio(2)))
    plan = plan_remux(video=video, audio=audio, subtitles=subs, config=_config(remove_images=True))

    assert plan is not None
    assert plan.video_indices == [0]
    assert len(plan.removed_images) == 1
    assert "mjpeg" in plan.removed_images[0]
    assert "600x900" in plan.removed_images[0]


def test_removing_attachments_drops_an_attached_font() -> None:
    probe = _probe(_video(0), _audio(1), _attachment(2, "Arial.ttf"))
    video, audio, subs = split_streams(probe)

    plan = plan_remux(
        video=video,
        audio=audio,
        subtitles=subs,
        config=_config(remove_attachments=True),
        attachments=attachment_streams(probe),
    )

    assert plan is not None
    assert len(plan.removed_attachments) == 1
    assert "Arial.ttf" in plan.removed_attachments[0]


def test_attachments_are_found_in_a_probe() -> None:
    probe = _probe(_video(0), _audio(1), _attachment(2), _attachment(3, "Comic.ttf"))

    assert [s["index"] for s in attachment_streams(probe)] == [2, 3]


def test_removing_the_title_leaves_other_metadata_alone() -> None:
    """ "Remove the title" means the title, not everything."""

    flags = metadata_argv_flags(MetadataRules(remove_title=True))

    assert flags == ["-metadata", "title="]
    assert "-map_metadata" not in flags


def test_removing_all_metadata_clears_everything_and_restates_the_title() -> None:
    """Stated explicitly so a container regenerating a title from the filename cannot
    quietly reintroduce one."""

    flags = metadata_argv_flags(MetadataRules(remove_other_metadata=True, remove_title=True))

    assert flags[:2] == ["-map_metadata", "-1"]
    assert flags[-2:] == ["-metadata", "title="]


def test_removing_language_tags_is_its_own_flag() -> None:
    assert metadata_argv_flags(MetadataRules(remove_language_tags=True)) == ["-metadata:s", "language="]


# --- the pass is required --------------------------------------------------------


def test_a_file_whose_only_change_is_a_stripped_poster_is_remuxed() -> None:
    """Otherwise it would be reported as "nothing to do" and copied through with the
    poster intact, which is the setting appearing not to work."""

    video, audio, subs = split_streams(_probe(_video(0), _cover_art(1), _audio(2)))
    plan = plan_remux(video=video, audio=audio, subtitles=subs, config=_config(remove_images=True))

    assert plan is not None
    assert is_remux_required(plan, audio, subs) is True


def test_a_file_whose_only_change_is_a_stripped_title_is_remuxed() -> None:
    video, audio, subs = split_streams(_probe(_video(0), _audio(1)))
    plan = plan_remux(video=video, audio=audio, subtitles=subs, config=_config(remove_title=True))

    assert plan is not None
    assert is_remux_required(plan, audio, subs) is True


def test_a_file_whose_only_change_is_stripped_metadata_is_remuxed() -> None:
    video, audio, subs = split_streams(_probe(_video(0), _audio(1)))
    plan = plan_remux(video=video, audio=audio, subtitles=subs, config=_config(remove_other_metadata=True))

    assert plan is not None
    assert is_remux_required(plan, audio, subs) is True


# --- ffmpeg argv ------------------------------------------------------------------


def test_the_argv_maps_only_the_real_video_when_images_are_removed() -> None:
    from pathlib import Path

    video, audio, subs = split_streams(_probe(_video(0), _cover_art(1), _audio(2)))
    plan = plan_remux(video=video, audio=audio, subtitles=subs, config=_config(remove_images=True))
    assert plan is not None

    argv = build_ffmpeg_argv(ffmpeg_bin="ffmpeg", src=Path("in.mkv"), dst=Path("out.mkv"), plan=plan)

    mapped = [argv[i + 1] for i, token in enumerate(argv) if token == "-map"]
    assert "0:0" in mapped
    assert "0:1" not in mapped


def test_the_argv_carries_the_metadata_flags_after_the_codec_copy() -> None:
    from pathlib import Path

    video, audio, subs = split_streams(_probe(_video(0), _audio(1)))
    plan = plan_remux(video=video, audio=audio, subtitles=subs, config=_config(remove_other_metadata=True))
    assert plan is not None

    argv = build_ffmpeg_argv(ffmpeg_bin="ffmpeg", src=Path("in.mkv"), dst=Path("out.mkv"), plan=plan)

    assert "-map_metadata" in argv
    assert argv.index("-map_metadata") > argv.index("copy")


# --- what the operator is told ----------------------------------------------------


def test_the_notes_say_what_was_removed() -> None:
    notes = metadata_removal_notes(
        MetadataRules(remove_images=True, remove_title=True),
        removed_images=[_cover_art()],
        removed_attachments=[],
    )

    assert any("embedded image" in n for n in notes)
    assert any("container title" in n for n in notes)


def test_the_display_line_is_empty_when_nothing_was_removed() -> None:
    from mediamop.modules.refiner.refiner_remux_track_display import metadata_removed_line_from_plan

    video, audio, subs = split_streams(_probe(_video(0), _audio(1)))
    plan = plan_remux(video=video, audio=audio, subtitles=subs, config=_config())
    assert plan is not None

    assert metadata_removed_line_from_plan(plan) in ("", "—", "-")


def test_the_display_line_names_a_removed_poster() -> None:
    from mediamop.modules.refiner.refiner_remux_track_display import metadata_removed_line_from_plan

    video, audio, subs = split_streams(_probe(_video(0), _cover_art(1), _audio(2)))
    plan = plan_remux(video=video, audio=audio, subtitles=subs, config=_config(remove_images=True))
    assert plan is not None

    assert "embedded image" in metadata_removed_line_from_plan(plan)
