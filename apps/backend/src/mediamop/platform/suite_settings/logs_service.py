"""Read and prune structured MediaMop runtime logs."""

from __future__ import annotations

import json
import os
import tempfile
from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy.orm import Session

from mediamop.core.config import MediaMopSettings
from mediamop.platform.suite_settings.service import ensure_suite_settings_row


@dataclass(frozen=True)
class ParsedLogEntry:
    timestamp: str
    level: str
    component: str
    message: str
    detail: str | None
    traceback: str | None
    source: str | None
    logger: str
    correlation_id: str | None
    job_id: str | None


def read_suite_logs(
    settings: MediaMopSettings,
    *,
    level: str | None = None,
    search: str | None = None,
    has_exception: bool | None = None,
    limit: int = 100,
) -> tuple[list[ParsedLogEntry], int, dict[str, int]]:
    path = _log_file_path(settings)
    if not path.is_file():
        return ([], 0, {"ERROR": 0, "WARNING": 0, "INFO": 0})

    requested_level = (level or "").strip().upper() or None
    search_term = (search or "").strip().lower()
    rows: deque[ParsedLogEntry] = deque(maxlen=max(1, min(limit, 250)))
    counts = {"ERROR": 0, "WARNING": 0, "INFO": 0}
    total = 0

    try:
        handle = path.open("r", encoding="utf-8")
    except OSError:
        return ([], 0, counts)

    with handle:
        for raw in handle:
            entry = _parse_log_line(raw)
            if entry is None:
                continue
            if _skip_low_value_noise(entry):
                continue
            total += 1
            counts[_count_bucket(entry.level)] += 1
            if requested_level and entry.level != requested_level:
                continue
            if has_exception is True and not entry.traceback:
                continue
            if has_exception is False and entry.traceback:
                continue
            if search_term:
                haystack = " ".join(
                    part
                    for part in (
                        entry.message,
                        entry.detail or "",
                        entry.traceback or "",
                        entry.logger,
                        entry.source or "",
                        entry.component,
                        entry.correlation_id or "",
                        entry.job_id or "",
                    )
                    if part
                ).lower()
                if search_term not in haystack:
                    continue
            rows.append(entry)

    return list(reversed(rows)), total, counts


def prune_logs_for_retention(session: Session, settings: MediaMopSettings) -> None:
    keep_days = max(1, int(ensure_suite_settings_row(session).log_retention_days))
    prune_log_file(settings, keep_days=keep_days)


def prune_log_file(settings: MediaMopSettings, *, keep_days: int) -> None:
    path = _log_file_path(settings)
    if not path.is_file():
        return
    cutoff = datetime.now(UTC) - timedelta(days=max(1, keep_days))
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_name: str | None = None
    try:
        fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".prune", dir=str(path.parent))
        with path.open("r", encoding="utf-8") as source, os.fdopen(fd, "w", encoding="utf-8") as target:
            for raw in source:
                parsed = _parse_log_line(raw)
                if parsed is None:
                    continue
                try:
                    at = datetime.fromisoformat(parsed.timestamp.replace("Z", "+00:00"))
                except ValueError:
                    continue
                if at >= cutoff:
                    target.write(raw.rstrip("\n") + "\n")
        os.replace(tmp_name, path)
    except OSError:
        if tmp_name:
            try:
                Path(tmp_name).unlink()
            except OSError:
                pass
        return


def _log_file_path(settings: MediaMopSettings) -> Path:
    return Path(settings.log_dir) / "mediamop.log"


def _parse_log_line(raw: str) -> ParsedLogEntry | None:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    timestamp = str(payload.get("timestamp") or "").strip()
    level = str(payload.get("level") or "INFO").strip().upper() or "INFO"
    logger = str(payload.get("logger") or "mediamop").strip() or "mediamop"
    message = str(payload.get("message") or "").strip()
    if not timestamp or not message:
        return None
    return ParsedLogEntry(
        timestamp=timestamp,
        level=level,
        component=_component_label(logger=logger, source=payload.get("source")),
        message=message,
        detail=_clean_optional_str(payload.get("detail")),
        traceback=_clean_optional_str(payload.get("traceback")),
        source=_clean_optional_str(payload.get("source")),
        logger=logger,
        correlation_id=_clean_optional_str(payload.get("correlation_id")),
        job_id=_clean_optional_str(payload.get("job_id")),
    )


def _component_label(*, logger: str, source: object) -> str:
    haystack = f"{logger} {source or ''}".lower()
    if "modules.refiner" in haystack:
        return "Refiner"
    if "modules.pruner" in haystack:
        return "Pruner"
    if "modules.subber" in haystack:
        return "Subber"
    if "platform.auth" in haystack:
        return "Authentication"
    if "platform.activity" in haystack:
        return "Activity"
    return "System"


def _clean_optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _count_bucket(level: str) -> str:
    if level in {"ERROR", "CRITICAL"}:
        return "ERROR"
    if level == "WARNING":
        return "WARNING"
    return "INFO"


def _skip_low_value_noise(entry: ParsedLogEntry) -> bool:
    if entry.level in {"ERROR", "WARNING", "CRITICAL"}:
        return False
    return not entry.logger.startswith("mediamop")
