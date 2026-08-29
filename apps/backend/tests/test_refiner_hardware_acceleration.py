"""Hardware acceleration: detection, selection, and the fallback that must never fail a file.

Refiner always stream-copies, so this matters little today. It exists because device
selection is a hard blocker the moment anything encodes, and because auto-detection picks
the wrong device often enough that an escape hatch is not optional (#345).

The rule every test here is really checking: **a device that is busy, absent, or simply
not compiled in falls back to software with a reason, and never fails a file.**
"""

from __future__ import annotations

import subprocess
from unittest.mock import patch

from mediamop.modules.refiner.refiner_hardware_acceleration import (
    DEFAULT_STRICTNESS,
    STRICTNESS_LEVELS,
    VENDOR_METHODS,
    AccelerationReport,
    HardwareSettings,
    decide_acceleration,
    detect_acceleration,
    normalize_decode_mode,
    normalize_strictness,
    parse_disabled_vendors,
)


def _report(*methods: str) -> AccelerationReport:
    return AccelerationReport(available_methods=tuple(methods), detected=True, detail="")


# --- detection -----------------------------------------------------------------------


def _completed(stdout: str, returncode: int = 0) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=["ffmpeg"], returncode=returncode, stdout=stdout, stderr="")


def test_ffmpegs_reported_methods_are_parsed() -> None:
    output = "Hardware acceleration methods:\ncuda\nvaapi\nqsv\n"

    with patch("subprocess.run", return_value=_completed(output)):
        report = detect_acceleration("ffmpeg")

    assert report.detected is True
    assert set(report.available_methods) == {"cuda", "vaapi", "qsv"}
    assert set(report.vendors) == {"nvidia", "intel", "vaapi"}
    # Said plainly, because a compiled-in method and a working device are different facts.
    assert "does not prove a device is present" in report.detail


def test_a_build_with_no_acceleration_reports_none_and_says_so() -> None:
    with patch("subprocess.run", return_value=_completed("Hardware acceleration methods:\n")):
        report = detect_acceleration("ffmpeg")

    assert report.detected is True
    assert report.available_methods == ()
    assert "no hardware acceleration methods" in report.detail


def test_a_missing_ffmpeg_reports_nothing_rather_than_raising() -> None:
    """A machine with no ffmpeg must not take the endpoint or the pass down."""

    with patch("subprocess.run", side_effect=OSError("no such file")):
        report = detect_acceleration("ffmpeg")

    assert report.detected is False
    assert report.available_methods == ()
    assert "could not ask ffmpeg" in report.detail


def test_a_failing_ffmpeg_reports_nothing_rather_than_raising() -> None:
    with patch("subprocess.run", return_value=_completed("", returncode=1)):
        report = detect_acceleration("ffmpeg")

    assert report.detected is False
    assert "software decoding" in report.detail


def test_a_timeout_reports_nothing_rather_than_raising() -> None:
    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="ffmpeg", timeout=10)):
        report = detect_acceleration("ffmpeg")

    assert report.detected is False


# --- choosing ------------------------------------------------------------------------


def test_off_is_the_default_and_passes_no_flags() -> None:
    """Exactly what MediaMop does today by not passing the flags at all."""

    decision = decide_acceleration(settings=HardwareSettings(), report=_report("cuda"))

    assert decision.using_hardware is False
    assert decision.fell_back_to_software is False
    assert decision.argv_flags == []
    assert "switched off" in decision.reason


def test_auto_picks_a_method_and_names_it() -> None:
    decision = decide_acceleration(settings=HardwareSettings(mode="auto"), report=_report("vaapi", "cuda"))

    assert decision.method == "cuda"
    assert decision.argv_flags == ["-hwaccel", "cuda"]
    assert "automatically" in decision.reason


def test_auto_is_deterministic_so_the_same_machine_picks_the_same_device() -> None:
    """Not ffmpeg's own order: a predictable choice is worth more than a clever one."""

    report = _report("amf", "qsv", "cuda", "vaapi")

    first = decide_acceleration(settings=HardwareSettings(mode="auto"), report=report)
    second = decide_acceleration(settings=HardwareSettings(mode="auto"), report=report)

    assert first.method == second.method == "cuda"


def test_a_named_device_is_used_when_available() -> None:
    decision = decide_acceleration(
        settings=HardwareSettings(mode="device", device="qsv"), report=_report("cuda", "qsv")
    )

    assert decision.method == "qsv"
    assert decision.argv_flags == ["-hwaccel", "qsv"]


def test_strictness_is_passed_only_when_it_differs_from_ffmpegs_own_default() -> None:
    normal = decide_acceleration(settings=HardwareSettings(strictness="normal"), report=_report())
    experimental = decide_acceleration(settings=HardwareSettings(strictness="experimental"), report=_report())

    assert normal.argv_flags == []
    assert experimental.argv_flags == ["-strict", "experimental"]


# --- the fallback, which is the point ------------------------------------------------


def test_no_acceleration_available_falls_back_and_records_why() -> None:
    decision = decide_acceleration(
        settings=HardwareSettings(mode="auto"),
        report=AccelerationReport(detected=True, detail="This ffmpeg build reports no hardware acceleration."),
    )

    assert decision.using_hardware is False
    assert decision.fell_back_to_software is True
    assert "fell back to software" in decision.reason


def test_a_configured_device_that_is_missing_falls_back_and_lists_what_there_is() -> None:
    """The operator needs to know what to pick instead, not just that their choice failed."""

    decision = decide_acceleration(
        settings=HardwareSettings(mode="device", device="cuda"), report=_report("vaapi", "qsv")
    )

    assert decision.fell_back_to_software is True
    assert "'cuda' is not one this ffmpeg build supports" in decision.reason
    assert "vaapi" in decision.reason and "qsv" in decision.reason


def test_a_device_mode_with_no_device_named_falls_back() -> None:
    decision = decide_acceleration(settings=HardwareSettings(mode="device"), report=_report("cuda"))

    assert decision.fell_back_to_software is True
    assert "no device name was given" in decision.reason


def test_ffmpeg_being_unavailable_entirely_falls_back() -> None:
    decision = decide_acceleration(
        settings=HardwareSettings(mode="auto"),
        report=AccelerationReport(detected=False, detail="MediaMop could not ask ffmpeg."),
    )

    assert decision.fell_back_to_software is True


# --- the escape hatch ----------------------------------------------------------------


def test_a_disabled_vendor_is_skipped_by_auto() -> None:
    """The reason FileFlows ships four explicit disable elements: auto picks wrong."""

    decision = decide_acceleration(
        settings=HardwareSettings(mode="auto", disabled_vendors=("nvidia",)), report=_report("cuda", "vaapi")
    )

    assert decision.method == "vaapi"


def test_a_disabled_vendor_blocks_it_even_when_named_explicitly() -> None:
    decision = decide_acceleration(
        settings=HardwareSettings(mode="device", device="cuda", disabled_vendors=("nvidia",)),
        report=_report("cuda"),
    )

    assert decision.fell_back_to_software is True
    assert "switched off" in decision.reason


def test_disabling_every_available_vendor_falls_back_and_says_so() -> None:
    decision = decide_acceleration(
        settings=HardwareSettings(mode="auto", disabled_vendors=("nvidia", "intel", "amd", "vaapi", "apple")),
        report=_report("cuda", "qsv", "vaapi"),
    )

    assert decision.fell_back_to_software is True
    assert "every acceleration method" in decision.reason


# --- parsing -------------------------------------------------------------------------


def test_only_known_vendors_are_accepted() -> None:
    assert parse_disabled_vendors("nvidia, NOT_A_VENDOR ,intel,nvidia") == ("nvidia", "intel")
    assert parse_disabled_vendors("") == ()
    assert parse_disabled_vendors(None) == ()


def test_every_selectable_vendor_maps_to_at_least_one_method() -> None:
    for vendor, methods in VENDOR_METHODS.items():
        assert methods, vendor


def test_unknown_modes_and_strictness_fall_back_to_the_current_behaviour() -> None:
    assert normalize_decode_mode("something") == "off"
    assert normalize_decode_mode(None) == "off"
    assert normalize_strictness("something") == DEFAULT_STRICTNESS
    assert normalize_strictness(None) == DEFAULT_STRICTNESS
    for level in STRICTNESS_LEVELS:
        assert normalize_strictness(level) == level
