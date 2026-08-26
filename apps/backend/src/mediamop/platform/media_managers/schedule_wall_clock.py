"""Wall-clock schedule windows (IANA timezone) for operator-defined scan windows."""

from __future__ import annotations

from datetime import UTC, datetime, time, timezone
from zoneinfo import ZoneInfo

DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _parse_hhmm(s: str, *, default: time) -> time:
    try:
        parts = (s or "").strip().split(":")
        if len(parts) != 2:
            return default
        h = int(parts[0])
        m = int(parts[1])
        if not (0 <= h <= 23 and 0 <= m <= 59):
            return default
        return time(hour=h, minute=m)
    except Exception:
        return default


def _parse_days(s: str) -> set[str]:
    st = (s or "").strip()
    if st == "":
        return set()
    tokens = [t.strip() for t in st.split(",") if t.strip()]
    out = {t for t in tokens if t in DAY_NAMES}
    return out if out else set(DAY_NAMES)


def schedule_time_window_active(
    *,
    schedule_enabled: bool,
    schedule_days: str,
    schedule_start: str,
    schedule_end: str,
    timezone_name: str,
    now: datetime,
) -> bool:
    """True when the current wall clock (in ``timezone_name``) is inside the configured window."""

    if not schedule_enabled:
        return True
    try:
        tz = ZoneInfo((timezone_name or "UTC").strip() or "UTC")
    except Exception:
        tz = ZoneInfo("UTC")
    cur = now
    cur = cur.replace(tzinfo=UTC).astimezone(tz) if cur.tzinfo is None else cur.astimezone(tz)
    day = DAY_NAMES[cur.weekday()]
    allowed_days = _parse_days(schedule_days)
    if day not in allowed_days:
        return False
    start_t = _parse_hhmm(schedule_start, default=time(0, 0))
    end_t = _parse_hhmm(schedule_end, default=time(23, 59))
    cur_t = cur.time().replace(second=0, microsecond=0)
    if start_t <= end_t:
        return start_t <= cur_t <= end_t
    return cur_t >= start_t or cur_t <= end_t
