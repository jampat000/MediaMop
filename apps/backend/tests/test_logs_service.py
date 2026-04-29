from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

from mediamop.core.config import MediaMopSettings
from mediamop.platform.suite_settings.logs_service import prune_log_file, read_suite_logs


def _settings(tmp_path: Path) -> MediaMopSettings:
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    return replace(MediaMopSettings.load(), log_dir=str(log_dir))


def _line(at: datetime, *, level: str = "INFO", message: str = "hello") -> str:
    return json.dumps(
        {
            "timestamp": at.isoformat().replace("+00:00", "Z"),
            "level": level,
            "logger": "mediamop.tests",
            "message": message,
            "source": "test.py:1",
        },
        separators=(",", ":"),
    )


def test_read_suite_logs_streams_and_returns_newest_matching_rows(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    now = datetime.now(UTC)
    path = Path(settings.log_dir) / "mediamop.log"
    with path.open("w", encoding="utf-8") as handle:
        for i in range(20):
            handle.write(_line(now + timedelta(seconds=i), message=f"row-{i}") + "\n")

    rows, total, counts = read_suite_logs(settings, search="row", limit=5)

    assert total == 20
    assert counts["INFO"] == 20
    assert [row.message for row in rows] == ["row-19", "row-18", "row-17", "row-16", "row-15"]


def test_prune_log_file_replaces_atomically_and_removes_temp_on_success(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    now = datetime.now(UTC)
    path = Path(settings.log_dir) / "mediamop.log"
    path.write_text(
        "\n".join(
            [
                _line(now - timedelta(days=40), message="old"),
                _line(now - timedelta(days=2), message="fresh"),
            ],
        )
        + "\n",
        encoding="utf-8",
    )

    prune_log_file(settings, keep_days=30)

    text = path.read_text(encoding="utf-8")
    assert "fresh" in text
    assert "old" not in text
    assert not list(Path(settings.log_dir).glob("*.prune"))
