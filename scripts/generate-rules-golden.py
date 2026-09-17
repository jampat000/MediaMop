"""Record what the Python rules engine decides, so the .NET port can be held to it.

The .NET server (``apps/server``) ports Refiner's rules engine (``refiner_remux_rules``,
``refiner_track_sorters``, ``refiner_metadata_rules``, ``refiner_original_language`` and the
display helpers) to ``Weir.Core.Rules``. This script runs the Python engine over a corpus of
ffprobe-style inputs and rule configurations and writes each input together with Python's
answer to ``apps/server/tests/Weir.Core.Tests/Rules/golden``. ``GoldenParityTests`` loads every
file and asserts that the .NET engine gives exactly the same answer.

Run with the backend's virtualenv. The script puts this checkout's ``apps/backend/src`` first
on ``sys.path``, so an editable install elsewhere cannot shadow the code under test:

    apps/backend/.venv/Scripts/python.exe scripts/generate-rules-golden.py          # write
    apps/backend/.venv/Scripts/python.exe scripts/generate-rules-golden.py --check  # compare only

Outcomes that raise record the Python exception type instead of a result.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_SRC = REPO_ROOT / "apps" / "backend" / "src"
DEFAULT_OUTPUT = REPO_ROOT / "apps" / "server" / "tests" / "Weir.Core.Tests" / "Rules" / "golden"

sys.path.insert(0, str(BACKEND_SRC))

from weir.integrations.metadata.provider_port import (
    LookupResult,
    TitleMetadata,
)
from weir.refiner.refiner_metadata_rules import (
    MetadataRules,
    metadata_argv_flags,
)
from weir.refiner.refiner_original_language import (
    OriginalLanguageRules,
    canonical_language,
    parse_additional_languages,
    select_original_language_tracks,
)
from weir.refiner.refiner_remux_lang_display import (
    refiner_lang_display,
    refiner_lang_display_or_blank,
)
from weir.refiner.refiner_remux_rules import (
    PlannedTrack,
    RemuxPlan,
    _audio_codec_quality_rank,
    attachment_streams,
    default_refiner_remux_rules_config,
    is_remux_required,
    normalize_audio_preference_mode,
    normalize_lang,
    parse_path_lines,
    parse_subtitle_langs_csv,
    plan_remux,
    refiner_media_extensions_sorted,
    split_streams,
)
from weir.refiner.refiner_remux_track_display import (
    audio_after_line_from_plan,
    audio_before_line_from_probe,
    metadata_removed_line_from_plan,
    subtitle_after_line_from_plan,
    subtitle_before_line_from_probe,
)
from weir.refiner.refiner_track_sorters import (
    TrackSorterError,
    describe_sorters,
    dump_sorters,
    parse_sorters,
    preset_sorters,
    sort_key_for_track,
    validate_sorters,
)

# --- stream builders -------------------------------------------------------------------


def video(index: int = 0, codec: str = "h264", **extra: Any) -> dict[str, Any]:
    stream: dict[str, Any] = {
        "index": index,
        "codec_type": "video",
        "codec_name": codec,
        "width": 1920,
        "height": 1080,
        "avg_frame_rate": "24000/1001",
        "nb_frames": "150000",
        "disposition": {"default": 1, "attached_pic": 0},
    }
    stream.update(extra)
    return stream


def cover(index: int, *, attached_pic: bool = True, codec: str = "mjpeg", **extra: Any) -> dict[str, Any]:
    stream: dict[str, Any] = {
        "index": index,
        "codec_type": "video",
        "codec_name": codec,
        "width": 600,
        "height": 900,
        "avg_frame_rate": "0/0",
        "nb_frames": "1",
    }
    if attached_pic:
        stream["disposition"] = {"attached_pic": 1, "default": 0}
    stream.update(extra)
    return stream


def audio(
    index: int,
    lang: str | None = "eng",
    codec: str = "eac3",
    channels: Any = 6,
    bit_rate: Any = "640000",
    *,
    default: int = 0,
    title: str | None = None,
    **extra: Any,
) -> dict[str, Any]:
    stream: dict[str, Any] = {"index": index, "codec_type": "audio", "codec_name": codec}
    if channels is not None:
        stream["channels"] = channels
    if bit_rate is not None:
        stream["bit_rate"] = bit_rate
    tags: dict[str, Any] = {}
    if lang is not None:
        tags["language"] = lang
    if title is not None:
        tags["title"] = title
    if tags:
        stream["tags"] = tags
    stream["disposition"] = {"default": default, "forced": 0}
    stream.update(extra)
    return stream


def sub(
    index: int, lang: str | None = "eng", *, forced: int = 0, default: int = 0, codec: str = "subrip", **extra: Any
) -> dict[str, Any]:
    stream: dict[str, Any] = {"index": index, "codec_type": "subtitle", "codec_name": codec}
    if lang is not None:
        stream["tags"] = {"language": lang}
    stream["disposition"] = {"default": default, "forced": forced}
    stream.update(extra)
    return stream


def attachment(index: int, name: str | None = "Arial.ttf", **extra: Any) -> dict[str, Any]:
    stream: dict[str, Any] = {"index": index, "codec_type": "attachment", "codec_name": "ttf"}
    if name is not None:
        stream["tags"] = {"filename": name, "mimetype": "application/x-truetype-font"}
    stream.update(extra)
    return stream


def probe(*streams: Any, **extra: Any) -> dict[str, Any]:
    out: dict[str, Any] = {"streams": list(streams), "format": {"format_name": "matroska,webm"}}
    out.update(extra)
    return out


# --- configs ---------------------------------------------------------------------------


def config(**over: Any) -> dict[str, Any]:
    base = default_refiner_remux_rules_config()
    metadata = over.pop("metadata", {})
    cfg = replace(base, metadata=MetadataRules(**metadata), **over)
    return config_to_json(cfg)


def config_to_json(cfg: Any) -> dict[str, Any]:
    return {
        "primary_audio_lang": cfg.primary_audio_lang,
        "secondary_audio_lang": cfg.secondary_audio_lang,
        "tertiary_audio_lang": cfg.tertiary_audio_lang,
        "default_audio_slot": cfg.default_audio_slot,
        "remove_commentary": cfg.remove_commentary,
        "subtitle_mode": cfg.subtitle_mode,
        "subtitle_langs": list(cfg.subtitle_langs),
        "preserve_forced_subs": cfg.preserve_forced_subs,
        "preserve_default_subs": cfg.preserve_default_subs,
        "audio_preference_mode": cfg.audio_preference_mode,
        "audio_sorters_json": cfg.audio_sorters_json,
        "metadata": metadata_to_json(cfg.metadata),
        "preferred_audio_indices": list(cfg.preferred_audio_indices),
        "original_language_note": cfg.original_language_note,
    }


def config_from_json(data: dict[str, Any]) -> Any:
    return replace(
        default_refiner_remux_rules_config(),
        primary_audio_lang=data["primary_audio_lang"],
        secondary_audio_lang=data["secondary_audio_lang"],
        tertiary_audio_lang=data["tertiary_audio_lang"],
        default_audio_slot=data["default_audio_slot"],
        remove_commentary=data["remove_commentary"],
        subtitle_mode=data["subtitle_mode"],
        subtitle_langs=tuple(data["subtitle_langs"]),
        preserve_forced_subs=data["preserve_forced_subs"],
        preserve_default_subs=data["preserve_default_subs"],
        audio_preference_mode=data["audio_preference_mode"],
        audio_sorters_json=data["audio_sorters_json"],
        metadata=MetadataRules(**data["metadata"]),
        preferred_audio_indices=tuple(data["preferred_audio_indices"]),
        original_language_note=data["original_language_note"],
    )


def metadata_to_json(rules: MetadataRules) -> dict[str, bool]:
    return {
        "remove_images": rules.remove_images,
        "remove_attachments": rules.remove_attachments,
        "remove_title": rules.remove_title,
        "remove_language_tags": rules.remove_language_tags,
        "remove_other_metadata": rules.remove_other_metadata,
    }


def sorters_json(*entries: dict[str, Any]) -> str:
    return json.dumps(list(entries))


# --- outcomes --------------------------------------------------------------------------


def track_to_json(track: PlannedTrack) -> dict[str, Any]:
    return {
        "input_index": track.input_index,
        "lang_label": track.lang_label,
        "commentary": track.commentary,
        "forced": track.forced,
        "default": track.default,
        "channels": track.channels,
        "lossless": track.lossless,
        "bitrate": track.bitrate,
        "codec_rank": track.codec_rank,
        "codec_name": track.codec_name,
        "kind": track.kind,
    }


def plan_to_json(plan: RemuxPlan) -> dict[str, Any]:
    return {
        "video_indices": plan.video_indices,
        "audio": [track_to_json(t) for t in plan.audio],
        "subtitles": [track_to_json(t) for t in plan.subtitles],
        "removed_audio": plan.removed_audio,
        "removed_subtitles": plan.removed_subtitles,
        "default_audio_output_index": plan.default_audio_output_index,
        "audio_selection_notes": plan.audio_selection_notes,
        "removed_images": plan.removed_images,
        "removed_attachments": plan.removed_attachments,
        "metadata_notes": plan.metadata_notes,
        "metadata": metadata_to_json(plan.metadata),
    }


def run_plan_case(probe_data: dict[str, Any], config_data: dict[str, Any]) -> dict[str, Any]:
    """The same sequence the remux pass runs (``file_remux_pass/run.py``)."""

    cfg = config_from_json(config_data)
    try:
        video_streams, audio_streams, sub_streams = split_streams(probe_data)
        attachments = attachment_streams(probe_data)
        split = {
            "video": [s.get("index") for s in video_streams],
            "audio": [s.get("index") for s in audio_streams],
            "subtitles": [s.get("index") for s in sub_streams],
            "attachments": [s.get("index") for s in attachments],
        }
        plan = plan_remux(
            video=video_streams, audio=audio_streams, subtitles=sub_streams, config=cfg, attachments=attachments
        )
        if plan is None:
            return {"split": split, "plan": None}
        return {
            "split": split,
            "plan": plan_to_json(plan),
            "remux_required": is_remux_required(plan, audio_streams, sub_streams),
            "lines": {
                "audio_before": audio_before_line_from_probe(audio_streams),
                "audio_after": audio_after_line_from_plan(plan),
                "subtitle_before": subtitle_before_line_from_probe(sub_streams),
                "subtitle_after": subtitle_after_line_from_plan(plan, remove_all=cfg.subtitle_mode == "remove_all"),
                "metadata_removed": metadata_removed_line_from_plan(plan),
            },
            "metadata_argv": metadata_argv_flags(plan.metadata),
        }
    except Exception as exc:  # noqa: BLE001 - the exception type is the recorded outcome
        return {"error": type(exc).__name__}


# --- the corpus ------------------------------------------------------------------------

S_SIMPLE = probe(video(0), audio(1, "eng", default=1), sub(2, "eng"))
S_DUAL = probe(video(0), audio(1, "jpn", "flac", 2, "1500000", default=1), audio(2, "eng", "ac3", 6, "448000"))
S_TIER = probe(
    video(0),
    audio(1, "eng", "truehd", 8, "4000000", default=1),
    audio(2, "eng", "ac3", 6, "640000"),
    audio(3, "eng", "aac", 2, "128000", title="Director's Commentary"),
    audio(4, "fre", "dts", 6, "1509000"),
    sub(5, "eng"),
    sub(6, "fre", forced=1),
)
S_UNTAGGED = probe(video(0), audio(1, None, "ac3", 6, "448000"), audio(2, "und", "aac", 2, "128000"), sub(3, None))
S_NO_AUDIO = probe(video(0), sub(1, "eng"))
S_ONLY_COMMENTARY = probe(video(0), audio(1, "eng", "aac", 2, "128000", title="Commentary with cast"))
S_CHANNEL_TIE = probe(
    video(0),
    audio(1, "eng", "ac3", 6, "448000"),
    audio(2, "eng", "ac3", 6, "640000"),
    audio(3, "eng", "ac3", 6, "640000", default=1),
    audio(4, "eng", "ac3", 6, None),
)
S_ALL_EQUAL = probe(video(0), audio(3, "eng", "ac3", 6, "448000"), audio(1, "eng", "ac3", 6, "448000"))
S_LOSSLESS = probe(
    video(0),
    audio(1, "eng", "flac", 2, "900000"),
    audio(2, "eng", "eac3", 2, "640000"),
    audio(3, "eng", "pcm_s24le", 2, "2304000"),
    audio(4, "eng", "alac", 2, "1000000"),
)
S_LOSSLESS_VS_CHANNELS = probe(video(0), audio(1, "eng", "flac", 2, "900000"), audio(2, "eng", "eac3", 6, "640000"))
S_COVER = probe(video(0), cover(1), audio(2, "eng", default=1), attachment(3, "Arial.ttf"), attachment(4, None))
S_COVER_NO_DISPOSITION = probe(
    video(0), cover(1, attached_pic=False), cover(2, attached_pic=False, codec="png"), audio(3, "eng")
)
S_ONLY_IMAGES = probe(cover(0), cover(1, codec="png"), audio(2, "eng"))
S_MJPEG_VIDEO = probe(
    video(0, "mjpeg", avg_frame_rate="25/1", nb_frames="50000", disposition={"default": 1}), audio(1, "eng")
)
S_SUBS = probe(
    video(0),
    audio(1, "eng", default=1),
    sub(2, "fre", default=1),
    sub(3, "eng", forced=1),
    sub(4, "eng", default=1),
    sub(5, "jpn"),
    sub(6, None),
    sub(7, "en-US"),
    sub(8, "spa", forced=1, default=1),
)
S_WEIRD_VALUES = probe(
    {"index": "0", "codec_type": "Video ", "codec_name": "hevc"},
    {
        "index": "1",
        "codec_type": " AUDIO",
        "codec_name": "DTS",
        "channels": "6",
        "bit_rate": 1509000,
        "tags": {"language": "ENG", "title": None, "comment": "Commentary track"},
        "disposition": {"default": "1", "forced": "yes", "comment": None},
    },
    {
        "index": 2,
        "codec_type": "audio",
        "codec_name": "",
        "channels": 0,
        "tags": ["not", "a", "dict"],
        "disposition": "nope",
    },
    {
        "index": 3,
        "codec_type": "audio",
        "codec_name": "aac",
        "channels": 2.9,
        "bit_rate": True,
        "tags": {"language": None, "LANGUAGE": "fre", "title": 5},
        "disposition": {"default": 1.7},
    },
    {"index": 4, "codec_type": "subtitle", "tags": {"language": "EN-gb"}, "disposition": {"forced": "1"}},
    "not a stream",
    42,
    {"codec_type": "data"},
)
S_FRENCH_FILM = probe(
    video(0),
    audio(1, "eng", "eac3", 6, "640000", default=1),
    audio(2, "fra", "ac3", 6, "448000"),
    audio(3, "fre", "aac", 2, "128000", title="Commentaire / commentary"),
)
S_LONG_LANG = probe(
    video(0),
    audio(1, "english", "ac3", 6, "448000"),
    audio(2, "pt-BR", "aac", 2, "128000"),
    audio(3, "zh-Hans", "aac", 2, "128000"),
    audio(4, "a-very-long-language-tag", "aac", 2, "128000"),
    sub(5, "pt-br"),
    sub(6, "zh-Hans"),
)
S_UNKNOWN_CODECS = probe(
    video(0),
    audio(1, "eng", "atmos_whatever", 8, "0"),
    audio(2, "eng", "", 8, "0"),
    audio(3, "eng", "mp2", 8, "0"),
    audio(4, "eng", "wmav2", None, None),
)
S_UNSORTED_INDICES = probe(
    audio(5, "eng", "ac3", 2, "192000"), sub(4, "eng"), video(2), audio(1, "jpn", "aac", 2, "128000"), video(0)
)
S_EMPTY_STREAMS = {"streams": []}
S_NO_STREAMS_KEY = {"format": {"format_name": "mov"}}
S_STREAMS_NOT_LIST = {"streams": {"0": video(0)}}
S_BAD_BITRATE = probe(video(0), audio(1, "eng", "ac3", 6, "N/A"))
S_AUDIO_NO_INDEX = probe(video(0), {"codec_type": "audio", "codec_name": "ac3", "tags": {"language": "eng"}})
S_NULL_INDEX = probe(video(0), {"index": None, "codec_type": "audio"})
S_SUB_NO_INDEX = probe(video(0), audio(1, "eng"), {"codec_type": "subtitle", "tags": {"language": "fre"}})
S_MULTI_LANG = probe(
    video(0),
    audio(1, "ger", "dts", 8, "1509000"),
    audio(2, "spa", "ac3", 6, "448000"),
    audio(3, "jpn", "truehd", 8, "3000000"),
    audio(4, "eng", "aac", 2, "128000", title="Descriptive audio"),
    audio(5, "eng", "eac3", 6, "768000", default=1),
    audio(6, "ita", "opus", 2, "256000"),
)
S_ANIME = probe(
    video(0),
    audio(1, "jpn", "flac", 2, "1000000", default=1),
    audio(2, "eng", "eac3", 6, "640000"),
    sub(3, "eng", forced=1, codec="ass"),
    sub(4, "eng", default=1, codec="ass"),
    attachment(5, "font1.otf"),
    attachment(6, "font2.ttf"),
)
S_ALREADY_CLEAN = probe(video(0), audio(1, "eng", "eac3", 6, "640000", default=1), sub(2, "eng", forced=1))
S_DEFAULT_MOVES = probe(video(0), audio(1, "eng", "eac3", 6, "640000", default=0), sub(2, "eng", default=1))
S_COMMENTARY_COMMENT_TAG = probe(
    video(0),
    audio(1, "eng", "ac3", 6, "448000", tags={"language": "eng", "comment": "Audio COMMENTARY by director"}),
    audio(2, "eng", "aac", 2, "128000", tags={"language": "eng", "comment": ""}),
)
S_ATTACHMENT_TITLE = probe(
    video(0),
    audio(1, "eng"),
    attachment(2, None, tags={"title": " Cover font "}),
    attachment(3, None, tags="nope"),
    {"index": 4, "codec_type": "ATTACHMENT", "codec_name": "otf", "tags": {"filename": 7}},
)
S_IMAGE_EDGE = probe(
    video(0),
    {"index": 1, "codec_type": "video", "codec_name": "PNG", "nb_frames": "N/A", "avg_frame_rate": "25/1"},
    {"index": 2, "codec_type": "video", "codec_name": "gif", "nb_frames": "N/A", "avg_frame_rate": " 0/1 "},
    {"index": 3, "codec_type": "video", "codec_name": "webp", "width": 0, "height": 300},
    {"index": 4, "codec_type": "video", "codec_name": "h264", "disposition": {"attached_pic": "1"}},
    {"index": 5, "codec_type": "video", "codec_name": "bmp", "nb_frames": 0.5, "avg_frame_rate": "30/1"},
    audio(6, "eng"),
)
# Python's str()/repr()/int() on values ffprobe does not normally produce, so the .NET
# conversions are held to the same answers.
S_PY_VALUES = probe(
    {"index": 0, "codec_type": "video", "codec_name": "h264", "avg_frame_rate": "25/1"},
    {"index": 1, "codec_type": "video", "codec_name": "PNG", "nb_frames": " 1 ", "width": 600.0, "height": 1e20},
    {"index": 2, "codec_type": "video", "codec_name": "gif", "nb_frames": 2, "width": 1.5e-7, "height": -0.0001},
    {"index": 3, "codec_type": "video", "codec_name": " ", "nb_frames": 1, "width": 12, "height": 7},
    {
        "index": 4,
        "codec_type": "audio",
        "codec_name": "TrueHD ",
        "channels": "  8 ",
        "bit_rate": "4_000_000",
        "tags": {"language": 1.5, "title": ["Commentary"]},
        "disposition": {"default": 0.0, "forced": "0x1"},
    },
    {
        "index": 5,
        "codec_type": "audio",
        "codec_name": "flac",
        "channels": 1e3,
        "bit_rate": -5,
        "tags": {"language": True, "title": {"a": None, "b": [1, 2.5, "it's"]}},
        "disposition": {"default": True, "forced": "1"},
    },
    {
        "index": 6,
        "codec_type": "audio",
        "codec_name": "ac3",
        "channels": 6,
        "tags": {"language": chr(0xD1) + "ed", "title": "caf" + chr(0xE9)},
    },
    {
        "index": 7,
        "codec_type": "subtitle",
        "tags": {"language": "EN" + chr(0x2003)},
        "disposition": {"default": 2, "forced": -1},
    },
    {"index": 8, "codec_type": "attachment", "tags": {"filename": 3.0}},
    {"index": 9, "codec_type": "attachment", "tags": {"filename": "", "title": "\tquo'te\"s\t"}},
)
S_CODEC_TYPE_NOT_STRING = probe(video(0), {"index": 1, "codec_type": 5}, audio(2, "eng"))
S_CODEC_TYPE_FALSY_NUMBER = probe(video(0), {"index": 1, "codec_type": 0}, audio(2, "eng"))
S_ATTACHED_PIC_NOT_INT = probe(video(0), {"index": 1, "codec_type": "video", "disposition": {"attached_pic": "x"}})
S_INDEX_FLOAT = probe({"index": 0.0, "codec_type": "video"}, {"index": 1.9, "codec_type": "audio", "codec_name": "aac"})

SORTER_ENGLISH_THEN_51 = sorters_json({"field": "language", "value": "eng"}, {"field": "channels", "value": ">=5.1"})

ALL_METADATA = {
    "remove_images": True,
    "remove_attachments": True,
    "remove_title": True,
    "remove_language_tags": True,
    "remove_other_metadata": True,
}

FRENCH_NOTE = "Kept audio in the original language (fre) because the metadata provider identified it."

PLAN_CASES: list[tuple[str, dict[str, Any], dict[str, Any]]] = [
    ("simple-default", S_SIMPLE, config()),
    ("simple-keep-eng-subs", S_SIMPLE, config(subtitle_mode="keep_selected", subtitle_langs=("eng",))),
    ("simple-strict", S_SIMPLE, config(audio_preference_mode="preferred_langs_strict")),
    ("simple-all-languages", S_SIMPLE, config(audio_preference_mode="quality_all_languages")),
    ("simple-unknown-policy", S_SIMPLE, config(audio_preference_mode="Loudest-Please")),
    ("dual-default", S_DUAL, config()),
    ("dual-jpn-first", S_DUAL, config(primary_audio_lang="jpn", secondary_audio_lang="eng")),
    ("dual-strict-jpn", S_DUAL, config(primary_audio_lang="JPN", audio_preference_mode="preferred_langs_strict")),
    ("dual-strict-no-match", S_DUAL, config(primary_audio_lang="fre", audio_preference_mode="preferred_langs_strict")),
    ("dual-strict-no-primary", S_DUAL, config(primary_audio_lang="", audio_preference_mode="preferred_langs_strict")),
    ("dual-all-languages", S_DUAL, config(audio_preference_mode="quality_all_languages")),
    ("dual-fallback-no-tier", S_DUAL, config(primary_audio_lang="ger", secondary_audio_lang="spa")),
    ("dual-fallback-no-langs", S_DUAL, config(primary_audio_lang="", secondary_audio_lang="")),
    ("dual-same-lang-repeated", S_DUAL, config(primary_audio_lang="eng", secondary_audio_lang="en-US")),
    ("tier-default", S_TIER, config()),
    ("tier-keep-commentary", S_TIER, config(remove_commentary=False)),
    ("tier-fre-first", S_TIER, config(primary_audio_lang="fre", secondary_audio_lang="eng", tertiary_audio_lang="jpn")),
    ("tier-all-languages", S_TIER, config(audio_preference_mode="quality_all_languages", remove_commentary=False)),
    (
        "tier-subs-keep-all-stored-mode",
        S_TIER,
        config(subtitle_mode="keep_all", subtitle_langs=("fre", "eng")),
    ),
    ("tier-subs-empty-selection", S_TIER, config(subtitle_mode="keep_selected", subtitle_langs=())),
    (
        "tier-sorter-prefer-dts",
        S_TIER,
        config(primary_audio_lang="", audio_sorters_json=sorters_json({"field": "codec", "value": "dts"})),
    ),
    (
        "tier-sorter-prefer-51",
        S_TIER,
        config(audio_sorters_json=sorters_json({"field": "channels", "value": "=5.1"})),
    ),
    (
        "tier-sorter-smallest-bitrate",
        S_TIER,
        config(audio_sorters_json=sorters_json({"field": "bitrate", "reversed": True})),
    ),
    (
        "tier-sorter-commentary-first",
        S_TIER,
        config(remove_commentary=False, audio_sorters_json=sorters_json({"field": "commentary", "reversed": True})),
    ),
    ("tier-sorter-empty-list", S_TIER, config(audio_sorters_json="[]")),
    ("tier-sorter-garbage", S_TIER, config(audio_sorters_json="{not json")),
    (
        "tier-sorter-title-matches-codec-name",
        S_TIER,
        config(audio_sorters_json=sorters_json({"field": "title", "value": "ac3"})),
    ),
    ("untagged-default", S_UNTAGGED, config()),
    ("untagged-all-languages", S_UNTAGGED, config(audio_preference_mode="quality_all_languages")),
    ("untagged-strict", S_UNTAGGED, config(audio_preference_mode="preferred_langs_strict")),
    ("untagged-und-tier", S_UNTAGGED, config(primary_audio_lang="und")),
    ("untagged-keep-und-subs", S_UNTAGGED, config(subtitle_mode="keep_selected", subtitle_langs=("und", "eng"))),
    ("no-audio", S_NO_AUDIO, config()),
    ("no-audio-all-languages", S_NO_AUDIO, config(audio_preference_mode="quality_all_languages")),
    ("only-commentary-removed", S_ONLY_COMMENTARY, config()),
    ("only-commentary-kept", S_ONLY_COMMENTARY, config(remove_commentary=False)),
    ("channel-tie-bitrate", S_CHANNEL_TIE, config()),
    (
        "channel-tie-default-first",
        S_CHANNEL_TIE,
        config(audio_sorters_json=sorters_json({"field": "default"}, {"field": "bitrate"})),
    ),
    ("all-equal-index-tiebreak", S_ALL_EQUAL, config()),
    ("lossless-default", S_LOSSLESS, config()),
    (
        "lossless-sorter-codec-reversed",
        S_LOSSLESS,
        config(audio_sorters_json=sorters_json({"field": "codec", "reversed": True})),
    ),
    ("lossless-vs-channels", S_LOSSLESS_VS_CHANNELS, config()),
    (
        "lossless-vs-channels-codec-first",
        S_LOSSLESS_VS_CHANNELS,
        config(audio_sorters_json=sorters_json({"field": "codec"}, {"field": "channels"})),
    ),
    ("cover-default", S_COVER, config()),
    ("cover-remove-images", S_COVER, config(metadata={"remove_images": True})),
    ("cover-remove-attachments", S_COVER, config(metadata={"remove_attachments": True})),
    ("cover-remove-everything", S_COVER, config(metadata=ALL_METADATA)),
    ("cover-no-disposition-remove", S_COVER_NO_DISPOSITION, config(metadata={"remove_images": True})),
    ("only-images-remove", S_ONLY_IMAGES, config(metadata={"remove_images": True})),
    ("only-images-keep", S_ONLY_IMAGES, config()),
    ("mjpeg-video-remove-images", S_MJPEG_VIDEO, config(metadata={"remove_images": True})),
    ("image-edge-remove", S_IMAGE_EDGE, config(metadata={"remove_images": True})),
    ("metadata-title-only", S_ALREADY_CLEAN, config(metadata={"remove_title": True})),
    ("metadata-language-tags-only", S_ALREADY_CLEAN, config(metadata={"remove_language_tags": True})),
    ("metadata-other-only", S_ALREADY_CLEAN, config(metadata={"remove_other_metadata": True})),
    (
        "metadata-other-and-title",
        S_ALREADY_CLEAN,
        config(metadata={"remove_other_metadata": True, "remove_title": True}),
    ),
    ("attachments-described-by-title", S_ATTACHMENT_TITLE, config(metadata={"remove_attachments": True})),
    ("subs-keep-eng-fre", S_SUBS, config(subtitle_mode="keep_selected", subtitle_langs=("eng", "fre"))),
    (
        "subs-keep-no-forced-no-default",
        S_SUBS,
        config(
            subtitle_mode="keep_selected",
            subtitle_langs=("spa", "eng"),
            preserve_forced_subs=False,
            preserve_default_subs=False,
        ),
    ),
    (
        "subs-keep-forced-only",
        S_SUBS,
        config(subtitle_mode="keep_selected", subtitle_langs=("eng",), preserve_default_subs=False),
    ),
    (
        "subs-selection-not-normalized",
        S_SUBS,
        config(subtitle_mode="keep_selected", subtitle_langs=("ENG", "en-US", "jpn", "jpn")),
    ),
    ("subs-remove-all", S_SUBS, config(subtitle_mode="remove_all", subtitle_langs=("eng",))),
    ("already-clean-keep-subs", S_ALREADY_CLEAN, config(subtitle_mode="keep_selected", subtitle_langs=("eng",))),
    (
        "already-clean-drop-forced",
        S_ALREADY_CLEAN,
        config(subtitle_mode="keep_selected", subtitle_langs=("eng",), preserve_forced_subs=False),
    ),
    ("default-disposition-moves", S_DEFAULT_MOVES, config(subtitle_mode="keep_selected", subtitle_langs=("eng",))),
    ("weird-values-default", S_WEIRD_VALUES, config(subtitle_mode="keep_selected", subtitle_langs=("en",))),
    ("weird-values-keep-commentary", S_WEIRD_VALUES, config(remove_commentary=False)),
    ("weird-values-all-languages", S_WEIRD_VALUES, config(audio_preference_mode="quality_all_languages")),
    ("weird-values-none-tier", S_WEIRD_VALUES, config(primary_audio_lang="none", remove_commentary=False)),
    ("french-film-default", S_FRENCH_FILM, config()),
    (
        "french-film-original-language-hint",
        S_FRENCH_FILM,
        config(preferred_audio_indices=(2,), original_language_note=FRENCH_NOTE),
    ),
    (
        "french-film-hint-commentary-excluded",
        S_FRENCH_FILM,
        config(preferred_audio_indices=(3, 2), original_language_note=FRENCH_NOTE),
    ),
    (
        "french-film-hint-not-a-candidate",
        S_FRENCH_FILM,
        config(preferred_audio_indices=(9,), original_language_note="No audio track matched."),
    ),
    (
        "french-film-hint-beats-strict",
        S_FRENCH_FILM,
        config(audio_preference_mode="preferred_langs_strict", primary_audio_lang="jpn", preferred_audio_indices=(2,)),
    ),
    ("french-film-note-without-hint", S_FRENCH_FILM, config(original_language_note="Original-language did not apply.")),
    ("hint-with-no-audio", S_NO_AUDIO, config(preferred_audio_indices=(1,), original_language_note="n")),
    ("long-language-tags", S_LONG_LANG, config(subtitle_mode="keep_selected", subtitle_langs=("pt", "zh"))),
    ("long-language-tier-english", S_LONG_LANG, config(primary_audio_lang="english", secondary_audio_lang="PT-br")),
    ("unknown-codecs", S_UNKNOWN_CODECS, config()),
    (
        "unknown-codecs-codec-sorter",
        S_UNKNOWN_CODECS,
        config(audio_sorters_json=sorters_json({"field": "codec"}, {"field": "channels", "reversed": True})),
    ),
    ("unsorted-indices", S_UNSORTED_INDICES, config(subtitle_mode="keep_selected", subtitle_langs=("eng",))),
    ("empty-streams", S_EMPTY_STREAMS, config()),
    ("no-streams-key", S_NO_STREAMS_KEY, config()),
    ("streams-not-a-list", S_STREAMS_NOT_LIST, config()),
    ("error-bitrate-not-a-number", S_BAD_BITRATE, config()),
    ("error-audio-without-index", S_AUDIO_NO_INDEX, config()),
    ("error-null-index", S_NULL_INDEX, config()),
    ("error-subtitle-without-index", S_SUB_NO_INDEX, config(subtitle_mode="keep_selected", subtitle_langs=("eng",))),
    ("subtitle-without-index-remove-all", S_SUB_NO_INDEX, config()),
    ("multi-lang-default", S_MULTI_LANG, config()),
    ("multi-lang-tertiary", S_MULTI_LANG, config(primary_audio_lang="kor", secondary_audio_lang="", tertiary_audio_lang="spa")),
    ("multi-lang-all-languages", S_MULTI_LANG, config(audio_preference_mode="quality_all_languages")),
    (
        "multi-lang-filefloes-flow",
        S_MULTI_LANG,
        config(audio_preference_mode="quality_all_languages", audio_sorters_json=SORTER_ENGLISH_THEN_51),
    ),
    (
        "multi-lang-demote-descriptive",
        S_MULTI_LANG,
        config(
            audio_sorters_json=sorters_json(
                {"field": "title", "value": "descriptive", "reversed": True}, {"field": "bitrate", "reversed": True}
            )
        ),
    ),
    (
        "multi-lang-fallback-preferred-first",
        S_MULTI_LANG,
        config(primary_audio_lang="fre", secondary_audio_lang="kor", tertiary_audio_lang="ita"),
    ),
    ("anime-default", S_ANIME, config(subtitle_mode="keep_selected", subtitle_langs=("eng",))),
    (
        "anime-jpn-strip-fonts",
        S_ANIME,
        config(
            primary_audio_lang="jpn",
            secondary_audio_lang="eng",
            subtitle_mode="keep_selected",
            subtitle_langs=("eng",),
            metadata={"remove_attachments": True, "remove_title": True},
        ),
    ),
    ("commentary-in-comment-tag", S_COMMENTARY_COMMENT_TAG, config()),
    ("commentary-in-comment-tag-kept", S_COMMENTARY_COMMENT_TAG, config(remove_commentary=False)),
    (
        "python-values-everything-on",
        S_PY_VALUES,
        config(
            remove_commentary=False,
            primary_audio_lang="1.5",
            subtitle_mode="keep_selected",
            subtitle_langs=("en",),
            metadata=ALL_METADATA,
        ),
    ),
    (
        "python-values-all-languages",
        S_PY_VALUES,
        config(audio_preference_mode="quality_all_languages", metadata={"remove_images": True}),
    ),
    ("python-values-strict-true", S_PY_VALUES, config(primary_audio_lang="true", audio_preference_mode="preferred_langs_strict")),
    ("error-codec-type-not-a-string", S_CODEC_TYPE_NOT_STRING, config()),
    ("codec-type-falsy-number", S_CODEC_TYPE_FALSY_NUMBER, config()),
    ("error-attached-pic-not-an-int", S_ATTACHED_PIC_NOT_INT, config()),
    ("float-indices", S_INDEX_FLOAT, config()),
]

# --- sorters ---------------------------------------------------------------------------

SORTER_TRACKS: list[dict[str, Any]] = [
    {"index": 0, "language": "eng", "title": "English", "commentary": False, "default": True, "forced": False,
     "channels": 6, "bitrate": 640000, "codec": "eac3", "codec_rank": 12},
    {"index": 1, "language": "fre", "title": "Français 7.1", "commentary": False, "default": False, "forced": False,
     "channels": 8, "bitrate": 1509000, "codec": "dts", "codec_rank": 15},
    {"index": 2, "language": "eng", "title": "Commentary", "commentary": True, "default": False, "forced": True,
     "channels": 2, "bitrate": 128000, "codec": "aac", "codec_rank": 16},
    {"index": 3, "language": "", "title": "", "commentary": False, "default": False, "forced": False,
     "channels": 0, "bitrate": 0, "codec": "unknown", "codec_rank": 55},
    {"index": 4, "language": "jpn", "title": "Descriptive Audio", "commentary": False, "default": False,
     "forced": False, "channels": 1, "bitrate": 96000, "codec": "truehd", "codec_rank": 0},
    {"index": 5, "language": "eng", "title": "english", "commentary": False, "default": False, "forced": False,
     "channels": 6, "bitrate": 640000, "codec": "eac3", "codec_rank": 12},
]  # fmt: skip

SORTER_INPUTS: list[str | None] = [
    None,
    "",
    "   ",
    "not json",
    '"a string"',
    "[]",
    "[1, 2, 3]",
    "{{{",
    '{"field": "channels"}',
    '[{"field": "loudness"}]',
    '[{"field": "loudness"}, {"field": "channels"}]',
    '[{"field": " Channels "}, {"field": "BITRATE", "reversed": 1}]',
    '[{"field": 5}, {"field": null}, {"field": true}, "channels"]',
    '[{"field": "channels", "value": ">=5.1"}]',
    '[{"field": "channels", "value": "  <= 2.0 "}, {"field": "channels", "value": "stereo"}]',
    '[{"field": "channels", "value": "mono"}, {"field": "channels", "value": "!=7.1"}]',
    '[{"field": "channels", "value": "> 5 . 1"}, {"field": "channels", "value": "=abc"}]',
    '[{"field": "channels", "value": "<6"}, {"field": "channels", "value": "=1_0"}]',
    '[{"field": "bitrate", "value": ">=640k"}, {"field": "bitrate", "value": "<1_000_000"}]',
    '[{"field": "bitrate", "value": ">kk"}, {"field": "bitrate", "value": "=640000"}]',
    '[{"field": "bitrate", "value": ">1e5"}, {"field": "bitrate", "value": "!=nan"}]',
    '[{"field": "bitrate", "value": "<inf"}, {"field": "bitrate", "value": "=640.0k"}]',
    '[{"field": "default", "value": "true"}, {"field": "forced", "value": "!=yes"}]',
    '[{"field": "commentary", "value": "0"}, {"field": "commentary", "value": "on", "reversed": true}]',
    '[{"field": "language", "value": "ENG"}, {"field": "language", "value": "!=fre"}]',
    '[{"field": "title", "value": "descriptive", "reversed": true}]',
    '[{"field": "title", "value": "!=commentary"}]',
    '[{"field": "codec", "value": "dts"}, {"field": "codec", "value": "=EAC3"}]',
    '[{"field": "codec", "value": ""}, {"field": "codec", "value": "   "}, {"field": "codec", "value": 5}]',
    '[{"field": "title"}, {"field": "language", "reversed": true}]',
    '[{"field": "codec"}, {"field": "codec", "reversed": true}]',
    '[{"field": "channels"}, {"field": "bitrate", "reversed": true}]',
    '[{"field": "default"}, {"field": "forced", "reversed": true}, {"field": "commentary"}]',
    '[{"field": "commentary", "reversed": true}, {"field": "default", "reversed": "false"}]',
    '[{"field": "language", "value": "eng"}, {"field": "channels", "value": ">=5.1"}]',
    '[{"field": "title", "value": "=Français 7.1"}]',
    '[{"field": "bitrate", "value": "x"}, {"field": "title", "value": "o\'k"}]',
    '[{"field": "language", "value": "eng", "reversed": []}, {"field": "channels", "value": null}]',
    '[{"field": "channels", "reversed": {}}, {"field": "bitrate", "reversed": [0]}]',
    (
        '[{"field": "bitrate"}, {"field": "channels"}, {"field": "codec"}, {"field": "language"}, {"field": "title"},'
        ' {"field": "default"}, {"field": "forced"}, {"field": "commentary"}]'
    ),
    '[{"field": "codec\\u00e9"}]',
    '[{"field": "o\'k"}]',
    '[{"field": "title", "value": "caf\\u00e9 \\ud83c\\udfb5"}]',
]


def run_sorter_case(raw: str | None) -> dict[str, Any]:
    parsed = parse_sorters(raw)
    try:
        validated: dict[str, Any] = {"ok": validate_sorters(raw)}
    except TrackSorterError as exc:
        validated = {"error": str(exc)}
    keys = [list(sort_key_for_track(parsed, t)) for t in SORTER_TRACKS]
    ranked = sorted(SORTER_TRACKS, key=lambda t: sort_key_for_track(parsed, t))
    return {
        "parsed": dump_sorters(parsed),
        "described": describe_sorters(parsed),
        "validated": validated,
        "keys": keys,
        "ranking": [t["index"] for t in ranked],
    }


# --- original language -----------------------------------------------------------------


def lookup_to_json(lookup: LookupResult) -> dict[str, Any]:
    meta = lookup.metadata
    return {
        "status": lookup.status,
        "detail": lookup.detail,
        "metadata": None
        if meta is None
        else {
            "original_language": meta.original_language,
            "title": meta.title,
            "year": meta.year,
            "provider_id": meta.provider_id,
        },
    }


def matched(language: str) -> LookupResult:
    return LookupResult(
        status="matched", metadata=TitleMetadata(original_language=language, title="Film", year=2001), detail="matched"
    )


def tracks(*pairs: tuple[int, str]) -> list[dict[str, Any]]:
    return [{"index": i, "language": lang} for i, lang in pairs]


ON = OriginalLanguageRules(enabled=True)

ORIGINAL_LANGUAGE_CASES: list[tuple[str, OriginalLanguageRules, LookupResult, list[dict[str, Any]]]] = [
    ("original-wins", ON, matched("fr"), tracks((0, "eng"), (1, "fre"))),
    (
        "additional-languages",
        OriginalLanguageRules(enabled=True, additional_languages=("eng",)),
        matched("es"),
        tracks((0, "eng"), (1, "eng"), (2, "spa"), (3, "spa"), (4, "spa"), (5, "ger")),
    ),
    (
        "keep-every-track",
        OriginalLanguageRules(enabled=True, keep_only_first=False, additional_languages=("eng", "spa")),
        matched("es"),
        tracks((0, "spa"), (1, "spa"), (2, "eng"), (3, "ENG-us")),
    ),
    ("japanese-plus-english", OriginalLanguageRules(enabled=True, additional_languages=("eng",)), matched("ja"),
     tracks((0, "eng"), (1, "jpn"))),
    ("untagged-ignored", ON, matched("fr"), tracks((0, ""), (1, "eng"))),
    ("untagged-as-original", OriginalLanguageRules(enabled=True, treat_empty_as_original=True), matched("fr"),
     tracks((0, ""), (1, "eng"), (2, "fra"))),
    ("disabled", OriginalLanguageRules(enabled=False), matched("fr"), tracks((0, "eng"))),
    ("no-match", ON, LookupResult(status="no_match", detail="The metadata provider had no match for Film."),
     tracks((0, "eng"))),
    ("no-match-no-detail", ON, LookupResult(status="unreachable"), tracks((0, "eng"))),
    ("matched-without-metadata", ON, LookupResult(status="matched"), tracks((0, "eng"))),
    ("no-original-language", ON, LookupResult(status="matched", metadata=TitleMetadata(original_language="  ")),
     tracks((0, "eng"))),
    ("first-if-none", ON, matched("fr"), tracks((0, "eng"), (1, "ger"))),
    ("first-if-none-no-tracks", ON, matched("fr"), []),
    ("first-if-none-off", OriginalLanguageRules(enabled=True, first_if_none=False), matched("fr"), tracks((0, "eng"))),
    ("other-standard", ON, matched("fr"), tracks((0, "eng"), (1, "fra"))),
    ("unknown-code", OriginalLanguageRules(enabled=True, additional_languages=("qaa", "fre")), matched("qaa"),
     tracks((0, "qaa"), (1, "fre"), (2, "fr-CA"))),
    ("additional-includes-original", OriginalLanguageRules(enabled=True, additional_languages=("ger", "eng")),
     matched("de"), tracks((0, "eng"), (1, "deu"), (2, "ger"))),
]  # fmt: skip


def run_original_language_case(
    rules: OriginalLanguageRules, lookup: LookupResult, track_list: list[dict[str, Any]]
) -> dict[str, Any]:
    outcome = select_original_language_tracks(rules=rules, lookup=lookup, tracks=track_list)
    return {
        "input": {
            "rules": {
                "enabled": rules.enabled,
                "additional_languages": list(rules.additional_languages),
                "keep_only_first": rules.keep_only_first,
                "first_if_none": rules.first_if_none,
                "treat_empty_as_original": rules.treat_empty_as_original,
            },
            "lookup": lookup_to_json(lookup),
            "tracks": track_list,
        },
        "expected": {
            "preferred_indices": list(outcome.preferred_indices),
            "note": outcome.note,
            "chose": outcome.chose,
        },
    }


# --- languages and small helpers -------------------------------------------------------

LANGUAGE_INPUTS: list[str | None] = [
    None,
    "",
    "   ",
    "eng",
    "ENG",
    " en ",
    "en-US",
    "pt-BR",
    "zh-Hans",
    "zh_Hans",
    "und",
    "fre",
    "fra",
    "fr",
    "deu",
    "ger",
    "de",
    "zho",
    "chi",
    "nld",
    "dut",
    "ces",
    "ell",
    "ron",
    "isl",
    "vie",
    "msa",
    "qaa",
    "e",
    "english",
    "a-very-long-language-tag",
    "none",
    "x1",
    "éng",
    "en-",
    "en-us-x",
    "\teng\n",
]

CODEC_INPUTS: list[str | None] = [None, "", "truehd", "TrueHD", " flac ", "dts_hd_ma", "dca", "wmav2", "atmos"]

CSV_INPUTS: list[str] = ["", "eng", "eng,fre", " ENG , en-US,\nfre\n,,jpn, eng", "e,english,EN", "en, FR ,en, "]

POLICY_INPUTS: list[str | None] = [None, "", "preferred_langs_strict", " QUALITY_ALL_LANGUAGES ", "loudest"]

PATH_LINE_INPUTS: list[str] = ["", "  /a  \n\n b \r\n\tc", "one"]

PRESET_INPUTS: list[str | None] = [None, "", "preferred_langs_quality", " Quality_All_Languages ", "other"]


def run_helpers() -> dict[str, Any]:
    return {
        "languages": [
            {
                "input": raw,
                "normalize_lang": normalize_lang(raw),
                "canonical_language": canonical_language(raw),
                "display": refiner_lang_display(raw),
                "display_or_blank": refiner_lang_display_or_blank(raw),
            }
            for raw in LANGUAGE_INPUTS
        ],
        "codec_ranks": [{"input": raw, "rank": _audio_codec_quality_rank(raw)} for raw in CODEC_INPUTS],
        "subtitle_langs_csv": [{"input": raw, "output": list(parse_subtitle_langs_csv(raw))} for raw in CSV_INPUTS],
        "additional_languages_csv": [
            {"input": raw, "output": list(parse_additional_languages(raw))} for raw in CSV_INPUTS
        ],
        "audio_preference_modes": [
            {"input": raw, "output": normalize_audio_preference_mode(raw)} for raw in POLICY_INPUTS
        ],
        "path_lines": [{"input": raw, "output": parse_path_lines(raw)} for raw in PATH_LINE_INPUTS],
        "presets": [{"input": raw, "output": dump_sorters(preset_sorters(raw))} for raw in PRESET_INPUTS],
        "media_extensions": list(refiner_media_extensions_sorted()),
        "default_config": config_to_json(default_refiner_remux_rules_config()),
    }


# --- writing ---------------------------------------------------------------------------


def _render(data: Any) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def build_files() -> dict[str, str]:
    files: dict[str, str] = {}
    names: set[str] = set()
    for name, probe_data, config_data in PLAN_CASES:
        if name in names:
            raise SystemExit(f"Duplicate case name {name!r}.")
        names.add(name)
        # Round-trip through JSON so Python sees exactly what the .NET test will parse.
        probe_json = json.loads(json.dumps(probe_data))
        config_json = json.loads(json.dumps(config_data))
        files[f"plan-{name}.json"] = _render(
            {
                "name": name,
                "input": {"probe": probe_json, "config": config_json},
                "expected": run_plan_case(json.loads(json.dumps(probe_json)), config_json),
            }
        )
    files["sorters.json"] = _render(
        {
            "tracks": SORTER_TRACKS,
            "cases": [{"input": raw, "expected": run_sorter_case(raw)} for raw in SORTER_INPUTS],
        }
    )
    files["original-language.json"] = _render(
        [{"name": name, **run_original_language_case(*rest)} for name, *rest in ORIGINAL_LANGUAGE_CASES]
    )
    files["helpers.json"] = _render(run_helpers())
    return files


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true", help="fail if the checked-in golden files are out of date")
    args = parser.parse_args()

    import weir

    expected_root = BACKEND_SRC.resolve()
    if expected_root not in Path(weir.__file__).resolve().parents:
        raise SystemExit(f"weir was imported from {weir.__file__}, not from {expected_root}.")

    files = build_files()
    output: Path = args.output

    if args.check:
        on_disk = {p.name: p for p in output.glob("*.json")} if output.is_dir() else {}
        problems: list[str] = []
        for name, content in sorted(files.items()):
            path = on_disk.get(name)
            if path is None:
                problems.append(f"missing: {name}")
            elif path.read_text(encoding="utf-8").replace("\r\n", "\n") != content:
                problems.append(f"out of date: {name}")
        problems.extend(f"not generated: {name}" for name in sorted(set(on_disk) - set(files)))
        if problems:
            for problem in problems:
                print(problem, file=sys.stderr)
            print("Run scripts/generate-rules-golden.py to regenerate the golden files.", file=sys.stderr)
            return 1
        print(f"{len(files)} golden files in {output} match the Python rules engine.")
        return 0

    output.mkdir(parents=True, exist_ok=True)
    for stale in output.glob("*.json"):
        if stale.name not in files:
            stale.unlink()
    for name, content in files.items():
        (output / name).write_text(content, encoding="utf-8", newline="\n")
    plan_cases = sum(1 for name in files if name.startswith("plan-"))
    print(f"Wrote {len(files)} files ({plan_cases} plan cases) to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
