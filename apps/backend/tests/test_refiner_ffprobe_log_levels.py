from pathlib import Path
from types import SimpleNamespace

import pytest

from mediamop.modules.refiner import refiner_remux_mux


def test_ffprobe_success_diagnostics_are_debug_not_warning(tmp_path: Path, monkeypatch) -> None:
    media = tmp_path / "movie.mkv"
    media.write_bytes(b"not-empty")
    debug_messages: list[str] = []
    warning_messages: list[str] = []
    monkeypatch.setattr(refiner_remux_mux, "resolve_ffprobe_ffmpeg", lambda *, mediamop_home: ("ffprobe", "ffmpeg"))
    monkeypatch.setattr(refiner_remux_mux.logger, "debug", lambda msg, *args, **kwargs: debug_messages.append(msg % args))
    monkeypatch.setattr(refiner_remux_mux.logger, "warning", lambda msg, *args, **kwargs: warning_messages.append(msg % args))
    monkeypatch.setattr(
        refiner_remux_mux.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout='{"streams":[]}', stderr=""),
    )

    refiner_remux_mux.ffprobe_json(media, mediamop_home=str(tmp_path))

    assert not any("REFINER_FFPROBE" in message for message in warning_messages)
    assert any("REFINER_FFPROBE_FILE_STATE" in message for message in debug_messages)
    assert any("REFINER_FFPROBE_CALL" in message for message in debug_messages)
    assert any("REFINER_FFPROBE_RESULT" in message for message in debug_messages)


def test_ffprobe_failure_result_still_warns(tmp_path: Path, monkeypatch) -> None:
    media = tmp_path / "movie.mkv"
    media.write_bytes(b"not-empty")
    warning_messages: list[str] = []
    monkeypatch.setattr(refiner_remux_mux, "resolve_ffprobe_ffmpeg", lambda *, mediamop_home: ("ffprobe", "ffmpeg"))
    monkeypatch.setattr(refiner_remux_mux.logger, "debug", lambda *args, **kwargs: None)
    monkeypatch.setattr(refiner_remux_mux.logger, "warning", lambda msg, *args, **kwargs: warning_messages.append(msg % args))
    monkeypatch.setattr(
        refiner_remux_mux.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=1, stdout="", stderr="broken"),
    )

    with pytest.raises(RuntimeError, match="broken"):
        refiner_remux_mux.ffprobe_json(media, mediamop_home=str(tmp_path))

    assert any("REFINER_FFPROBE_RESULT" in message for message in warning_messages)
