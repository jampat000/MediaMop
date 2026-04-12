"""Human-readable audio and subtitle lines from ffprobe data and remux plans."""

from __future__ import annotations

from typing import Any

from mediamop.modules.refiner.refiner_remux_lang_display import refiner_lang_display, refiner_lang_display_or_blank
from mediamop.modules.refiner.refiner_remux_rules import PlannedTrack, RemuxPlan, _stream_tags, normalize_lang


def _channel_layout_label(n: int) -> str:
    if n <= 0:
        return ""
    if n == 1:
        return "1.0"
    if n == 2:
        return "2.0"
    if n == 6:
        return "5.1"
    if n == 8:
        return "7.1"
    return f"{n} ch"


def _codec_label(codec_name: str) -> str:
    c = (codec_name or "").strip().lower()
    if not c:
        return ""
    aliases = {
        "truehd": "TrueHD",
        "dts_hd": "DTS-HD MA",
        "eac3": "E-AC-3",
        "ac3": "AC-3",
        "aac": "AAC",
        "flac": "FLAC",
        "opus": "Opus",
        "vorbis": "Vorbis",
        "pcm_s16le": "PCM",
        "pcm_s24le": "PCM",
        "pcm_s32le": "PCM",
        "mp3": "MP3",
    }
    if c in aliases:
        return aliases[c]
    return c.replace("_", " ").upper()


def format_probe_audio_track_line(stream: dict[str, Any]) -> str:
    tags = _stream_tags(stream)
    lang = refiner_lang_display_or_blank(tags.get("language"))
    ch = int(stream.get("channels") or 0)
    ch_s = _channel_layout_label(ch)
    codec = _codec_label(str(stream.get("codec_name") or ""))
    parts = [p for p in (lang, ch_s, codec) if p]
    return " ".join(parts) if parts else "—"


def format_planned_audio_track_line(t: PlannedTrack) -> str:
    lang = refiner_lang_display_or_blank(t.lang_label)
    ch_s = _channel_layout_label(int(t.channels or 0))
    codec = _codec_label(t.codec_name)
    parts = [p for p in (lang, ch_s, codec) if p]
    return " ".join(parts) if parts else "—"


def join_track_lines(lines: list[str]) -> str:
    cleaned = [x.strip() for x in lines if (x or "").strip() and x.strip() != "—"]
    if not cleaned:
        return "—"
    return " · ".join(cleaned)


def audio_before_line_from_probe(audio_streams: list[dict[str, Any]]) -> str:
    return join_track_lines([format_probe_audio_track_line(s) for s in audio_streams])


def audio_after_line_from_plan(plan: RemuxPlan) -> str:
    lines = [format_planned_audio_track_line(t) for t in plan.audio if t.kind == "audio"]
    return join_track_lines(lines)


def subtitle_before_line_from_probe(subtitle_streams: list[dict[str, Any]]) -> str:
    bits: list[str] = []
    for s in subtitle_streams:
        tags = _stream_tags(s)
        lang = normalize_lang(tags.get("language") or "")
        bits.append(refiner_lang_display(lang) if lang else "Undetermined")
    if not bits:
        return "—"
    return " · ".join(bits)


def subtitle_after_line_from_plan(plan: RemuxPlan, *, remove_all: bool) -> str:
    if remove_all or not plan.subtitles:
        return "None"
    langs = [refiner_lang_display_or_blank(t.lang_label) for t in plan.subtitles if t.kind == "subtitle"]
    langs = [x for x in langs if x]
    if not langs:
        return "None"
    return " · ".join(langs)
