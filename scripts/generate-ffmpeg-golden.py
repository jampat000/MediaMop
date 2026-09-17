"""Record what the Python ffmpeg/ffprobe layer does, so the .NET port can be held to it.

The .NET server (``apps/server``) ports ``refiner_remux_mux`` and ``refiner_hardware_acceleration`` to
``Weir.Core.Media`` (command lines, classification, validation, progress, hardware choice) and
``Weir.Infrastructure.Media`` (running the tools). This script drives the Python functions with their
process and filesystem calls replaced by recorded inputs, and writes each input with Python's answer to
``apps/server/tests/Weir.Core.Tests/Media/golden``. ``MediaGoldenParityTests`` requires the same answers:
the same argv token for token, the same exception type and message, the same log payloads.

Run with the backend's virtualenv. The script puts this checkout's ``apps/backend/src`` first on
``sys.path``, so an editable install elsewhere cannot shadow the code under test:

    apps/backend/.venv/Scripts/python.exe scripts/generate-ffmpeg-golden.py          # write
    apps/backend/.venv/Scripts/python.exe scripts/generate-ffmpeg-golden.py --check  # compare only
"""

from __future__ import annotations

import argparse
import importlib.util
import io
import json
import subprocess
import sys
import tempfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_SRC = REPO_ROOT / "apps" / "backend" / "src"
DEFAULT_OUTPUT = REPO_ROOT / "apps" / "server" / "tests" / "Weir.Core.Tests" / "Media" / "golden"

sys.path.insert(0, str(BACKEND_SRC))

from weir.refiner import refiner_hardware_acceleration as hw  # noqa: E402
from weir.refiner import refiner_remux_mux as mux  # noqa: E402
from weir.refiner.refiner_metadata_rules import MetadataRules  # noqa: E402
from weir.refiner.refiner_remux_rules import PlannedTrack, RemuxPlan  # noqa: E402


def _load_rules_golden() -> Any:
    """The rules golden generator, for its plan corpus and JSON shapes."""

    spec = importlib.util.spec_from_file_location(
        "generate_rules_golden", REPO_ROOT / "scripts" / "generate-rules-golden.py"
    )
    if spec is None or spec.loader is None:
        raise SystemExit("Could not load scripts/generate-rules-golden.py.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RULES = _load_rules_golden()


def _error(exc: BaseException) -> dict[str, Any]:
    return {"error": {"type": type(exc).__name__, "message": str(exc)}}


def _stable_path(text: str) -> str:
    """Paths must print the same on Windows and Linux, or --check would depend on the OS."""

    if str(Path(text)) != text:
        raise SystemExit(f"{text!r} prints as {str(Path(text))!r} on this OS; choose a path both OSes print as-is.")
    return text


# --- command lines -----------------------------------------------------------------------

SOURCES = [
    ("in.mkv", "out.mkv"),
    ("C:\\Media\\Film (2019)\\Film (2019).mkv", "C:\\Work\\Film (2019).refiner.abc123de.mkv"),
    ("Amélie (2001) [1080p].mp4", "Amélie (2001) [1080p].refiner.x.mp4"),
    ("Show - S01E01 - 'Pilot' \"cut\".m2ts", "D:\\tmp dir\\out file.m2ts"),
]

BINARIES = ["ffmpeg", "C:\\Program Files\\Weir\\bin\\ffmpeg\\ffmpeg.exe", "ffmpeg-x"]


def track(
    index: int, *, kind: str = "audio", default: bool = False, forced: bool = False, lang: str = "eng"
) -> PlannedTrack:
    return PlannedTrack(input_index=index, lang_label=lang, default=default, forced=forced, kind=kind)  # type: ignore[arg-type]


def sub(index: int, **kwargs: Any) -> PlannedTrack:
    return track(index, kind="subtitle", **kwargs)


def hand_plan(
    video: list[int],
    audio: list[PlannedTrack],
    subtitles: list[PlannedTrack] | None = None,
    **metadata: bool,
) -> RemuxPlan:
    return RemuxPlan(video_indices=video, audio=audio, subtitles=subtitles or [], metadata=MetadataRules(**metadata))


HAND_PLANS: list[tuple[str, RemuxPlan]] = [
    ("one-audio", hand_plan([0], [track(1, default=True)])),
    ("one-audio-not-default", hand_plan([0], [track(1)])),
    ("no-video", hand_plan([], [track(0, default=True)])),
    ("two-videos", hand_plan([0, 3], [track(1, default=True), track(2)])),
    ("reordered-audio", hand_plan([0], [track(4, default=True), track(2), track(3)])),
    ("subs-default-forced", hand_plan([0], [track(1, default=True)], [sub(2, default=True, forced=True)])),
    ("subs-forced-only", hand_plan([0], [track(1, default=True)], [sub(2, forced=True), sub(3)])),
    ("subs-default-only", hand_plan([0], [track(1)], [sub(5, default=True), sub(4)])),
    ("many-tracks", hand_plan([0], [track(i, default=i == 3) for i in range(1, 12)], [sub(i) for i in range(12, 24)])),
    ("remove-title", hand_plan([0], [track(1, default=True)], remove_title=True)),
    ("remove-other", hand_plan([0], [track(1, default=True)], remove_other_metadata=True)),
    ("remove-other-and-title", hand_plan([0], [track(1, default=True)], remove_other_metadata=True, remove_title=True)),
    ("remove-language-tags", hand_plan([0], [track(1, default=True)], remove_language_tags=True)),
    (
        "remove-everything",
        hand_plan(
            [0],
            [track(2, default=True)],
            [sub(3, forced=True)],
            remove_images=True,
            remove_attachments=True,
            remove_title=True,
            remove_language_tags=True,
            remove_other_metadata=True,
        ),
    ),
    ("title-and-language", hand_plan([0], [track(1)], [sub(2)], remove_title=True, remove_language_tags=True)),
    ("images-only-flag", hand_plan([0], [track(2)], remove_images=True, remove_attachments=True)),
    ("large-indices", hand_plan([10], [track(123, default=True)], [sub(4567)])),
]

INPUT_FLAG_SETS: list[list[str] | None] = [
    None,
    [],
    ["-hwaccel", "cuda"],
    ["-strict", "experimental"],
    ["-hwaccel", "qsv", "-strict", "unofficial"],
]


def plan_json(plan: RemuxPlan) -> dict[str, Any]:
    return RULES.plan_to_json(plan)


def argv_case(name: str, plan: RemuxPlan, bin_: str, src: str, dst: str, flags: list[str] | None) -> dict[str, Any]:
    argv = mux.build_ffmpeg_argv(
        ffmpeg_bin=bin_, src=Path(_stable_path(src)), dst=Path(_stable_path(dst)), plan=plan, input_flags=flags
    )
    return {
        "name": name,
        "input": {"ffmpeg_bin": bin_, "src": src, "dst": dst, "input_flags": flags, "plan": plan_json(plan)},
        "expected": {"argv": argv, "progress_argv": mux._argv_with_progress(argv)},
    }


def _has_int_indices(plan: RemuxPlan) -> bool:
    indices = [*plan.video_indices, *(t.input_index for t in plan.audio), *(t.input_index for t in plan.subtitles)]
    return all(type(i) is int for i in indices)


def run_argv_cases() -> dict[str, Any]:
    cases: list[dict[str, Any]] = []
    for i, (name, plan) in enumerate(HAND_PLANS):
        src, dst = SOURCES[i % len(SOURCES)]
        flags = INPUT_FLAG_SETS[i % len(INPUT_FLAG_SETS)]
        cases.append(argv_case(f"hand-{name}", plan, BINARIES[i % len(BINARIES)], src, dst, flags))
    # Every combination of input flags and paths on one plan, so placement before -i is pinned.
    for fi, flags in enumerate(INPUT_FLAG_SETS):
        for si, (src, dst) in enumerate(SOURCES):
            plan = HAND_PLANS[5][1]
            cases.append(
                argv_case(f"flags-{fi}-paths-{si}", plan, BINARIES[(fi + si) % len(BINARIES)], src, dst, flags)
            )
    # Every plan the rules corpus produces, as the remux pass would hand it over.
    for name, probe_data, config_data in RULES.PLAN_CASES:
        cfg = RULES.config_from_json(json.loads(json.dumps(config_data)))
        probe_json = json.loads(json.dumps(probe_data))
        try:
            video, audio, subs = RULES.split_streams(probe_json)
            plan = RULES.plan_remux(
                video=video, audio=audio, subtitles=subs, config=cfg, attachments=RULES.attachment_streams(probe_json)
            )
        except Exception:  # noqa: BLE001 - a corpus case that raises has no argv
            continue
        if plan is None or not _has_int_indices(plan):
            continue
        cases.append(argv_case(f"rules-{name}", plan, "ffmpeg", "in.mkv", "out.mkv", None))

    ffprobe_cases = []
    for bin_ in ["ffprobe", "C:\\Program Files\\Weir\\bin\\ffmpeg\\ffprobe.exe"]:
        for size, duration in [(10, 10), (25, 14), (9999, 0), (0, 301), (-5, -5), (1, 1), (1024, 300), (1025, 299)]:
            for src, _ in SOURCES[:2]:
                ffprobe_cases.append(
                    {
                        "input": {
                            "ffprobe_bin": bin_,
                            "src": src,
                            "probe_size_mb": size,
                            "analyze_duration_seconds": duration,
                        },
                        "expected": mux.build_ffprobe_argv(
                            ffprobe_bin=bin_,
                            src=Path(_stable_path(src)),
                            probe_size_mb=size,
                            analyze_duration_seconds=duration,
                        ),
                    }
                )

    integrity_cases = []
    for bin_ in BINARIES:
        for src, _ in SOURCES:
            captured: list[list[str]] = []

            def _run(argv: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
                captured.append(argv)  # noqa: B023 - consumed before the next iteration
                return subprocess.CompletedProcess(argv, 0, "", "")

            with (
                mock.patch.object(mux, "resolve_ffprobe_ffmpeg", lambda bin_=bin_, **_k: ("ffprobe", bin_)),
                mock.patch.object(mux.subprocess, "run", _run),
            ):
                mux.validate_media_integrity(Path(_stable_path(src)), weir_home="home")
            integrity_cases.append({"input": {"ffmpeg_bin": bin_, "path": src}, "expected": captured[0]})

    progress_argv_cases = [
        {"input": argv, "expected": mux._argv_with_progress(argv)}
        for argv in [[], ["ffmpeg"], ["ffmpeg", "out"], ["a", "b", "c"]]
    ]
    return {
        "remux": cases,
        "ffprobe": ffprobe_cases,
        "integrity": integrity_cases,
        "progress_argv": progress_argv_cases,
        "constants": {
            "REFINER_FFMPEG_TIMEOUT_S": mux.REFINER_FFMPEG_TIMEOUT_S,
            "REFINER_FFMPEG_SLOW_GRACE_S": mux.REFINER_FFMPEG_SLOW_GRACE_S,
            "REFINER_FFMPEG_MAX_PROJECTED_REMAINING_S": mux.REFINER_FFMPEG_MAX_PROJECTED_REMAINING_S,
            "_REFINER_FFPROBE_LOG_MAX_CHARS": mux._REFINER_FFPROBE_LOG_MAX_CHARS,
            "_REFINER_FFMPEG_STDERR_TAIL_BYTES": mux._REFINER_FFMPEG_STDERR_TAIL_BYTES,
            "_UNREADABLE_MEDIA_MARKERS": list(mux._UNREADABLE_MEDIA_MARKERS),
        },
    }


# --- ffprobe outcomes ----------------------------------------------------------------------

_PATH_TYPE = type(Path())


class FakePath(_PATH_TYPE):  # type: ignore[misc, valid-type]
    """A path whose filesystem answers are recorded, so logs and errors are the same on every machine."""

    exists_value = True
    is_file_value = True
    size = 1234
    mtime = 1700000000.25

    def exists(self) -> bool:  # type: ignore[override]
        return self.exists_value

    def is_file(self) -> bool:  # type: ignore[override]
        return self.is_file_value

    def stat(self) -> Any:  # type: ignore[override]
        return SimpleNamespace(st_size=self.size, st_mtime=self.mtime)

    def resolve(self, strict: bool = False) -> FakePath:  # type: ignore[override]
        return self


def fake_path(
    text: str, *, exists: bool = True, is_file: bool = True, size: int = 1234, mtime: float = 1700000000.25
) -> FakePath:
    path = FakePath(_stable_path(text))
    path.exists_value = exists
    path.is_file_value = is_file
    path.size = size
    path.mtime = mtime
    return path


@contextmanager
def captured_logs() -> Iterator[list[dict[str, str]]]:
    records: list[dict[str, str]] = []

    def _sink(level: str) -> Callable[..., None]:
        def _log(msg: str, *args: Any, **_kwargs: Any) -> None:
            records.append({"level": level, "message": msg % args if args else msg})

        return _log

    with (
        mock.patch.object(mux.logger, "debug", _sink("debug")),
        mock.patch.object(mux.logger, "warning", _sink("warning")),
    ):
        yield records


FFPROBE_RUNS: list[tuple[str, dict[str, Any]]] = [
    ("ok-streams", {"returncode": 0, "stdout": '{"streams":[]}', "stderr": ""}),
    (
        "ok-full",
        {
            "returncode": 0,
            "stdout": '{"streams": [{"index": 0, "codec_type": "video"}], "format": {"duration": "12.5"}}\n',
            "stderr": "",
        },
    ),
    ("ok-with-stderr-noise", {"returncode": 0, "stdout": '{"format": {}}', "stderr": "[mov] something harmless"}),
    ("ok-unicode", {"returncode": 0, "stdout": '{"format": {"tags": {"title": "Amélie \\u2014 ☃"}}}', "stderr": ""}),
    ("empty-stdout", {"returncode": 0, "stdout": "", "stderr": ""}),
    ("whitespace-stdout", {"returncode": 0, "stdout": " \n\t ", "stderr": ""}),
    ("list-stdout", {"returncode": 0, "stdout": "[]", "stderr": ""}),
    ("null-stdout", {"returncode": 0, "stdout": "null", "stderr": ""}),
    ("number-stdout", {"returncode": 0, "stdout": "42", "stderr": ""}),
    ("bad-json", {"returncode": 0, "stdout": "{bad", "stderr": ""}),
    ("truncated-json", {"returncode": 0, "stdout": '{"streams": [', "stderr": ""}),
    ("invalid-data", {"returncode": 1, "stdout": "", "stderr": "film.mkv: Invalid data found when processing input"}),
    ("ebml", {"returncode": 1, "stdout": "", "stderr": "EBML header parsing failed"}),
    ("moov", {"returncode": 1, "stdout": "", "stderr": "[mov,mp4,m4a] moov atom not found\nfilm.mp4: Invalid data"}),
    ("codec-params", {"returncode": 1, "stdout": "", "stderr": "Could not find codec parameters for stream 0"}),
    ("end-of-file", {"returncode": 1, "stdout": "", "stderr": "film.mkv: End of file"}),
    ("marker-upper-case", {"returncode": 1, "stdout": "", "stderr": "  INVALID DATA FOUND WHEN PROCESSING INPUT  \n"}),
    ("marker-in-stdout", {"returncode": 1, "stdout": "moov atom not found", "stderr": ""}),
    ("stderr-wins-over-stdout", {"returncode": 1, "stdout": "moov atom not found", "stderr": "Permission denied"}),
    ("permission-denied", {"returncode": 1, "stdout": "", "stderr": "film.mkv: Permission denied"}),
    ("no-such-file", {"returncode": 1, "stdout": "", "stderr": "film.mkv: No such file or directory"}),
    ("broken", {"returncode": 1, "stdout": "", "stderr": "broken"}),
    ("silent-failure", {"returncode": 1, "stdout": "", "stderr": ""}),
    ("whitespace-failure", {"returncode": 234, "stdout": "  ", "stderr": " \n "}),
    ("negative-exit", {"returncode": -11, "stdout": "", "stderr": "Segmentation fault"}),
    ("long-stderr", {"returncode": 1, "stdout": "", "stderr": "x" * 2100 + " end of file"}),
    ("long-stdout-ok", {"returncode": 0, "stdout": '{"format": {"comment": "' + "é" * 2500 + '"}}', "stderr": ""}),
    ("marker-split-by-newline", {"returncode": 1, "stdout": "", "stderr": "invalid data found\nwhen processing input"}),
    ("unicode-stderr", {"returncode": 1, "stdout": "", "stderr": "Fichier « film » : données invalides \ufffd"}),
    ("timeout", {"timeout": True}),
]

FFPROBE_PATHS: list[tuple[str, dict[str, Any]]] = [
    ("missing", {"exists": False, "is_file": False, "size": -1, "mtime": 0.0}),
    ("directory", {"exists": True, "is_file": False, "size": 0, "mtime": 1700000001.0}),
    ("empty", {"exists": True, "is_file": True, "size": 0, "mtime": 1700000002.5}),
]


def run_ffprobe_case(
    path_text: str, run: dict[str, Any], *, path_state: dict[str, Any] | None = None, **kwargs: Any
) -> dict[str, Any]:
    state = path_state or {}
    path = fake_path(path_text, **state)
    if not state.get("exists", True) or state.get("size") == -1:
        # stat() raising is how a missing file reaches size -1 and mtime 0.0.
        def _raise() -> Any:
            raise OSError("missing")

        path.stat = _raise  # type: ignore[method-assign]

    def _run(argv: list[str], **run_kwargs: Any) -> Any:
        if run.get("timeout"):
            raise subprocess.TimeoutExpired(argv, run_kwargs["timeout"])
        return SimpleNamespace(returncode=run["returncode"], stdout=run["stdout"], stderr=run["stderr"])

    with (
        captured_logs() as logs,
        mock.patch.object(mux, "resolve_ffprobe_ffmpeg", lambda **_k: ("ffprobe", "ffmpeg")),
        mock.patch.object(mux.subprocess, "run", _run),
    ):
        try:
            outcome: dict[str, Any] = {"result": mux.ffprobe_json(path, weir_home="home", **kwargs)}
        except Exception as exc:  # noqa: BLE001 - the exception is the recorded outcome
            outcome = _error(exc)
    return {**outcome, "logs": logs}


def run_ffprobe_outcomes() -> list[dict[str, Any]]:
    cases = []
    for name, run in FFPROBE_RUNS:
        cases.append(
            {
                "name": name,
                "input": {"path": "Film (2019).mkv", "run": run, "path_state": None, "kwargs": {}},
                "expected": run_ffprobe_case("Film (2019).mkv", run),
            }
        )
    for name, state in FFPROBE_PATHS:
        run = {"returncode": 0, "stdout": "{}", "stderr": ""}
        cases.append(
            {
                "name": f"path-{name}",
                "input": {"path": "C:\\Media\\gone.mkv", "run": run, "path_state": state, "kwargs": {}},
                "expected": run_ffprobe_case("C:\\Media\\gone.mkv", run, path_state=state),
            }
        )
    for name, kwargs in [
        ("controls", {"probe_size_mb": 64, "analyze_duration_seconds": 30}),
        ("controls-clamped", {"probe_size_mb": 5000, "analyze_duration_seconds": 0}),
        ("timeout-custom", {"timeout_s": 7}),
    ]:
        run = {"timeout": True} if name == "timeout-custom" else {"returncode": 0, "stdout": "{}", "stderr": ""}
        cases.append(
            {
                "name": name,
                "input": {"path": "a.b.c.mkv", "run": run, "path_state": None, "kwargs": kwargs},
                "expected": run_ffprobe_case("a.b.c.mkv", run, **kwargs),
            }
        )
    for suffix_name in [".hidden", "noext", "trailing.", "Movie.MKV", "a" * 70 + ".x" + "y" * 70]:
        run = {"returncode": 0, "stdout": "{}", "stderr": ""}
        cases.append(
            {
                "name": f"suffix-{suffix_name[:12]}",
                "input": {"path": suffix_name, "run": run, "path_state": None, "kwargs": {}},
                "expected": run_ffprobe_case(suffix_name, run),
            }
        )
    return cases


# --- validation ----------------------------------------------------------------------------


def _probe(duration: Any, audio: int = 1, **extra: Any) -> dict[str, Any]:
    return {
        "format": {"duration": duration},
        "streams": [
            {"codec_type": "video", "duration": duration},
            *({"codec_type": "audio", "duration": duration} for _ in range(audio)),
        ],
        **extra,
    }


VALIDATION_CASES: list[tuple[str, dict[str, Any], int, float | None]] = [
    ("partial-download", _probe("212.546"), 1, 5384.046),
    ("normal-rounding", _probe("5379.0"), 1, 5384.046),
    ("exactly-at-tolerance", _probe("5330.20554"), 1, 5384.046),
    ("just-below-tolerance", _probe("5330.2"), 1, 5384.046),
    ("short-file-five-second-floor", _probe("15.1"), 1, 20.0),
    ("short-file-too-short", _probe("14.9"), 1, 20.0),
    ("no-audio", _probe("100", audio=0), 0, None),
    ("one-audio-no-expectations", _probe("100"), 0, None),
    ("no-streams-key", {"format": {"duration": "10"}}, 0, None),
    ("streams-null", {"streams": None}, 0, None),
    ("streams-empty-dict", {"streams": {}}, 0, None),
    ("streams-dict", {"streams": {"0": {"codec_type": "audio"}}}, 0, None),
    ("streams-string", {"streams": "audio"}, 0, None),
    ("audio-count-matches", _probe("10", audio=2), 2, None),
    ("audio-count-mismatch", _probe("10", audio=3), 2, None),
    ("expected-audio-zero-ignores-count", _probe("10", audio=3), 0, None),
    ("audio-upper-case", {"streams": [{"codec_type": "AUDIO"}, {"codec_type": "Audio"}]}, 2, None),
    ("audio-non-dict-entries", {"streams": ["audio", 1, None, {"codec_type": "audio"}]}, 1, None),
    ("codec-type-null", {"streams": [{"codec_type": None}, {"codec_type": "audio"}]}, 0, None),
    ("codec-type-number", {"streams": [{"codec_type": 5}, {"codec_type": "audio"}]}, 0, None),
    ("codec-type-zero", {"streams": [{"codec_type": 0}, {"codec_type": "audio"}]}, 0, None),
    ("no-duration-anywhere", {"streams": [{"codec_type": "audio"}]}, 1, 100.0),
    ("duration-zero-expected-skips", _probe("1"), 1, 0.0),
    ("duration-negative-expected-skips", _probe("1"), 1, -5.0),
    ("duration-na", _probe("N/A"), 1, 100.0),
    ("duration-number", _probe(99.5), 1, 100.0),
    ("duration-int", _probe(96), 1, 100.0),
    ("duration-true", _probe(True), 1, 100.0),
    ("duration-list", _probe([1]), 1, 100.0),
    ("duration-nan-text", _probe("nan"), 1, 100.0),
    ("duration-inf-text", _probe("inf"), 1, 100.0),
    ("duration-negative", _probe("-50"), 1, 100.0),
    ("duration-with-spaces", _probe(" 98.0 "), 1, 100.0),
    ("duration-underscore", _probe("9_9.0"), 1, 100.0),
    (
        "stream-longer-than-format",
        {"format": {"duration": "10"}, "streams": [{"codec_type": "audio", "duration": "95.5"}]},
        1,
        100.0,
    ),
    ("format-not-dict", {"format": "x", "streams": [{"codec_type": "audio", "duration": "50"}]}, 1, 100.0),
    ("huge-expected", _probe("1e300"), 1, 1e308),
    ("rounding-half-even", _probe("0.25"), 1, 1000.25),
    ("rounding-half-even-2", _probe("0.35"), 1, 1000.45),
    ("big-int-duration", _probe(10**400), 1, 100.0),
]

DURATION_CASES: list[dict[str, Any]] = [
    {},
    {"format": None},
    {"format": {"duration": "0"}, "streams": [{"duration": "0.0"}]},
    {"format": {"duration": "12.5"}},
    {"streams": [{"duration": "3"}, "x", {"duration": "7"}, {"duration": "bad"}]},
    {"streams": "nope", "format": {"duration": "1.5"}},
    {"format": {"duration": 1e-9}},
    {"format": {"duration": "1e400"}},
    {"format": {"duration": False}, "streams": [{"duration": True}]},
    {"format": {"duration": {"a": 1}}, "streams": [{"duration": []}]},
]


def run_validation() -> dict[str, Any]:
    remux_cases = []
    for name, data, expected_audio, expected_duration in VALIDATION_CASES:
        with mock.patch.object(mux, "ffprobe_json", lambda *_a, data=data, **_k: json.loads(json.dumps(data))):
            try:
                mux.validate_remux_output(
                    Path("out.mkv"),
                    weir_home="home",
                    expected_audio=expected_audio,
                    expected_duration_seconds=expected_duration,
                )
                outcome: dict[str, Any] = {"ok": True}
            except Exception as exc:  # noqa: BLE001 - the exception is the recorded outcome
                outcome = _error(exc)
        remux_cases.append(
            {
                "name": name,
                "input": {
                    "probe": json.dumps(data),
                    "expected_audio": expected_audio,
                    "expected_duration_seconds": None if expected_duration is None else repr(expected_duration),
                },
                "expected": outcome,
            }
        )

    durations = []
    for data in DURATION_CASES:
        try:
            value = mux._probe_duration_seconds(json.loads(json.dumps(data)))
            outcome = {"result": None if value is None else repr(value)}
        except Exception as exc:  # noqa: BLE001
            outcome = _error(exc)
        durations.append({"input": json.dumps(data), "expected": outcome})

    integrity = []
    for rc, stderr in [
        (0, "ignored warning"),
        (1, "Invalid data found when processing input"),
        (1, ""),
        (1, "   \n"),
        (69, "  [matroska] Element at 0x1234 ending at 0x5678 exceeds containing master element\n"),
        (-9, "é" * 2001),
        (1, "x" * 2000),
        (1, "y" * 2001),
    ]:
        with (
            mock.patch.object(mux, "resolve_ffprobe_ffmpeg", lambda **_k: ("ffprobe", "ffmpeg")),
            mock.patch.object(
                mux.subprocess,
                "run",
                # Bound under names the real call does not pass: it passes stdout= and stderr= keywords.
                lambda argv, rc_=rc, err_=stderr, **_k: subprocess.CompletedProcess(argv, rc_, None, err_),
            ),
        ):
            try:
                mux.validate_media_integrity(Path("in.mkv"), weir_home="home")
                outcome = {"ok": True}
            except Exception as exc:  # noqa: BLE001
                outcome = _error(exc)
        integrity.append({"input": {"returncode": rc, "stderr": stderr}, "expected": outcome})

    return {"remux_output": remux_cases, "durations": durations, "integrity": integrity}


# --- running ffmpeg --------------------------------------------------------------------------


def run_quiet_ffmpeg_case(rc: int | None, stderr: bytes, timeout_s: int | None) -> dict[str, Any]:
    def _run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        kwargs["stderr"].write(stderr)
        if rc is None:
            raise subprocess.TimeoutExpired(argv, kwargs["timeout"])
        return subprocess.CompletedProcess(argv, rc)

    with mock.patch.object(mux.subprocess, "run", _run):
        try:
            if timeout_s is None:
                mux.run_ffmpeg(["ffmpeg", "-i", "in.mkv", "out.mkv"])
            else:
                mux.run_ffmpeg(["ffmpeg", "-i", "in.mkv", "out.mkv"], timeout_s=timeout_s)
            return {"ok": True}
        except Exception as exc:  # noqa: BLE001
            return _error(exc)


QUIET_RUNS: list[tuple[int | None, bytes, int | None]] = [
    (0, b"", None),
    (0, b"noise", None),
    (1, b"", None),
    (1, b"  \r\n", None),
    (1, b"Error while decoding stream #0:1: Invalid data found when processing input\r\n", None),
    (1, b"\xff\xfe broken \xc3\x28 utf8 \xe2\x82", None),
    (1, b"a" * 40000 + b"LAST LINE\n", None),
    (1, "é".encode() * 20000, None),
    (1, b"\x80" + b"z" * (32 * 1024 - 1), None),
    (None, b"", None),
    (None, b"", 25),
]


class _FakeProcess:
    def __init__(self, lines: list[str], rc: int, stderr: bytes, stderr_handle: Any) -> None:
        self.stdout = iter(lines)
        self.rc = rc
        self.killed = False
        stderr_handle.write(stderr)

    def kill(self) -> None:
        self.killed = True

    def poll(self) -> int | None:
        return -9 if self.killed else None

    def wait(self, timeout: int) -> int:
        del timeout
        return -9 if self.killed else self.rc


PROGRESS_RUNS: list[dict[str, Any]] = [
    {
        "name": "absurd-projection",
        "lines": ["out_time_ms=1000000\n", "speed=0.006x\n", "progress=continue\n"],
        "times": [0.0, 1.0, 2.0, 61.0],
        "duration": 72500.0,
    },
    {
        "name": "normal-run",
        "lines": [
            "frame=10\n",
            "out_time_ms=5000000\n",
            "speed=2.0x\n",
            "progress=continue\n",
            "out_time_ms=10000000\n",
            "speed=2.1x\n",
            "progress=continue\n",
            "out_time_ms=20000000\n",
            "progress=end\n",
        ],
        "times": [100.0, 100.5, 101.0, 101.5, 102.5, 103.0, 103.5, 105.0, 106.0, 106.5],
        "duration": 20.0,
    },
    {
        "name": "no-duration",
        "lines": ["out_time_ms=5000000\n", "progress=continue\n", "progress=end\n"],
        "times": [0.0, 1.0, 2.0, 3.0],
        "duration": None,
    },
    {
        "name": "zero-duration",
        "lines": ["out_time_ms=5000000\n", "progress=continue\n"],
        "times": [0.0, 1.0, 2.0],
        "duration": 0.0,
    },
    {
        "name": "na-out-time",
        "lines": ["out_time_ms=N/A\n", "speed=N/A\n", "progress=continue\n", "out_time_ms=\n", "progress=end\n"],
        "times": [0.0, 0.1, 0.2, 0.3, 0.4, 0.5],
        "duration": 60.0,
    },
    {
        "name": "missing-out-time",
        "lines": ["progress=continue\n"],
        "times": [0.0, 70.0],
        "duration": 60.0,
    },
    {
        "name": "overshoot-caps-at-99",
        "lines": ["out_time_ms=90000000\n", "progress=continue\n", "out_time_ms=-5\n", "progress=continue\n"],
        "times": [0.0, 1.0, 2.0, 3.0, 4.0],
        "duration": 60.0,
    },
    {
        "name": "noise-lines",
        "lines": [
            "\n",
            "   \n",
            "no equals here\n",
            "=empty key\n",
            "a=b=c\n",
            " progress = continue \n",
            "progress=continue\r\n",
        ],
        "times": [0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0],
        "duration": 10.0,
    },
    {
        "name": "timeout-on-line",
        "lines": ["out_time_ms=1\n", "progress=continue\n"],
        "times": [0.0, 1.0, 3601.5],
        "duration": 10.0,
    },
    {
        "name": "custom-timeout",
        "lines": ["out_time_ms=1\n", "progress=continue\n"],
        "times": [0.0, 5.0, 11.0],
        "duration": 10.0,
        "timeout_s": 10,
    },
    {
        "name": "no-timeout",
        "lines": ["out_time_ms=1000000\n", "progress=end\n"],
        "times": [0.0, 99999.0, 99999.5],
        "duration": 10.0,
        "timeout_s": None,
    },
    {
        "name": "clock-goes-backwards",
        "lines": ["out_time_ms=1000000\n", "progress=continue\n"],
        "times": [50.0, 49.0, 48.0],
        "duration": 10.0,
    },
    {
        "name": "slow-but-under-twelve-hours",
        "lines": ["out_time_ms=60000000\n", "progress=continue\n"],
        "times": [0.0, 60.0, 600.0],
        "duration": 3600.0,
    },
    {
        "name": "slow-before-grace",
        "lines": ["out_time_ms=1000\n", "progress=continue\n"],
        "times": [0.0, 10.0, 59.9],
        "duration": 72500.0,
    },
    {
        "name": "failed-exit-with-stderr",
        "lines": ["out_time_ms=1000000\n", "progress=continue\n"],
        "times": [0.0, 1.0, 2.0],
        "duration": 10.0,
        "rc": 1,
        "stderr": "Conversion failed!\r\n",
    },
    {
        "name": "failed-exit-silent",
        "lines": [],
        "times": [0.0],
        "duration": 10.0,
        "rc": 187,
        "stderr": "",
    },
    {
        "name": "end-without-duration-still-100",
        "lines": ["out_time_ms=123456789\n", "progress=end\n"],
        "times": [0.0, 1.0, 1.25],
        "duration": None,
    },
    {
        "name": "float-out-time",
        "lines": ["out_time_ms=1.5e6\n", "speed= 1.23x\n", "progress=continue\n"],
        "times": [0.0, 0.25, 0.5, 0.75],
        "duration": 3.0,
    },
    {
        "name": "inf-out-time",
        "lines": ["out_time_ms=inf\n", "progress=continue\n"],
        "times": [0.0, 1.0, 2.0],
        "duration": 3.0,
    },
    {
        "name": "nan-out-time",
        "lines": ["out_time_ms=nan\n", "progress=continue\n"],
        "times": [0.0, 1.0, 2.0],
        "duration": 3.0,
    },
    {
        "name": "zero-elapsed",
        "lines": ["out_time_ms=1000000\n", "progress=continue\n"],
        "times": [0.0, 0.0, 0.0],
        "duration": 10.0,
    },
]


def run_progress_case(case: dict[str, Any]) -> dict[str, Any]:
    updates: list[dict[str, Any]] = []
    processes: list[_FakeProcess] = []
    times = iter(case["times"])

    def _popen(_argv: list[str], **kwargs: Any) -> _FakeProcess:
        process = _FakeProcess(case["lines"], case.get("rc", 0), case.get("stderr", "").encode(), kwargs["stderr"])
        processes.append(process)
        return process

    kwargs: dict[str, Any] = {"progress_callback": updates.append, "duration_seconds": case["duration"]}
    if "timeout_s" in case:
        kwargs["timeout_s"] = case["timeout_s"]
    with (
        mock.patch.object(mux.subprocess, "Popen", _popen),
        mock.patch.object(mux.time, "monotonic", lambda: next(times)),
    ):
        try:
            mux.run_ffmpeg(["ffmpeg", "-i", "in.mkv", "out.mkv"], **kwargs)
            outcome: dict[str, Any] = {"ok": True}
        except Exception as exc:  # noqa: BLE001
            outcome = _error(exc)
    for update in updates:
        for key in ("percent", "processed_seconds"):
            if update[key] is not None:
                update[key] = repr(update[key])
    return {**outcome, "updates": updates, "killed": processes[0].killed}


# --- hardware ------------------------------------------------------------------------------

HWACCEL_OUTPUTS: list[tuple[str, dict[str, Any]]] = [
    ("typical", {"returncode": 0, "stdout": "Hardware acceleration methods:\ncuda\nvaapi\nqsv\n"}),
    (
        "windows-build",
        {
            "returncode": 0,
            "stdout": "Hardware acceleration methods:\r\ncuda\r\ndxva2\r\nqsv\r\nd3d11va\r\nopencl\r\nvulkan\r\nd3d12va\r\namf\r\n",
        },
    ),
    ("none", {"returncode": 0, "stdout": "Hardware acceleration methods:\n"}),
    ("empty", {"returncode": 0, "stdout": ""}),
    ("duplicates-and-case", {"returncode": 0, "stdout": "Hardware acceleration methods:\nCUDA\ncuda\n  VAAPI  \n\n"}),
    (
        "prose-and-symbols",
        {
            "returncode": 0,
            "stdout": "Hardware acceleration methods:\nnot a method\ncuda-x\nvideo_toolbox2\nqsv\tx\n\x0cvdpau\x0b",
        },
    ),
    ("videotoolbox", {"returncode": 0, "stdout": "Hardware acceleration methods:\nvideotoolbox\n"}),
    ("failed", {"returncode": 1, "stdout": ""}),
    ("negative-exit", {"returncode": -1073741515, "stdout": "cuda\n"}),
    ("oserror", {"raise": "oserror"}),
    ("timeout", {"raise": "timeout"}),
]


def run_detection(behaviour: dict[str, Any]) -> dict[str, Any]:
    argvs: list[list[str]] = []

    def _run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        argvs.append(argv)
        if behaviour.get("raise") == "oserror":
            raise OSError("no such file")
        if behaviour.get("raise") == "timeout":
            raise subprocess.TimeoutExpired(argv, kwargs["timeout"])
        return subprocess.CompletedProcess(argv, behaviour["returncode"], behaviour["stdout"], "")

    with mock.patch.object(hw.subprocess, "run", _run):
        report = hw.detect_acceleration("ffmpeg")
    return {"argv": argvs[0], "report": report_json(report)}


def report_json(report: hw.AccelerationReport) -> dict[str, Any]:
    return {
        "available_methods": list(report.available_methods),
        "detected": report.detected,
        "detail": report.detail,
        "vendors": list(report.vendors),
    }


REPORTS: list[tuple[str, hw.AccelerationReport]] = [
    (
        "none-detected",
        hw.AccelerationReport(detected=True, detail="This ffmpeg build reports no hardware acceleration."),
    ),
    ("undetected", hw.AccelerationReport(detected=False, detail="Weir could not ask ffmpeg.")),
    ("undetected-blank", hw.AccelerationReport(detected=False, detail="")),
    ("cuda", hw.AccelerationReport(available_methods=("cuda",), detected=True)),
    (
        "all",
        hw.AccelerationReport(
            available_methods=("amf", "cuda", "d3d11va", "qsv", "vaapi", "videotoolbox"), detected=True
        ),
    ),
    ("windows", hw.AccelerationReport(available_methods=("d3d11va", "dxva2", "qsv"), detected=True)),
    ("d3d11va-only", hw.AccelerationReport(available_methods=("d3d11va",), detected=True)),
    ("amf-vaapi", hw.AccelerationReport(available_methods=("amf", "vaapi"), detected=True)),
    ("unknown-only", hw.AccelerationReport(available_methods=("opencl", "vulkan"), detected=True)),
    ("methods-but-undetected", hw.AccelerationReport(available_methods=("cuda",), detected=False, detail="odd")),
]

SETTINGS: list[tuple[str, hw.HardwareSettings]] = [
    ("default", hw.HardwareSettings()),
    ("auto", hw.HardwareSettings(mode="auto")),
    ("auto-no-nvidia", hw.HardwareSettings(mode="auto", disabled_vendors=("nvidia",))),
    ("auto-no-intel-amd", hw.HardwareSettings(mode="auto", disabled_vendors=("intel", "amd"))),
    ("auto-all-off", hw.HardwareSettings(mode="auto", disabled_vendors=("nvidia", "intel", "amd", "vaapi", "apple"))),
    ("auto-experimental", hw.HardwareSettings(mode="auto", strictness="experimental")),
    ("device-cuda", hw.HardwareSettings(mode="device", device="cuda")),
    ("device-padded-upper", hw.HardwareSettings(mode="device", device="  QSV ")),
    ("device-blank", hw.HardwareSettings(mode="device", device="   ")),
    ("device-d3d11va-no-intel", hw.HardwareSettings(mode="device", device="d3d11va", disabled_vendors=("intel",))),
    ("device-d3d11va-no-amd", hw.HardwareSettings(mode="device", device="d3d11va", disabled_vendors=("amd",))),
    ("device-unknown-vendor", hw.HardwareSettings(mode="device", device="opencl", strictness="very")),
    ("off-strict", hw.HardwareSettings(mode="off", strictness="strict")),
    ("strictness-empty", hw.HardwareSettings(mode="auto", strictness="")),
    ("mode-unnormalized", hw.HardwareSettings(mode="Auto")),  # type: ignore[arg-type]
]


def run_hardware() -> dict[str, Any]:
    decisions = []
    for settings_name, settings in SETTINGS:
        for report_name, report in REPORTS:
            decision = hw.decide_acceleration(settings=settings, report=report)
            decisions.append(
                {
                    "name": f"{settings_name}/{report_name}",
                    "input": {
                        "settings": {
                            "mode": settings.mode,
                            "device": settings.device,
                            "disabled_vendors": list(settings.disabled_vendors),
                            "strictness": settings.strictness,
                            "wants_hardware": settings.wants_hardware,
                        },
                        "report": report_json(report),
                    },
                    "expected": {
                        "method": decision.method,
                        "argv_flags": decision.argv_flags,
                        "fell_back_to_software": decision.fell_back_to_software,
                        "reason": decision.reason,
                        "using_hardware": decision.using_hardware,
                    },
                }
            )
    text_inputs = [
        None,
        "",
        "nvidia",
        " NVIDIA , intel,nvidia,,amd ",
        "apple,vaapi,other",
        "Experimental",
        " strict ",
        "auto",
        "DEVICE",
        "on",
    ]
    return {
        "detection": [
            {"name": name, "input": behaviour, "expected": run_detection(behaviour)}
            for name, behaviour in HWACCEL_OUTPUTS
        ],
        "decisions": decisions,
        "parse_disabled_vendors": [
            {"input": raw, "expected": list(hw.parse_disabled_vendors(raw))} for raw in text_inputs
        ],
        "normalize_strictness": [{"input": raw, "expected": hw.normalize_strictness(raw)} for raw in text_inputs],
        "normalize_decode_mode": [{"input": raw, "expected": hw.normalize_decode_mode(raw)} for raw in text_inputs],
        "vendor_methods": [[vendor, list(methods)] for vendor, methods in hw.VENDOR_METHODS.items()],
        "strictness_levels": list(hw.STRICTNESS_LEVELS),
    }


# --- text ----------------------------------------------------------------------------------

BYTE_SAMPLES: list[bytes] = [
    b"",
    b"plain",
    b"  padded \r\n",
    b"a\r\nb\rc\nd\r\n\r\n",
    b"\r",
    b"\xff",
    b"\xc3\x28",
    b"\xe2\x82",
    b"\xe2\x82\xac\xf0\x9f\x98\x80",
    b"\xed\xa0\x80 surrogate",
    b"\xf4\x90\x80\x80 beyond",
    b"\xef\xbb\xbfbom",
    b"\x00nul\x0bvt\x0cff\x1cfs\x85",
    "Amélie ☃ \u2028 sep".encode(),
]


def lines_via_text_io(data: bytes) -> list[str]:
    wrapper = io.TextIOWrapper(io.BytesIO(data), encoding="utf-8", errors="replace")
    return [line[:-1] if line.endswith("\n") else line for line in wrapper]


def run_text() -> dict[str, Any]:
    decode = []
    with tempfile.TemporaryDirectory() as tmp:
        for i, data in enumerate(BYTE_SAMPLES):
            path = Path(tmp) / f"sample-{i}.bin"
            path.write_bytes(data)
            decode.append(
                {
                    "input": data.hex(),
                    "expected": {
                        "captured": subprocess.Popen._translate_newlines(None, data, "utf-8", "replace"),  # type: ignore[arg-type]
                        "tail": mux._read_tail_text(path),
                        "tail_4": mux._read_tail_text(path, max_bytes=4),
                        "tail_1": mux._read_tail_text(path, max_bytes=1),
                        "lines": lines_via_text_io(data),
                    },
                }
            )
    fixed_values = [
        0.0,
        -0.0,
        0.05,
        0.15,
        0.25,
        0.35,
        0.45,
        2.5,
        212.546,
        5384.046,
        5379.95,
        -0.04,
        1e22,
        1e-7,
        5e-324,
        float("inf"),
        float("-inf"),
        float("nan"),
        123456789.05,
        9.95,
    ]
    split_samples = ["", "a", "a\n", "a\r\nb\rc\x0bd\x0ce\x1cf\x1dg\x1eh\x85i\u2028j\u2029k", "\n\n", "x\ty z"]
    clip_samples = [("", 5), ("abcdef", 5), ("abcde", 5), ("é☃😀xyz", 3), ("😀" * 3, 2)]
    return {
        "decode": decode,
        "format_1f": [{"input": repr(v), "expected": f"{v:.1f}"} for v in fixed_values],
        "splitlines": [{"input": s, "expected": s.splitlines()} for s in split_samples],
        "clip": [{"input": [s, n], "expected": mux._clip_probe_text(s, max_chars=n)} for s, n in clip_samples],
        "timeout_messages": [
            {"input": {"argv": argv, "timeout": repr(t)}, "expected": str(subprocess.TimeoutExpired(argv, t))}
            for argv, t in [
                (["ffprobe", "-v", "quiet", "x's.mkv"], 120),
                (["ffmpeg", "-hwaccels"], 10.0),
                (["a\\b", 'say "hi"'], 5),
            ]
        ],
    }


# --- writing -------------------------------------------------------------------------------


def _render(data: Any) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def build_files() -> dict[str, str]:
    return {
        "argv.json": _render(run_argv_cases()),
        "ffprobe.json": _render(run_ffprobe_outcomes()),
        "validation.json": _render(run_validation()),
        "ffmpeg-run.json": _render(
            {
                "quiet": [
                    {
                        "input": {"returncode": rc, "stderr": stderr.hex(), "timeout_s": timeout_s},
                        "expected": run_quiet_ffmpeg_case(rc, stderr, timeout_s),
                    }
                    for rc, stderr, timeout_s in QUIET_RUNS
                ],
                "progress": [
                    {"name": case["name"], "input": case, "expected": run_progress_case(case)} for case in PROGRESS_RUNS
                ],
            }
        ),
        "hardware.json": _render(run_hardware()),
        "text.json": _render(run_text()),
    }


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
            print("Run scripts/generate-ffmpeg-golden.py to regenerate the golden files.", file=sys.stderr)
            return 1
        print(f"{len(files)} golden files in {output} match the Python ffmpeg layer.")
        return 0

    output.mkdir(parents=True, exist_ok=True)
    for stale in output.glob("*.json"):
        if stale.name not in files:
            stale.unlink()
    for name, content in files.items():
        (output / name).write_text(content, encoding="utf-8", newline="\n")
    argv_cases = json.loads(files["argv.json"])
    print(
        f"Wrote {len(files)} files to {output}: {len(argv_cases['remux'])} remux argv cases, "
        f"{len(argv_cases['ffprobe'])} ffprobe argv cases, {len(json.loads(files['ffprobe.json']))} ffprobe outcomes."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
