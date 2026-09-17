"""Waiting for something to become true, without fixed sleeps."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")


def wait_until(
    probe: Callable[[], T | None],
    *,
    timeout_s: float = 60.0,
    interval_s: float = 0.2,
    what: str = "the condition",
) -> T:
    """Call ``probe`` until it returns something truthy, and return that. Fails with the last value."""

    deadline = time.monotonic() + timeout_s
    last: object = None
    while True:
        try:
            value = probe()
        except AssertionError as exc:
            value = None
            last = exc
        else:
            if value:
                return value
            last = value
        if time.monotonic() >= deadline:
            raise AssertionError(f"Timed out after {timeout_s:.0f}s waiting for {what}; last saw: {last!r}")
        time.sleep(interval_s)
