"""A weighted budget for concurrency, instead of counting files.

``max_concurrent_files`` treated a 700 MB SD rip and a 60 GB 4K remux as the same unit of
work. They are not, and a machine sized for two of the latter is idle under six of the
former. Weighting by resolution makes small files effectively free and lets the box
self-limit on the expensive work, which is the real constraint.

The cost of a file is known **at enqueue**, not at lease, and is written onto the job row.
That is deliberate: the lease has to answer "does this fit in what is left?" in one
statement, and a row carrying its own cost makes that a comparison rather than a join
against a probe result that may not exist yet.

A file MediaMop has not processed before has no recorded resolution, so it costs
``undetermined`` — zero on the shipped defaults, matching the observed FileFlows values.
That errs toward admitting work rather than stalling on the unknown, and the resolution
is recorded after the first pass so the next one is weighted properly.
"""

from __future__ import annotations

from dataclasses import dataclass

#: The classes a file is weighted by. Fixed, because the operator-facing question is
#: "what does a 4K file cost me", not "define a resolution taxonomy".
RESOLUTION_CLASSES: tuple[str, ...] = ("sd", "720p", "1080p", "4k", "undetermined")

#: Bands by **width**, not height. Height alone cannot tell 1280x720 from 1920x800 — a
#: 2.35:1 crop of a 1080p master — and weighting a scope film as 720p would put the
#: expensive work in the free tier. Width is stable across aspect ratios: a 1080p file is
#: 1920 wide whether it is 1080, 1076 or 800 lines tall.
_CLASS_BY_WIDTH: tuple[tuple[int, str], ...] = (
    (1200, "sd"),
    (1900, "720p"),
    (2600, "1080p"),
)

#: Used only when width is missing from the probe. Less reliable, for the reason above.
_CLASS_BY_HEIGHT: tuple[tuple[int, str], ...] = (
    (700, "sd"),
    (1000, "720p"),
    (1500, "1080p"),
)


def resolution_class_for_dimensions(*, width: int | None, height: int | None) -> str:
    """The weight class for a video's dimensions.

    Bands rather than equalities, because real files are messy. Anything unknown is
    ``undetermined`` rather than guessed at.
    """

    if width is not None and width > 0:
        for ceiling, name in _CLASS_BY_WIDTH:
            if width < ceiling:
                return name
        return "4k"
    if height is None or height <= 0:
        return "undetermined"
    for ceiling, name in _CLASS_BY_HEIGHT:
        if height < ceiling:
            return name
    return "4k"


def resolution_class_for_height(height: int | None) -> str:
    """Class from height alone, for a file measured before widths were recorded."""

    return resolution_class_for_dimensions(width=None, height=height)


@dataclass(frozen=True, slots=True)
class RunnerBudget:
    """Total capacity and what each class of file costs against it."""

    capacity: int
    costs: dict[str, int]

    def cost_for(self, resolution_class: str | None) -> int:
        name = (resolution_class or "undetermined").strip().lower()
        if name not in self.costs:
            name = "undetermined"
        return max(0, int(self.costs.get(name, 0)))

    def available(self, *, in_use: int) -> int:
        return max(0, int(self.capacity) - max(0, int(in_use)))


def budget_from_settings(row: object) -> RunnerBudget:
    """Read the budget off the operator settings row."""

    return RunnerBudget(
        capacity=max(1, int(getattr(row, "runner_capacity", 4) or 4)),
        costs={
            "sd": max(0, int(getattr(row, "runner_cost_sd", 0) or 0)),
            "720p": max(0, int(getattr(row, "runner_cost_720p", 0) or 0)),
            "1080p": max(0, int(getattr(row, "runner_cost_1080p", 1) or 0)),
            "4k": max(0, int(getattr(row, "runner_cost_4k", 1) or 0)),
            "undetermined": max(0, int(getattr(row, "runner_cost_undetermined", 0) or 0)),
        },
    )


def capacity_from_legacy_concurrency(max_concurrent_files: int) -> int:
    """Map the old flat count onto a capacity that preserves behaviour on upgrade.

    One-for-one. With the shipped costs a 1080p or 4K file costs one unit, so a capacity
    equal to the old count runs the same number of expensive files at once. Smaller files
    now cost nothing and so run alongside, which is the improvement — and it is an
    improvement rather than a surprise, because the thing the old number was protecting
    was never the count.
    """

    return max(1, min(64, int(max_concurrent_files or 1)))


def _largest_dimension(video_streams: list[dict], keys: tuple[str, ...]) -> int | None:
    values: list[int] = []
    for stream in video_streams:
        if not isinstance(stream, dict):
            continue
        for key in keys:
            raw = stream.get(key)
            try:
                value = int(raw)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                continue
            if value > 0:
                values.append(value)
                break
    return max(values) if values else None


def video_dimensions_from_streams(video_streams: list[dict]) -> tuple[int | None, int | None]:
    """``(width, height)`` of the largest video stream, or ``(None, None)``.

    Largest rather than first: a file can carry a cover-art or thumbnail stream that
    ffprobe reports as video, and weighting a 4K remux by its 300-line poster would put
    the most expensive work in the free tier.
    """

    return (
        _largest_dimension(video_streams, ("width", "coded_width")),
        _largest_dimension(video_streams, ("height", "coded_height")),
    )


def video_height_from_streams(video_streams: list[dict]) -> int | None:
    """Height only, for callers that do not need the width."""

    return video_dimensions_from_streams(video_streams)[1]
