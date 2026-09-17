"""Tell the story of what happened to a file, in plain language (#468).

Every pass already stores a complete forensic record in ``refiner_file_log.detail_json``: what was
found inside the file, what was planned, what was removed, sizes, timings, the completeness check
and the collision decision. None of it was ever shown in a form an operator could read. This turns
that record into a sequence of short, plain steps.

Three rules shape it, all from ``docs/operator-messaging-standard.md``:

* **Narrated at read time, never stored.** The story is rebuilt from the stored record on every
  request, so improving a sentence here improves the whole history rather than only new entries.
* **Explain what did not happen, too.** "The video was copied, not re-encoded" is one of the most
  reassuring things this product can say, and it was never said anywhere.
* **Never break on an old record.** Records written before a field existed simply produce a shorter
  story. A missing field is omitted, never rendered as a raw key or a broken sentence.

No jargon leads a sentence. The raw record stays available beside the story for anyone who wants the
technical detail; it is just never the first thing shown.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

Tone = Literal["neutral", "good", "warn", "bad"]

#: Values the track-display helpers use to mean "nothing here", which must not be narrated as tracks.
_EMPTY_TRACK_LINES = frozenset({"", "—", "-", "none", "None"})


@dataclass(frozen=True, slots=True)
class StoryStep:
    heading: str
    sentence: str
    tone: Tone = "neutral"


def _text(value: Any) -> str:
    return " ".join(str(value).split()) if value is not None else ""


def _list(value: Any) -> list[str]:
    if isinstance(value, (list, tuple)):
        return [_text(item) for item in value if _text(item)]
    return []


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number else None  # reject NaN


def _bytes(value: float) -> str:
    size = abs(value)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            shown = f"{size:.0f}" if unit == "B" or size >= 100 else f"{size:.1f}"
            return f"{'-' if value < 0 else ''}{shown} {unit}"
        size /= 1024
    return f"{value:.0f} B"


def _duration(seconds: float) -> str:
    if seconds < 1:
        return "under a second"
    if seconds < 90:
        whole = round(seconds)
        return f"{whole} second{'s' if whole != 1 else ''}"
    minutes = round(seconds / 60)
    if minutes < 90:
        return f"{minutes} minute{'s' if minutes != 1 else ''}"
    hours = seconds / 3600
    return f"{hours:.1f} hours"


def _plural(count: int, word: str) -> str:
    return f"{count} {word}{'' if count == 1 else 's'}"


def _track_line(value: Any) -> str | None:
    line = _text(value)
    return None if line in _EMPTY_TRACK_LINES else line


def _picked_up(detail: dict[str, Any], library_name: str) -> StoryStep | None:
    where = _text(library_name)
    scope = _text(detail.get("media_scope"))
    kind = {"tv": "TV", "movie": "film"}.get(scope, "")
    if not where and not kind:
        return None
    sentence = "MediaMop took this file"
    if kind:
        sentence += f" as a {kind}"
    if where:
        sentence += f" in the {where} library"
    return StoryStep("Picked up", f"{sentence}.")


def _looked_inside(detail: dict[str, Any]) -> StoryStep | None:
    raw_counts = detail.get("stream_counts")
    counts: dict[str, Any] = raw_counts if isinstance(raw_counts, dict) else {}
    video = int(_number(counts.get("video")) or 0)
    audio = int(_number(counts.get("audio")) or 0)
    subs = int(_number(counts.get("subtitle")) or 0)
    audio_line = _track_line(detail.get("audio_before"))
    subs_line = _track_line(detail.get("subs_before"))

    if not counts and not audio_line and not subs_line:
        return None

    parts: list[str] = []
    if counts:
        parts.append(
            f"{_plural(video, 'video track')}, {_plural(audio, 'audio track')} and {_plural(subs, 'subtitle track')}"
        )
    sentence = f"It found {parts[0]}." if parts else "It looked inside the file."
    if audio_line:
        sentence += f" Audio: {audio_line}."
    if subs_line:
        sentence += f" Subtitles: {subs_line}."
    return StoryStep("Looked inside", sentence)


def _planned(detail: dict[str, Any], ok: bool) -> StoryStep | None:
    if detail.get("pass_through_unchanged") is True:
        return StoryStep(
            "Planned",
            "You asked for this file to pass through unchanged, so MediaMop planned to hand it on exactly as it arrived.",
        )

    removed_audio = _list(detail.get("removed_audio"))
    removed_subs = _list(detail.get("removed_subtitles"))
    removed_images = _list(detail.get("removed_images"))
    removed_attachments = _list(detail.get("removed_attachments"))
    audio_after = _track_line(detail.get("audio_after"))
    subs_after = _track_line(detail.get("subs_after"))
    remux_required = detail.get("remux_required")

    if remux_required is False:
        return StoryStep(
            "Planned",
            "Everything already matched your settings, so there was nothing to change.",
            "good",
        )

    changes: list[str] = []
    if removed_audio:
        changes.append(f"remove {_plural(len(removed_audio), 'audio track')}")
    if removed_subs:
        changes.append(f"remove {_plural(len(removed_subs), 'subtitle track')}")
    if removed_images:
        changes.append(f"remove {_plural(len(removed_images), 'embedded image')}")
    if removed_attachments:
        changes.append(f"remove {_plural(len(removed_attachments), 'attachment')}")
    if detail.get("metadata_removed"):
        changes.append("strip the file's metadata")

    if not changes and not audio_after and not subs_after:
        return None

    sentence = f"MediaMop planned to {', '.join(changes)}." if changes else "MediaMop planned the output tracks."
    if audio_after:
        sentence += f" Audio kept: {audio_after}."
    if subs_after:
        sentence += f" Subtitles kept: {subs_after}."
    if ok and remux_required is True and _video_was_stream_copied(detail):
        # The reassurance people most want and were never given. Only said when the recorded argv
        # proves it: encoding (HDR to SDR, scaling) is planned, and the day it ships an unconditional
        # version of this sentence would silently become a lie about someone's picture.
        sentence += " The video is copied, not re-encoded, so picture quality is unchanged."
    return StoryStep("Planned", sentence)


def _video_was_stream_copied(detail: dict[str, Any]) -> bool:
    """True only when the stored ffmpeg command demonstrably copied the video stream.

    Requires evidence rather than assuming: a record with no argv (older, or a pass that never ran
    ffmpeg) proves nothing, so the claim is left out rather than guessed.
    """

    argv = detail.get("ffmpeg_argv")
    if not isinstance(argv, (list, tuple)):
        return False
    args = [str(arg) for arg in argv]
    copies_everything = False
    for index, arg in enumerate(args[:-1]):
        following = args[index + 1]
        if arg in {"-c:v", "-codec:v", "-vcodec"} and following != "copy":
            return False
        if arg in {"-c", "-codec", "-c:v", "-codec:v", "-vcodec"} and following == "copy":
            copies_everything = True
    return copies_everything


def _choices(detail: dict[str, Any]) -> StoryStep | None:
    notes = _list(detail.get("audio_selection_notes"))
    if not notes:
        return None
    return StoryStep("Why these tracks", " ".join(note.rstrip(".") + "." for note in notes[:4]))


def _worked(detail: dict[str, Any]) -> StoryStep | None:
    elapsed = _number(detail.get("elapsed_seconds"))
    source = _number(detail.get("source_size_bytes"))
    output = _number(detail.get("output_size_bytes"))
    if elapsed is None and (source is None or output is None):
        return None

    bits: list[str] = []
    if elapsed is not None and elapsed > 0:
        bits.append(f"It took {_duration(elapsed)}")
    if source is not None and output is not None and source > 0:
        saved = source - output
        if saved > 0:
            bits.append(f"{_bytes(source)} became {_bytes(output)}, saving {_bytes(saved)}")
        elif saved < 0:
            bits.append(f"{_bytes(source)} became {_bytes(output)}")
        else:
            bits.append(f"the size stayed at {_bytes(source)}")
    if not bits:
        return None
    sentence = "; ".join(bits)
    return StoryStep(
        "Worked",
        f"{sentence[:1].upper()}{sentence[1:]}.",
        "good" if source and output and source > output else "neutral",
    )


def _verified(detail: dict[str, Any]) -> StoryStep | None:
    check = _text(detail.get("output_completeness_check")).lower()
    note = _text(detail.get("output_completeness_note"))
    if check == "passed":
        return StoryStep("Checked", "MediaMop checked the finished file was complete before handing it on.", "good")
    if check == "failed":
        return StoryStep("Checked", note or "The finished file did not pass MediaMop's completeness check.", "bad")
    return None


def _collision(detail: dict[str, Any]) -> StoryStep | None:
    reason = _text(detail.get("output_collision_reason"))
    if not reason:
        return None
    action = _text(detail.get("output_collision_action")).lower()
    return StoryStep("An output already existed", reason, "warn" if action == "skip" else "neutral")


def _handed_back(detail: dict[str, Any], ok: bool) -> StoryStep | None:
    if not ok:
        return None
    destination = _text(detail.get("output_file"))
    if not destination:
        return None
    return StoryStep(
        "Handed back", f"The result was written to {destination} for your media manager to import.", "good"
    )


def _failed(detail: dict[str, Any]) -> StoryStep | None:
    reason = _text(detail.get("reason")) or _text(detail.get("preflight_reason"))
    return StoryStep(
        "Could not finish",
        reason or "MediaMop could not process this file, and the record does not say why.",
        "bad",
    )


def narrate_pass(detail: dict[str, Any], *, library_name: str = "") -> list[StoryStep]:
    """The steps of one pass, in the order they happened. Never raises on a partial record."""

    if not isinstance(detail, dict):
        return []
    ok = detail.get("ok") is not False

    candidates = [
        _picked_up(detail, library_name),
        _looked_inside(detail),
        _planned(detail, ok),
        _choices(detail),
    ]
    if ok:
        candidates += [_worked(detail), _verified(detail), _collision(detail), _handed_back(detail, ok)]
    else:
        candidates.append(_failed(detail))
    return [step for step in candidates if step is not None]
