"""Hardware acceleration: what this machine offers, and what to ask ffmpeg for.

Refiner always stream-copies, so decode is rarely on the critical path today and no
encoder is invoked at all. This is deliberately modest for that reason. It exists because
it is a **hard blocker** the moment anything encodes — HDR to SDR, scaling, re-encoding an
oversized file, subtitle burn-in — and none of those can ship without device selection.

Three ideas, in order of how much they matter:

**Detection is read-only and honest.** MediaMop reports what ffmpeg says it was built
with. It does not report what the machine *has*, because a working device and a compiled-in
method are different facts and conflating them would offer an operator a choice that
cannot work. The Windows tray package ships its own ffmpeg build, so the answer genuinely
differs by install.

**Per-vendor disables exist because auto-detection picks wrong.** FileFlows carries four
explicit disable elements for exactly this reason, and anything built here needs the same
escape hatch.

**Every choice degrades to software.** A device that is busy, absent, or wrong must never
fail a file. The fallback is recorded so the operator can see it happened rather than
wondering why a pass was slow.
"""

from __future__ import annotations

import logging
import re
import subprocess  # noqa: S404 - ffmpeg is invoked by design, with a fixed argv
from dataclasses import dataclass, field
from typing import Literal

logger = logging.getLogger(__name__)

HardwareDecodeMode = Literal["off", "auto", "device"]

#: The vendors an operator can switch off individually, and the ffmpeg hwaccel names each
#: covers. Grouped by vendor rather than by method because "disable NVIDIA" is the thing
#: someone actually wants to say.
VENDOR_METHODS: dict[str, tuple[str, ...]] = {
    "nvidia": ("cuda", "nvdec", "cuvid"),
    "intel": ("qsv", "d3d11va"),
    "amd": ("amf", "d3d11va"),
    "vaapi": ("vaapi",),
    "apple": ("videotoolbox",),
}

#: ffmpeg's own strictness values, narrowest first. ``normal`` is ffmpeg's default and
#: what MediaMop has always effectively used by not passing the flag.
STRICTNESS_LEVELS: tuple[str, ...] = ("very", "strict", "normal", "unofficial", "experimental")
DEFAULT_STRICTNESS = "normal"

_HWACCEL_TIMEOUT_SECONDS = 10.0


@dataclass(frozen=True, slots=True)
class AccelerationReport:
    """What ffmpeg on this machine says it can do."""

    #: Methods ffmpeg was compiled with. Not proof a device is present or working.
    available_methods: tuple[str, ...] = ()
    detected: bool = False
    #: Why detection produced nothing, when it did not.
    detail: str = ""

    @property
    def vendors(self) -> tuple[str, ...]:
        found = [
            vendor
            for vendor, methods in VENDOR_METHODS.items()
            if any(method in self.available_methods for method in methods)
        ]
        return tuple(sorted(found))


def detect_acceleration(ffmpeg_bin: str) -> AccelerationReport:
    """Ask ffmpeg what it was built with.

    Deliberately reports **compiled-in methods**, not working devices: those are different
    facts, and offering a choice that cannot work is worse than offering fewer choices.
    Never raises — a machine with no ffmpeg reports nothing available and says why.
    """

    try:
        completed = subprocess.run(  # noqa: S603 - fixed argv, no shell, no user input
            [ffmpeg_bin, "-hide_banner", "-hwaccels"],
            capture_output=True,
            text=True,
            timeout=_HWACCEL_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return AccelerationReport(
            detected=False,
            detail=f"MediaMop could not ask ffmpeg which acceleration methods it supports ({exc}).",
        )

    if completed.returncode != 0:
        return AccelerationReport(
            detected=False,
            detail=(
                "ffmpeg did not report its acceleration methods "
                f"(exit code {completed.returncode}). MediaMop will use software decoding."
            ),
        )

    methods: list[str] = []
    for raw in (completed.stdout or "").splitlines():
        line = raw.strip().lower()
        # The first line is a heading; anything with whitespace is prose, not a method.
        if not line or ":" in line or " " in line:
            continue
        if re.fullmatch(r"[a-z0-9_]+", line):
            methods.append(line)
    if not methods:
        return AccelerationReport(
            detected=True,
            detail="This ffmpeg build reports no hardware acceleration methods, so decoding is done in software.",
        )
    return AccelerationReport(
        available_methods=tuple(sorted(set(methods))),
        detected=True,
        detail=f"ffmpeg reports {len(methods)} acceleration method(s). Being listed does not prove a device is present.",
    )


@dataclass(frozen=True, slots=True)
class HardwareSettings:
    """What the library asked for."""

    mode: HardwareDecodeMode = "off"
    #: The named method when ``mode`` is ``device`` — ``cuda``, ``qsv``, ``vaapi``.
    device: str = ""
    disabled_vendors: tuple[str, ...] = ()
    strictness: str = DEFAULT_STRICTNESS

    @property
    def wants_hardware(self) -> bool:
        return self.mode in {"auto", "device"}


@dataclass(slots=True)
class AccelerationDecision:
    """What MediaMop will actually ask ffmpeg for, and why."""

    method: str = ""
    argv_flags: list[str] = field(default_factory=list)
    fell_back_to_software: bool = False
    reason: str = ""

    @property
    def using_hardware(self) -> bool:
        return bool(self.method)


def _vendor_of(method: str) -> str | None:
    for vendor, methods in VENDOR_METHODS.items():
        if method in methods:
            return vendor
    return None


def _allowed(method: str, disabled: tuple[str, ...]) -> bool:
    vendor = _vendor_of(method)
    return vendor is None or vendor not in disabled


def decide_acceleration(
    *,
    settings: HardwareSettings,
    report: AccelerationReport,
) -> AccelerationDecision:
    """Choose a decode method, falling back to software with a reason rather than failing.

    A device that is busy, absent or simply not compiled in must never fail a file. Every
    path here ends in a usable answer.
    """

    strict_flags = (
        ["-strict", settings.strictness] if settings.strictness and settings.strictness != DEFAULT_STRICTNESS else []
    )

    if not settings.wants_hardware:
        return AccelerationDecision(
            argv_flags=strict_flags,
            reason="Hardware decoding is switched off for this library, so MediaMop decoded in software.",
        )

    if not report.detected or not report.available_methods:
        return AccelerationDecision(
            argv_flags=strict_flags,
            fell_back_to_software=True,
            reason=(
                "MediaMop fell back to software decoding because this ffmpeg build reports no hardware "
                f"acceleration. {report.detail}".strip()
            ),
        )

    if settings.mode == "device":
        wanted = settings.device.strip().lower()
        if not wanted:
            return AccelerationDecision(
                argv_flags=strict_flags,
                fell_back_to_software=True,
                reason=(
                    "MediaMop fell back to software decoding because this library is set to use a named "
                    "device but no device name was given."
                ),
            )
        if wanted not in report.available_methods:
            return AccelerationDecision(
                argv_flags=strict_flags,
                fell_back_to_software=True,
                reason=(
                    f"MediaMop fell back to software decoding because the configured device '{wanted}' is not "
                    f"one this ffmpeg build supports. It offers: {', '.join(report.available_methods)}."
                ),
            )
        if not _allowed(wanted, settings.disabled_vendors):
            return AccelerationDecision(
                argv_flags=strict_flags,
                fell_back_to_software=True,
                reason=(
                    f"MediaMop fell back to software decoding because '{wanted}' belongs to a vendor this "
                    "library has switched off."
                ),
            )
        return AccelerationDecision(
            method=wanted,
            argv_flags=["-hwaccel", wanted, *strict_flags],
            reason=f"Decoding with '{wanted}', as configured for this library.",
        )

    # Auto. Preference order rather than ffmpeg's own, so the choice is predictable and
    # the same machine picks the same device every run.
    for candidate in ("cuda", "qsv", "vaapi", "videotoolbox", "d3d11va", "amf"):
        if candidate in report.available_methods and _allowed(candidate, settings.disabled_vendors):
            return AccelerationDecision(
                method=candidate,
                argv_flags=["-hwaccel", candidate, *strict_flags],
                reason=f"Chose '{candidate}' automatically from what this ffmpeg build offers.",
            )

    return AccelerationDecision(
        argv_flags=strict_flags,
        fell_back_to_software=True,
        reason=(
            "MediaMop fell back to software decoding because every acceleration method this ffmpeg build "
            "offers belongs to a vendor this library has switched off."
        ),
    )


def parse_disabled_vendors(csv: str | None) -> tuple[str, ...]:
    out: list[str] = []
    for raw in (csv or "").split(","):
        name = raw.strip().lower()
        if name in VENDOR_METHODS and name not in out:
            out.append(name)
    return tuple(out)


def normalize_strictness(raw: str | None) -> str:
    value = (raw or "").strip().lower()
    return value if value in STRICTNESS_LEVELS else DEFAULT_STRICTNESS


def normalize_decode_mode(raw: str | None) -> HardwareDecodeMode:
    value = (raw or "").strip().lower()
    return value if value in {"off", "auto", "device"} else "off"  # type: ignore[return-value]
