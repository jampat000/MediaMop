"""In-process sliding-window rate limiting (Phase 6).

No Redis or external store: counters live in process memory. Suitable for a single
node or few uvicorn workers; limits are **not** shared across processes.

Tradeoffs (intentional for this stage):
- Each worker maintains its own buckets (effective limit scales ~linearly with workers).
- Restart clears counters (attackers also get a fresh window).
- Keys default to the immediate peer IP (``request.client.host``); reverse-proxy setups
  must terminate TLS and expose the real client consistently (``X-Forwarded-For`` is
  **not** parsed here to avoid spoofing without a trusted proxy contract).
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict


class SlidingWindowLimiter:
    """Fixed-capacity sliding window: at most ``max_events`` timestamps within ``window_seconds``."""

    __slots__ = ("_buckets", "_lock", "max_events", "window_seconds")

    def __init__(self, *, max_events: int, window_seconds: float) -> None:
        if max_events < 1:
            raise ValueError("max_events must be >= 1")
        if window_seconds <= 0:
            raise ValueError("window_seconds must be > 0")
        self.max_events = max_events
        self.window_seconds = float(window_seconds)
        self._lock = threading.Lock()
        self._buckets: dict[str, list[float]] = defaultdict(list)

    def allow(self, key: str) -> bool:
        """Record one event for ``key``. Return True if allowed, False if limited."""

        now = time.monotonic()
        cutoff = now - self.window_seconds
        k = key or "unknown"
        with self._lock:
            bucket = self._buckets[k]
            while bucket and bucket[0] < cutoff:
                bucket.pop(0)
            if len(bucket) >= self.max_events:
                return False
            bucket.append(now)
            return True

    def reset_for_tests(self) -> None:
        with self._lock:
            self._buckets.clear()


def client_rate_limit_key(request) -> str:
    """Stable per-request key for abuse controls (direct peer IP when present)."""

    if request.client and request.client.host:
        return request.client.host
    return "unknown"
