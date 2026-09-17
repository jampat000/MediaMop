"""Which of the operator's devices can play a file without the media server converting it (#467).

**Information only.** Nothing in this package may feed a processing decision. The media manager
already decided what the file should be when it grabbed it; MediaMop does what it is configured to
do and nothing more. If conforming files to devices is ever wanted, it is a separate, explicitly
configured feature — not this one quietly growing teeth (see #472).

The device list is data (``devices.json``), sourced from the manufacturers' published media
specifications and Jellyfin's client codec tables, each device naming its source. An operator can
replace it without a release by putting a copy at ``MEDIAMOP_HOME/direct-play-devices.json``.

The badge is computed from facts the processing pass already measured when it probed the file. It
never probes again.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any, Literal

logger = logging.getLogger(__name__)

OVERRIDE_FILE_NAME = "direct-play-devices.json"
Verdict = Literal["yes", "no", "maybe", "unknown"]

_AUDIO_LABELS = {
    "aac": "AAC",
    "ac3": "Dolby Digital",
    "eac3": "Dolby Digital Plus",
    "dts": "DTS",
    "truehd": "Dolby TrueHD",
    "flac": "FLAC",
    "opus": "Opus",
    "vorbis": "Vorbis",
    "mp3": "MP3",
    "alac": "Apple Lossless",
    "pcm": "PCM",
}
_VIDEO_LABELS = {"h264": "H.264", "hevc": "HEVC", "vp9": "VP9", "av1": "AV1", "mpeg4": "MPEG-4", "mpeg2video": "MPEG-2"}


@dataclass(frozen=True, slots=True)
class DeviceProfile:
    id: str
    name: str
    source: str
    note: str
    containers_yes: frozenset[str]
    containers_maybe: frozenset[str]
    video: dict[str, dict[str, Any]]
    video_maybe: dict[str, dict[str, Any]]
    audio_yes: frozenset[str]
    audio_maybe: frozenset[str]


@dataclass(frozen=True, slots=True)
class MediaFacts:
    """What the pass measured. ``None`` means not measured, and is never read as "no"."""

    container: str | None
    video_codec: str | None
    video_height: int | None
    video_bit_depth: int | None
    audio_codecs: tuple[str, ...] | None


@dataclass(frozen=True, slots=True)
class DirectPlayVerdict:
    device_id: str
    device_name: str
    verdict: Verdict
    reasons: tuple[str, ...] = field(default=())


def _profile(raw: dict[str, Any]) -> DeviceProfile:
    return DeviceProfile(
        id=str(raw["id"]),
        name=str(raw["name"]),
        source=str(raw.get("source") or ""),
        note=str(raw.get("note") or ""),
        containers_yes=frozenset(raw.get("containers", {}).get("yes", [])),
        containers_maybe=frozenset(raw.get("containers", {}).get("maybe", [])),
        video=dict(raw.get("video") or {}),
        video_maybe=dict(raw.get("video_maybe") or {}),
        audio_yes=frozenset(raw.get("audio", {}).get("yes", [])),
        audio_maybe=frozenset(raw.get("audio", {}).get("maybe", [])),
    )


def load_device_profiles(mediamop_home: str | None) -> tuple[DeviceProfile, ...]:
    """The operator's copy when there is a readable one, otherwise the shipped list."""

    if mediamop_home:
        override = Path(mediamop_home) / OVERRIDE_FILE_NAME
        if override.is_file():
            try:
                data = json.loads(override.read_text(encoding="utf-8"))
                return tuple(_profile(item) for item in data["devices"])
            except (OSError, ValueError, KeyError, TypeError):
                logger.warning("Ignoring %s: it is not a readable device list.", override, exc_info=True)
    text = resources.files(__package__).joinpath("devices.json").read_text(encoding="utf-8")
    return tuple(_profile(item) for item in json.loads(text)["devices"])


def _audio_family(codec: str) -> str:
    value = codec.strip().lower()
    return "pcm" if value.startswith("pcm_") else value


def container_for_path(relative_path: str) -> str | None:
    suffix = Path(relative_path).suffix.lower().lstrip(".")
    return suffix or None


def _video_fits(limits: dict[str, Any], facts: MediaFacts) -> tuple[bool, str | None]:
    max_height = limits.get("max_height")
    if max_height is not None and facts.video_height is not None and facts.video_height > int(max_height):
        return False, f"its {facts.video_height}p video is above {int(max_height)}p"
    max_depth = limits.get("max_bit_depth")
    if max_depth is not None and facts.video_bit_depth is not None and facts.video_bit_depth > int(max_depth):
        return False, f"its {facts.video_bit_depth}-bit video is above {int(max_depth)}-bit"
    containers = limits.get("containers")
    if containers and facts.container and facts.container not in containers:
        return False, f"it plays that video only in {', '.join(c.upper() for c in containers)}"
    return True, None


def evaluate(profile: DeviceProfile, facts: MediaFacts) -> DirectPlayVerdict:
    """One device's answer, with the reasons in words an operator can act on."""

    no: list[str] = []
    maybe: list[str] = []
    unknown = False

    if facts.container is None:
        unknown = True
    elif facts.container not in profile.containers_yes:
        (maybe if facts.container in profile.containers_maybe else no).append(f"{facts.container.upper()} files")

    codec = (facts.video_codec or "").strip().lower() or None
    label = _VIDEO_LABELS.get(codec or "", (codec or "").upper())
    if codec is None:
        unknown = True
    elif codec in profile.video:
        fits, why = _video_fits(profile.video[codec], facts)
        if not fits:
            if codec in profile.video_maybe and _video_fits(profile.video_maybe[codec], facts)[0]:
                maybe.append(f"{label} video ({why})")
            else:
                no.append(f"{label} video ({why})")
    elif codec in profile.video_maybe:
        fits, why = _video_fits(profile.video_maybe[codec], facts)
        (maybe if fits else no).append(f"{label} video" + (f" ({why})" if why else ""))
    else:
        no.append(f"{label} video")

    if facts.audio_codecs is None:
        unknown = True
    elif facts.audio_codecs:
        families = [_audio_family(c) for c in facts.audio_codecs]
        playable = [f for f in families if f in profile.audio_yes]
        partial = [f for f in families if f in profile.audio_maybe]
        unplayable = sorted({f for f in families if f not in profile.audio_yes and f not in profile.audio_maybe})
        names = ", ".join(_AUDIO_LABELS.get(f, f.upper()) for f in unplayable)
        if not playable and not partial:
            no.append(f"{names} audio")
        elif unplayable:
            # Another track can play, but the one a player picks might not.
            maybe.append(f"{names} audio on some tracks")
        elif partial and not playable:
            maybe.append(", ".join(_AUDIO_LABELS.get(f, f.upper()) for f in sorted(set(partial))) + " audio")

    if no:
        return DirectPlayVerdict(profile.id, profile.name, "no", tuple(f"cannot play {r}" for r in no))
    if maybe:
        return DirectPlayVerdict(profile.id, profile.name, "maybe", tuple(f"may not play {r}" for r in maybe))
    if unknown:
        return DirectPlayVerdict(profile.id, profile.name, "unknown", ("MediaMop has not measured this file yet",))
    return DirectPlayVerdict(profile.id, profile.name, "yes")
