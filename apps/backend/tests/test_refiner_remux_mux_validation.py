"""Safety validation for staged Refiner output."""

from pathlib import Path
from subprocess import CompletedProcess
from typing import Any

import pytest

from mediamop.modules.refiner import refiner_remux_mux as mux


def _probe(*, duration: float, audio: int = 1) -> dict:
    return {
        "format": {"duration": str(duration)},
        "streams": [
            {"codec_type": "video", "duration": str(duration)},
            *({"codec_type": "audio", "duration": str(duration)} for _ in range(audio)),
        ],
    }


def test_staged_output_is_rejected_when_its_duration_is_only_a_partial_download(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    staged = tmp_path / "testament.mkv"
    staged.write_bytes(b"partial")
    monkeypatch.setattr(mux, "ffprobe_json", lambda *_args, **_kwargs: _probe(duration=212.546))

    with pytest.raises(mux.MediaCompletenessError, match=r"212\.5s of 5384\.0s expected"):
        mux.validate_remux_output(
            staged,
            mediamop_home=str(tmp_path),
            expected_audio=1,
            expected_duration_seconds=5384.046,
        )


def test_staged_output_accepts_normal_duration_rounding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    staged = tmp_path / "complete.mkv"
    staged.write_bytes(b"complete")
    monkeypatch.setattr(mux, "ffprobe_json", lambda *_args, **_kwargs: _probe(duration=5379.0))

    mux.validate_remux_output(
        staged,
        mediamop_home=str(tmp_path),
        expected_audio=1,
        expected_duration_seconds=5384.046,
    )


def test_source_integrity_validation_reads_primary_video_to_completion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "complete.mkv"
    source.write_bytes(b"complete")
    calls: list[list[str]] = []
    monkeypatch.setattr(mux, "resolve_ffprobe_ffmpeg", lambda **_kwargs: ("ffprobe", "ffmpeg"))

    def _run(argv: list[str], **_kwargs: Any) -> CompletedProcess[str]:
        calls.append(argv)
        return CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(mux.subprocess, "run", _run)

    mux.validate_media_integrity(source, mediamop_home=str(tmp_path))

    assert calls == [
        [
            "ffmpeg",
            "-hide_banner",
            "-v",
            "error",
            "-xerror",
            "-err_detect",
            "explode",
            "-i",
            str(source),
            "-map",
            "0:v:0",
            "-c",
            "copy",
            "-f",
            "null",
            "-",
        ]
    ]


def test_source_integrity_validation_rejects_incomplete_media(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "testament.mkv"
    source.write_bytes(b"partial")
    monkeypatch.setattr(mux, "resolve_ffprobe_ffmpeg", lambda **_kwargs: ("ffprobe", "ffmpeg"))
    monkeypatch.setattr(
        mux.subprocess,
        "run",
        lambda argv, **_kwargs: CompletedProcess(argv, 1, "", "Invalid data found when processing input"),
    )

    with pytest.raises(mux.MediaCompletenessError, match="Invalid data found when processing input"):
        mux.validate_media_integrity(source, mediamop_home=str(tmp_path))


def test_temp_output_is_deleted_when_duration_validation_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.mkv"
    source.write_bytes(b"source")
    plan = type("Plan", (), {"audio": [object()]})()
    monkeypatch.setattr(mux, "resolve_ffprobe_ffmpeg", lambda **_kwargs: ("ffprobe", "ffmpeg"))
    monkeypatch.setattr(mux, "build_ffmpeg_argv", lambda **_kwargs: ["ffmpeg", "output"])
    monkeypatch.setattr(mux, "run_ffmpeg", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        mux,
        "validate_remux_output",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(mux.MediaCompletenessError("incomplete")),
    )

    with pytest.raises(mux.MediaCompletenessError, match="incomplete"):
        mux.remux_to_temp_file(
            src=source,
            work_dir=tmp_path / "work",
            plan=plan,  # type: ignore[arg-type]
            mediamop_home=str(tmp_path),
            duration_seconds=100.0,
        )

    assert list((tmp_path / "work").iterdir()) == []


def test_progress_run_stops_absurd_projected_runtime_without_piping_stderr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeProcess:
        def __init__(self) -> None:
            self.stdout = iter(
                [
                    "out_time_ms=1000000\n",
                    "speed=0.006x\n",
                    "progress=continue\n",
                ]
            )
            self.killed = False

        def kill(self) -> None:
            self.killed = True

        def poll(self) -> int | None:
            return -9 if self.killed else None

        def wait(self, timeout: int) -> int:
            del timeout
            return -9 if self.killed else 0

    process = FakeProcess()
    popen_stderr: list[Any] = []

    def fake_popen(*_args: Any, **kwargs: Any) -> FakeProcess:
        popen_stderr.append(kwargs["stderr"])
        return process

    times = iter([0.0, 1.0, 2.0, 61.0])
    monkeypatch.setattr(mux.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(mux.time, "monotonic", lambda: next(times))

    with pytest.raises(RuntimeError, match="more than 12 hours remaining"):
        mux.run_ffmpeg(
            ["ffmpeg", "input.mpg", "output.mpg"],
            progress_callback=lambda _update: None,
            duration_seconds=72_500.0,
        )

    assert process.killed is True
    assert popen_stderr and popen_stderr[0] is not mux.subprocess.PIPE
