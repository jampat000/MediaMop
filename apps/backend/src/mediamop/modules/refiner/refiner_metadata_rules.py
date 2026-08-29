"""Embedded images, attachments and container metadata.

Refiner had no metadata handling at all. It planned video, audio and subtitle streams and
copied everything else through untouched, so embedded cover art, stale titles, attached
fonts and container tags all survived a pass.

The cover-art case is the one with teeth. **An embedded poster is an mjpeg video stream**,
and the plan kept every video stream it found:

    video_indices = [int(s["index"]) for s in video]

So the poster was carried into the output and counted as video. Any logic that reasons
about "the video stream" then has to cope with there being two of them, which is a bug
waiting for the first person who writes it.

Everything here defaults **off**. A pass that started stripping titles and tags because
an upgrade landed would be changing files nobody asked it to change.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

#: Codecs that appear as a video stream but are a still image. ffprobe reports an
#: embedded poster exactly like a video track, so the codec is the only reliable signal.
_IMAGE_CODECS: frozenset[str] = frozenset({"mjpeg", "png", "bmp", "gif", "webp", "jpeg", "tiff"})

#: ffprobe's own marker for a stream that is a thumbnail rather than the picture.
_ATTACHED_PIC = "attached_pic"


@dataclass(frozen=True, slots=True)
class MetadataRules:
    """What to strip. All off by default, so an upgrade changes nothing."""

    remove_images: bool = False
    remove_attachments: bool = False
    remove_title: bool = False
    remove_language_tags: bool = False
    remove_other_metadata: bool = False

    @property
    def any_enabled(self) -> bool:
        return (
            self.remove_images
            or self.remove_attachments
            or self.remove_title
            or self.remove_language_tags
            or self.remove_other_metadata
        )


def is_image_stream(stream: dict[str, Any]) -> bool:
    """True for an embedded poster or thumbnail carried as a video stream.

    Two signals, either of which is enough. ``attached_pic`` is the explicit one and is
    what a well-formed file sets; the codec check catches files where it is absent, which
    is common in output from older tools.
    """

    if not isinstance(stream, dict):
        return False
    disposition = stream.get("disposition")
    if isinstance(disposition, dict) and int(disposition.get(_ATTACHED_PIC) or 0):
        return True
    codec = str(stream.get("codec_name") or "").strip().lower()
    if codec not in _IMAGE_CODECS:
        return False
    # A codec alone is not proof: some genuine video is mjpeg. A single frame, or a
    # stream with no frame rate, is a still.
    frames = stream.get("nb_frames")
    try:
        if frames is not None and int(frames) <= 1:
            return True
    except (TypeError, ValueError):
        pass
    rate = str(stream.get("avg_frame_rate") or "").strip()
    return rate in {"", "0/0", "0/1"}


def is_attachment_stream(stream: dict[str, Any]) -> bool:
    """True for an attached font or similar."""

    return isinstance(stream, dict) and str(stream.get("codec_type") or "").strip().lower() == "attachment"


def split_video_and_images(video_streams: list[dict[str, Any]]) -> tuple[list[dict], list[dict]]:
    """``(real video, embedded images)``.

    Always separated, whether or not removal is switched on, so the plan knows which
    stream is the picture even when the poster is being kept.
    """

    real: list[dict] = []
    images: list[dict] = []
    for stream in video_streams:
        (images if is_image_stream(stream) else real).append(stream)
    # A file of nothing but images is not a file with no video: keeping the first stream
    # rather than planning an output with no picture at all is the safe reading of an
    # ambiguous probe.
    if not real and images:
        return [images[0]], images[1:]
    return real, images


def describe_image_stream(stream: dict[str, Any]) -> str:
    codec = str(stream.get("codec_name") or "unknown").strip()
    width = stream.get("width")
    height = stream.get("height")
    size = f"{width}x{height}" if width and height else "unknown size"
    return f"embedded image ({codec}, {size})"


def describe_attachment_stream(stream: dict[str, Any]) -> str:
    tags = stream.get("tags")
    name = ""
    if isinstance(tags, dict):
        name = str(tags.get("filename") or tags.get("title") or "").strip()
    return f"attachment ({name})" if name else "attachment"


def metadata_argv_flags(rules: MetadataRules) -> list[str]:
    """The ffmpeg flags for container-level stripping.

    Order matters and is deliberate: ``-map_metadata -1`` clears everything, so a
    narrower option has to come *after* it or be replaced by it. When only the title is
    being removed, the title is cleared on its own and the rest of the metadata survives,
    which is what "remove the title" means.
    """

    flags: list[str] = []
    if rules.remove_other_metadata:
        flags.extend(["-map_metadata", "-1"])
    elif rules.remove_title:
        flags.extend(["-metadata", "title="])
    if rules.remove_other_metadata and rules.remove_title:
        # Already cleared by -map_metadata, but stated explicitly so a container that
        # regenerates a title from the filename does not quietly reintroduce one.
        flags.extend(["-metadata", "title="])
    if rules.remove_language_tags:
        flags.extend(["-metadata:s", "language="])
    return flags


def metadata_removal_notes(
    rules: MetadataRules,
    *,
    removed_images: list[dict[str, Any]],
    removed_attachments: list[dict[str, Any]],
) -> list[str]:
    """What was stripped, for the before/after display and the activity detail."""

    notes: list[str] = []
    for stream in removed_images:
        notes.append(f"Removed {describe_image_stream(stream)}.")
    for stream in removed_attachments:
        notes.append(f"Removed {describe_attachment_stream(stream)}.")
    if rules.remove_title:
        notes.append("Removed the container title.")
    if rules.remove_language_tags:
        notes.append("Removed stream language tags.")
    if rules.remove_other_metadata:
        notes.append("Removed the remaining container metadata.")
    return notes
