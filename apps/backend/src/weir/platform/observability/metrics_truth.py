"""Shared helpers for dashboard/overview metric truthfulness."""

from __future__ import annotations

from collections.abc import Mapping


def require_non_negative_metric_counts(counts: Mapping[str, int]) -> None:
    for name, value in counts.items():
        if int(value) < 0:
            raise ValueError(f"Metric {name!r} must not be negative.")


def finalized_success_total(counts: Mapping[str, int]) -> int:
    """Return a success total from explicit finalized terminal outcome components only."""

    require_non_negative_metric_counts(counts)
    return sum(int(v) for v in counts.values())
