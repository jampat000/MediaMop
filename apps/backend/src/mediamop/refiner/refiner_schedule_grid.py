"""A 7x24 schedule at 15-minute resolution, stored as 672 characters.

The existing schedule is one start time, one end time and a set of days. That cannot say
"overnight on weeknights and all day at the weekend", which is the shape most operators
actually want from a tool that saturates a disk. A grid can, and a grid at 15-minute
resolution is the same thing FileFlows exposes.

Stored as a string of ``'0'``/``'1'`` rather than a table of slots, because it is read on
every lease decision and a single column read beats 672 rows. An empty string means "no
restriction", which is what every existing library has, so nothing changes on upgrade
until someone draws a grid.

Day 0 is Monday, matching ``datetime.weekday()`` and the existing ``DAY_NAMES`` order, so
there is one weekday convention in the codebase rather than two.
"""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

#: 15-minute resolution. 4 slots an hour, 96 a day, 672 a week.
SLOTS_PER_HOUR = 4
SLOTS_PER_DAY = 24 * SLOTS_PER_HOUR
SLOTS_PER_WEEK = 7 * SLOTS_PER_DAY
SLOT_MINUTES = 60 // SLOTS_PER_HOUR


class ScheduleGridError(ValueError):
    """The grid text is not a usable schedule."""


def empty_grid() -> str:
    """No restriction. Distinct from an all-zero grid, which means "never"."""

    return ""


def full_grid() -> str:
    return "1" * SLOTS_PER_WEEK


def normalize_grid(raw: str | None) -> str:
    """Validate and canonicalise stored grid text.

    Anything that is not exactly 672 characters of ``0``/``1`` is rejected rather than
    coerced: a grid silently padded to a length it did not have would switch work on or
    off at times the operator never chose.
    """

    text = (raw or "").strip()
    if not text:
        return ""
    if len(text) != SLOTS_PER_WEEK:
        raise ScheduleGridError(
            f"A schedule grid must be exactly {SLOTS_PER_WEEK} characters "
            f"(7 days x {SLOTS_PER_DAY} quarter-hours); this one has {len(text)}."
        )
    if set(text) - {"0", "1"}:
        raise ScheduleGridError("A schedule grid may only contain 0 and 1.")
    return text


def slot_index(*, weekday: int, hour: int, minute: int) -> int:
    """Index into the grid for a wall-clock moment. Monday is 0."""

    return (weekday % 7) * SLOTS_PER_DAY + hour * SLOTS_PER_HOUR + minute // SLOT_MINUTES


def grid_allows(grid: str | None, *, timezone_name: str, now: datetime) -> bool:
    """Whether this moment is inside the grid.

    An empty grid allows everything. A grid that fails to parse also allows everything:
    refusing to work because a stored string is malformed would turn a display bug into
    a stoppage, and the malformed value is reported elsewhere.
    """

    try:
        text = normalize_grid(grid)
    except ScheduleGridError:
        return True
    if not text:
        return True
    try:
        tz = ZoneInfo((timezone_name or "UTC").strip() or "UTC")
    except Exception:
        tz = ZoneInfo("UTC")
    moment = now.replace(tzinfo=UTC) if now.tzinfo is None else now
    local = moment.astimezone(tz)
    return text[slot_index(weekday=local.weekday(), hour=local.hour, minute=local.minute)] == "1"


def grid_from_days_and_times(*, days: str, start: str, end: str) -> str:
    """Build a grid from the day/start/end fields it replaces.

    Used by the migration so an upgrade preserves exactly the window a library already
    had. Anything this cannot express faithfully returns an empty grid — no restriction —
    rather than a grid that is nearly right, because a schedule that is nearly right runs
    heavy work at a time the operator excluded.
    """

    from mediamop.platform.media_managers.schedule_wall_clock import DAY_NAMES

    wanted = {d.strip().lower()[:3] for d in (days or "").split(",") if d.strip()}
    if not wanted:
        return ""
    try:
        start_h, start_m = (int(x) for x in (start or "00:00").split(":", 1))
        end_h, end_m = (int(x) for x in (end or "23:59").split(":", 1))
    except (ValueError, TypeError):
        return ""

    start_slot = start_h * SLOTS_PER_HOUR + start_m // SLOT_MINUTES
    # 23:59 means "to the end of the day", so the final slot is inclusive.
    end_slot = end_h * SLOTS_PER_HOUR + end_m // SLOT_MINUTES
    if not (0 <= start_slot < SLOTS_PER_DAY and 0 <= end_slot < SLOTS_PER_DAY):
        return ""

    slots = ["0"] * SLOTS_PER_WEEK
    for day_index, name in enumerate(DAY_NAMES):
        if name.strip().lower()[:3] not in wanted:
            continue
        base = day_index * SLOTS_PER_DAY
        if start_slot <= end_slot:
            for s in range(start_slot, end_slot + 1):
                slots[base + s] = "1"
        else:
            # An overnight window runs to midnight and continues on the following day,
            # which is what the start<=end comparison in the old evaluator did too.
            for s in range(start_slot, SLOTS_PER_DAY):
                slots[base + s] = "1"
            for s in range(0, end_slot + 1):
                slots[((day_index + 1) % 7) * SLOTS_PER_DAY + s] = "1"
    return "".join(slots)


def next_open_slot(grid: str | None, *, timezone_name: str, now: datetime) -> datetime | None:
    """When the grid next allows work, or None if it never does or is unrestricted.

    An operator told "outside its scheduled hours" and nothing else has to go and read
    the grid to find out how long that means.
    """

    try:
        text = normalize_grid(grid)
    except ScheduleGridError:
        return None
    if not text or "1" not in text:
        return None
    try:
        tz = ZoneInfo((timezone_name or "UTC").strip() or "UTC")
    except Exception:
        tz = ZoneInfo("UTC")
    moment = now.replace(tzinfo=UTC) if now.tzinfo is None else now
    local = moment.astimezone(tz)
    start = slot_index(weekday=local.weekday(), hour=local.hour, minute=local.minute)
    from datetime import timedelta

    for ahead in range(1, SLOTS_PER_WEEK + 1):
        if text[(start + ahead) % SLOTS_PER_WEEK] == "1":
            aligned = local.replace(minute=(local.minute // SLOT_MINUTES) * SLOT_MINUTES, second=0, microsecond=0)
            return (aligned + timedelta(minutes=SLOT_MINUTES * ahead)).astimezone(UTC)
    return None
