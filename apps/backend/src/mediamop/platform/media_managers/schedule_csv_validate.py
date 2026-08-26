from __future__ import annotations

from mediamop.platform.media_managers.schedule_wall_clock import DAY_NAMES


def validate_schedule_days_csv(raw: str) -> str:
    """Return normalized comma-separated weekday tokens, or raise ValueError with plain message."""

    s = (raw or "").strip()
    if not s:
        return ""
    tokens = [t.strip() for t in s.split(",") if t.strip()]
    bad = [t for t in tokens if t not in DAY_NAMES]
    if bad:
        msg = "Days must be written like Mon, Tue, Wed with commas between them."
        raise ValueError(msg)
    return ",".join(tokens)


def normalize_hhmm(raw: str, *, fallback: str) -> str:
    t = (raw or "").strip()
    if not t:
        return fallback
    parts = t.split(":")
    if len(parts) != 2:
        msg = "Times must look like 09:30 (hour and minute)."
        raise ValueError(msg)
    try:
        h = int(parts[0])
        m = int(parts[1])
    except ValueError as e:
        msg = "Times must look like 09:30 (hour and minute)."
        raise ValueError(msg) from e
    if not (0 <= h <= 23 and 0 <= m <= 59):
        msg = "Hour must be 0–23 and minute must be 0–59."
        raise ValueError(msg)
    return f"{h:02d}:{m:02d}"
