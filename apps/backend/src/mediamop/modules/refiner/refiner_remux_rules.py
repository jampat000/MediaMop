"""Remux planning rules — Refiner-owned (ported from Fetcher ``app/refiner_rules.py``).

MediaMop does not import Fetcher at runtime; behavior is copied here for ``refiner.file.remux_pass.v1``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

SubtitleMode = Literal["remove_all", "keep_selected"]
DefaultAudioSlot = Literal["primary", "secondary"]

# Stored in refiner_audio_preference_mode (max 24 chars).
AudioSelectionPolicy = Literal[
    "preferred_langs_quality",
    "preferred_langs_strict",
    "quality_all_languages",
]

# Best (index 0) → worst. Unknown / unlisted codecs sort after all of these.
_AUDIO_CODEC_QUALITY_ORDER: tuple[str, ...] = (
    "truehd",
    "dts_hd_ma",
    "flac",
    "alac",
    "pcm_s32le",
    "pcm_s24le",
    "pcm_s16le",
    "pcm_f32le",
    "pcm_u8",
    "wavpack",
    "opus",
    "libopus",
    "eac3",
    "ac3",
    "dca",
    "dts",
    "aac",
    "libfdk_aac",
    "mp2",
    "mp3",
    "vorbis",
    "libvorbis",
    "wmav2",
)

_CODEC_RANK_LOOKUP: dict[str, int] = {c: i for i, c in enumerate(_AUDIO_CODEC_QUALITY_ORDER)}
_CODEC_UNKNOWN_RANK = len(_AUDIO_CODEC_QUALITY_ORDER) + 32


def _audio_codec_quality_rank(codec_name: str | None) -> int:
    """Lower rank = better codec for ordering (ascending sort = best first)."""
    c = (codec_name or "").strip().lower()
    if not c:
        return _CODEC_UNKNOWN_RANK
    return _CODEC_RANK_LOOKUP.get(c, _CODEC_UNKNOWN_RANK)


def normalize_audio_preference_mode(raw: str | None) -> AudioSelectionPolicy:
    """Return canonical ``refiner_audio_preference_mode``; unknown stored values use the default policy."""
    m = (raw or "").strip().lower()
    if m in ("preferred_langs_quality", "preferred_langs_strict", "quality_all_languages"):
        return m  # type: ignore[return-value]
    return "preferred_langs_quality"


_MEDIA_EXTENSIONS = frozenset({".mkv", ".mp4", ".m4v", ".webm", ".avi"})

# Historical allowlist marker kept for candidate classification docs/tests; cleanup behavior
# now removes all direct-child files in the processed source folder after successful live runs.
REFINER_SOURCE_SIDECAR_CLEANUP_SUFFIXES: frozenset[str] = frozenset(
    {".par2", ".sfv", ".nzb", ".nfo"}
)


def is_refiner_media_candidate(path: Path) -> bool:
    """Return True only for supported video files Refiner may process.

    Paths under the watched tree that are *not* candidates—including Usenet/repair
    sidecars (``.par2``, ``.sfv``, ``.nzb``, ``.nfo``), subtitles, and other
    non-allowlisted files—are ignored for processing: no activity rows, readiness,
    ffprobe, or output copies. After a **successful** live job, remaining direct-child
    files in the same source folder are removed, then empty watched subfolders may be
    removed; failed jobs do not run that source-folder file cleanup.
    """
    try:
        return path.is_file() and path.suffix.lower() in _MEDIA_EXTENSIONS
    except OSError:
        return False


def normalize_lang(tag: str | None) -> str:
    if not tag:
        return ""
    s = tag.strip().lower()
    if not s:
        return ""
    m = re.match(r"^([a-z]{2,3})(?:-[a-z0-9]+)?$", s)
    if m:
        return m.group(1)
    return s[:12]


def parse_subtitle_langs_csv(raw: str) -> tuple[str, ...]:
    parts = [normalize_lang(p) for p in (raw or "").replace("\n", ",").split(",")]
    out: list[str] = []
    seen: set[str] = set()
    for p in parts:
        if p and p not in seen:
            seen.add(p)
            out.append(p)
    return tuple(out)


def _stream_tags(stream: dict[str, Any]) -> dict[str, str]:
    tags = stream.get("tags") or {}
    if not isinstance(tags, dict):
        return {}
    return {str(k): str(v) for k, v in tags.items()}


def _stream_disposition(stream: dict[str, Any]) -> dict[str, int]:
    disp = stream.get("disposition") or {}
    if not isinstance(disp, dict):
        return {}
    out: dict[str, int] = {}
    for k, v in disp.items():
        try:
            out[str(k)] = int(v)
        except (TypeError, ValueError):
            continue
    return out


def is_commentary_audio(stream: dict[str, Any]) -> bool:
    tags = _stream_tags(stream)
    title = (tags.get("title") or "").lower()
    if "commentary" in title:
        return True
    if tags.get("comment") and "commentary" in (tags.get("comment") or "").lower():
        return True
    return False


@dataclass(frozen=True)
class RefinerRulesConfig:
    primary_audio_lang: str
    secondary_audio_lang: str
    tertiary_audio_lang: str
    default_audio_slot: DefaultAudioSlot
    remove_commentary: bool
    subtitle_mode: SubtitleMode
    subtitle_langs: tuple[str, ...]
    preserve_forced_subs: bool
    preserve_default_subs: bool
    audio_preference_mode: AudioSelectionPolicy


def _ordered_preference_langs(config: RefinerRulesConfig) -> list[str]:
    out: list[str] = []
    for raw in (config.primary_audio_lang, config.secondary_audio_lang, config.tertiary_audio_lang):
        lg = normalize_lang(raw)
        if lg and lg not in out:
            out.append(lg)
    return out


@dataclass
class PlannedTrack:
    input_index: int
    lang_label: str
    commentary: bool = False
    forced: bool = False
    default: bool = False
    channels: int = 0
    lossless: bool = False
    bitrate: int = 0
    codec_rank: int = _CODEC_UNKNOWN_RANK
    codec_name: str = ""
    kind: Literal["audio", "subtitle"] = "audio"


@dataclass
class RemuxPlan:
    video_indices: list[int]
    audio: list[PlannedTrack]
    subtitles: list[PlannedTrack]
    removed_audio: list[str] = field(default_factory=list)
    removed_subtitles: list[str] = field(default_factory=list)
    default_audio_output_index: int = 0
    audio_selection_notes: list[str] = field(default_factory=list)


def is_remux_required(plan: RemuxPlan, audio_probe: list[dict[str, Any]], sub_probe: list[dict[str, Any]]) -> bool:
    if [t.input_index for t in plan.audio] != [int(s["index"]) for s in audio_probe]:
        return True
    if [t.input_index for t in plan.subtitles] != [int(s["index"]) for s in sub_probe]:
        return True
    old_audio_disp = [(int(s["index"]), int(_stream_disposition(s).get("default", 0))) for s in audio_probe]
    new_audio_disp = [(t.input_index, int(t.default)) for t in plan.audio]
    if old_audio_disp != new_audio_disp:
        return True
    old_sub = [
        (int(s["index"]), int(_stream_disposition(s).get("forced", 0)), int(_stream_disposition(s).get("default", 0)))
        for s in sub_probe
    ]
    new_sub = [(t.input_index, int(t.forced), int(t.default)) for t in plan.subtitles]
    if old_sub != new_sub:
        return True
    return False


def split_streams(probe: dict[str, Any]) -> tuple[list[dict], list[dict], list[dict]]:
    streams = probe.get("streams")
    if not isinstance(streams, list):
        return [], [], []
    video: list[dict] = []
    audio: list[dict] = []
    subs: list[dict] = []
    for s in streams:
        if not isinstance(s, dict):
            continue
        ct = (s.get("codec_type") or "").strip().lower()
        if ct == "video":
            video.append(s)
        elif ct == "audio":
            audio.append(s)
        elif ct == "subtitle":
            subs.append(s)
    video.sort(key=lambda x: int(x.get("index", 0)))
    audio.sort(key=lambda x: int(x.get("index", 0)))
    subs.sort(key=lambda x: int(x.get("index", 0)))
    return video, audio, subs


def _is_lossless_audio(codec_name: str | None) -> bool:
    c = (codec_name or "").strip().lower()
    return c in {"flac", "truehd", "alac", "pcm_s16le", "pcm_s24le", "pcm_s32le", "wavpack"}


@dataclass
class _AudioCandidate:
    input_index: int
    lang_label: str
    commentary: bool
    default: bool
    channels: int
    bitrate: int
    codec_rank: int
    codec_name: str


def _candidate_from_stream(s: dict[str, Any]) -> _AudioCandidate | None:
    tags = _stream_tags(s)
    idx = int(s["index"])
    lang_raw = tags.get("language") or ""
    lang = normalize_lang(lang_raw)
    disp = _stream_disposition(s)
    codec_name = str(s.get("codec_name") or "")
    ch = int(s.get("channels") or 0)
    br = int(s.get("bit_rate") or 0)
    return _AudioCandidate(
        input_index=idx,
        lang_label=lang,
        commentary=is_commentary_audio(s),
        default=bool(disp.get("default")),
        channels=ch,
        bitrate=br,
        codec_rank=_audio_codec_quality_rank(codec_name),
        codec_name=codec_name or "unknown",
    )


def _quality_sort_key(
    c: _AudioCandidate,
    *,
    fallback_preferred_penalty: int | None,
) -> tuple[int, ...]:
    """
    Ascending tuple order = better candidate first.
    commentary → channels → codec → bitrate → default (weak) → index.
    fallback_preferred_penalty: 0 if lang matches configured preference set, 1 otherwise (fallback pool only).
    """
    com = 1 if c.commentary else 0
    ch = int(c.channels) if c.channels and c.channels > 0 else 0
    ch_unknown = 1 if ch <= 0 else 0
    ch_score = -min(ch, 64) if ch > 0 else 0
    cr = int(c.codec_rank)
    br = int(c.bitrate) if c.bitrate and c.bitrate > 0 else 0
    br_unknown = 1 if br <= 0 else 0
    br_score = -min(br, 2_000_000_000) if br > 0 else 0
    default_weak = 0 if c.default else 1
    idx = int(c.input_index)
    fp = 0 if fallback_preferred_penalty is None else int(fallback_preferred_penalty)
    return (fp, com, ch_unknown, ch_score, cr, br_unknown, br_score, default_weak, idx)


def _pick_best(
    pool: list[_AudioCandidate],
    *,
    preferred_set: frozenset[str],
    use_fallback_penalty: bool,
) -> _AudioCandidate:
    def fp(c: _AudioCandidate) -> int | None:
        if not use_fallback_penalty:
            return None
        return 0 if (c.lang_label and c.lang_label in preferred_set) else 1

    return min(pool, key=lambda c: _quality_sort_key(c, fallback_preferred_penalty=fp(c)))


def _describe_candidate(c: _AudioCandidate) -> str:
    lang = c.lang_label or "unknown"
    ch = c.channels if c.channels and c.channels > 0 else None
    ch_s = f"{ch} ch" if ch else "unknown channels"
    return f"{lang} {c.codec_name} {ch_s} (stream {c.input_index})"


def _select_audio_winner(
    *,
    config: RefinerRulesConfig,
    candidates: list[_AudioCandidate],
    removed_by_commentary: list[str],
) -> tuple[_AudioCandidate | None, list[str], list[str]]:
    """Returns (winner or None, removed_audio lines, log notes)."""
    notes: list[str] = []
    removed_audio: list[str] = list(removed_by_commentary)
    policy = normalize_audio_preference_mode(config.audio_preference_mode)
    preferred_list = _ordered_preference_langs(config)
    preferred_set = frozenset(preferred_list)

    if not candidates:
        notes.append("No eligible audio tracks after commentary and probe rules.")
        return None, removed_audio, notes

    if policy == "quality_all_languages":
        w = _pick_best(candidates, preferred_set=preferred_set, use_fallback_penalty=False)
        notes.append(
            f"Selected {_describe_candidate(w)} using quality across all languages "
            f"(policy: quality across all languages)."
        )
        return w, removed_audio, notes

    if policy == "preferred_langs_strict":
        pl = normalize_lang(config.primary_audio_lang)
        if not pl:
            notes.append("Strict policy requires a primary language; none configured.")
            return None, removed_audio, notes
        pool = [c for c in candidates if c.lang_label == pl]
        if not pool:
            notes.append(
                f"No audio tracks matched primary language '{pl}' (strict policy — no fallback to secondary or other languages)."
            )
            return None, removed_audio, notes
        w = _pick_best(pool, preferred_set=preferred_set, use_fallback_penalty=False)
        notes.append(
            f"Selected {_describe_candidate(w)} using primary language only (strict policy)."
        )
        return w, removed_audio, notes

    # preferred_langs_quality — tier walk then fallback
    for tier_lang in preferred_list:
        pool = [c for c in candidates if c.lang_label == tier_lang]
        if not pool:
            continue
        w = _pick_best(pool, preferred_set=preferred_set, use_fallback_penalty=False)
        others = [c for c in pool if c.input_index != w.input_index]
        if others:
            otxt = "; ".join(_describe_candidate(x) for x in sorted(others, key=lambda x: x.input_index))
            notes.append(
                f"Selected {_describe_candidate(w)} over {otxt} within the same language tier (ranked by quality)."
            )
        else:
            notes.append(f"Selected {_describe_candidate(w)} as the only track in the first matching language tier.")
        return w, removed_audio, notes

    # Fallback: no configured language matched any track
    w = _pick_best(candidates, preferred_set=preferred_set, use_fallback_penalty=True)
    notes.append(
        f"Fell back to {_describe_candidate(w)} because no track matched configured language tiers "
        f"({', '.join(preferred_list) or 'none'}); ranked by quality with preferred-language matches first."
    )
    return w, removed_audio, notes


def plan_remux(
    *,
    video: list[dict[str, Any]],
    audio: list[dict[str, Any]],
    subtitles: list[dict[str, Any]],
    config: RefinerRulesConfig,
) -> RemuxPlan | None:
    """
    Single winning audio track + retention policy: all other audio streams removed from output.
    Returns None if no audio would remain.
    """
    video_indices = [int(s["index"]) for s in video]

    removed_audio: list[str] = []
    notes: list[str] = []
    candidates: list[_AudioCandidate] = []

    for s in audio:
        if not isinstance(s, dict):
            continue
        com = is_commentary_audio(s)
        if config.remove_commentary and com:
            tags = _stream_tags(s)
            lang_raw = normalize_lang(tags.get("language"))
            removed_audio.append(f"{lang_raw or 'und'} (commentary excluded — remove commentary enabled)")
            notes.append(
                f"Excluded commentary track (stream {int(s['index'])}) because remove commentary is enabled."
            )
            continue
        c = _candidate_from_stream(s)
        if c is None:
            continue
        candidates.append(c)

    policy = normalize_audio_preference_mode(config.audio_preference_mode)

    winner, removed_audio, sel_notes = _select_audio_winner(
        config=config,
        candidates=list(candidates),
        removed_by_commentary=removed_audio,
    )
    notes.extend(sel_notes)

    if winner is None:
        return None

    # Retention: one winner; mark every other audio stream as removed
    winner_idx = winner.input_index
    for c in candidates:
        if c.input_index != winner_idx:
            removed_audio.append(
                f"{_describe_candidate(c)}: removed (not selected — {_describe_candidate(winner)} kept)"
            )
            notes.append(
                f"Removed non-selected {_describe_candidate(c)} after selecting {_describe_candidate(winner)}."
            )

    if policy == "preferred_langs_quality":
        pls = _ordered_preference_langs(config)
        if len(pls) > 1 and winner.lang_label in pls:
            wi = pls.index(winner.lang_label)
            for c in candidates:
                if c.input_index == winner_idx:
                    continue
                if c.lang_label in pls and pls.index(c.lang_label) > wi:
                    notes.append(
                        f"Ignored {_describe_candidate(c)} because preferred languages (tiered quality) "
                        f"had candidates in '{winner.lang_label}' first."
                    )

    disp = {}
    for s in audio:
        if int(s.get("index", -1)) == winner_idx:
            disp = _stream_disposition(s)
            break
    codec_name = ""
    for s in audio:
        if int(s.get("index", -1)) == winner_idx:
            codec_name = str(s.get("codec_name") or "")
            break

    kept = PlannedTrack(
        input_index=winner_idx,
        lang_label=winner.lang_label,
        commentary=winner.commentary,
        forced=bool(disp.get("forced")),
        default=True,
        channels=winner.channels,
        lossless=_is_lossless_audio(codec_name),
        bitrate=winner.bitrate,
        codec_rank=winner.codec_rank,
        codec_name=codec_name,
        kind="audio",
    )

    # Subtitles (unchanged policy)
    kept_subs: list[PlannedTrack] = []
    removed_sub_labels: list[str] = []
    if config.subtitle_mode == "remove_all":
        for s in subtitles:
            tags = _stream_tags(s)
            removed_sub_labels.append(normalize_lang(tags.get("language")) or "und")
    else:
        sel = set(config.subtitle_langs)
        if not sel:
            for s in subtitles:
                tags = _stream_tags(s)
                removed_sub_labels.append(normalize_lang(tags.get("language")) or "und")
        else:
            for s in subtitles:
                tags = _stream_tags(s)
                idx = int(s["index"])
                lang = normalize_lang(tags.get("language"))
                disp_s = _stream_disposition(s)
                if not lang or lang not in sel:
                    removed_sub_labels.append(lang or "und")
                    continue
                t = PlannedTrack(
                    input_index=idx,
                    lang_label=lang,
                    forced=bool(disp_s.get("forced")),
                    default=bool(disp_s.get("default")),
                    kind="subtitle",
                )
                if not config.preserve_forced_subs:
                    t.forced = False
                if not config.preserve_default_subs:
                    t.default = False
                kept_subs.append(t)
            rank = {l: n for n, l in enumerate(config.subtitle_langs)}
            kept_subs.sort(key=lambda t: (rank.get(t.lang_label, 99), t.input_index))

    return RemuxPlan(
        video_indices=video_indices,
        audio=[kept],
        subtitles=kept_subs,
        removed_audio=removed_audio,
        removed_subtitles=removed_sub_labels,
        default_audio_output_index=0,
        audio_selection_notes=notes,
    )


def collect_media_files_under_path(path_str: str) -> list[str]:
    """Expand a path line to files (file itself or recursive media extensions under a directory)."""
    root = Path(path_str.strip()).expanduser()
    if not root.exists():
        return []
    if root.is_file():
        return [str(root.resolve())] if is_refiner_media_candidate(root) else []
    if not root.is_dir():
        return []
    out: list[str] = []
    try:
        for p in root.rglob("*"):
            if is_refiner_media_candidate(p):
                try:
                    out.append(str(p.resolve()))
                except OSError:
                    out.append(str(p))
    except OSError:
        return []
    out.sort()
    return out


def parse_path_lines(raw: str) -> list[str]:
    lines: list[str] = []
    for line in (raw or "").splitlines():
        s = line.strip()
        if s:
            lines.append(s)
    return lines
