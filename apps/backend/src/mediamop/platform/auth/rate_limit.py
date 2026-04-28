"""In-process sliding-window rate limiting.

Counters live in process memory and are valid only under MediaMop's supported
single-application-process deployment model.
"""

from __future__ import annotations

import ipaddress
import logging
import threading
import time
from collections import defaultdict

logger = logging.getLogger(__name__)
_forwarded_without_trust_warned = False


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
    """Stable per-request key for abuse controls.

    ``X-Forwarded-For`` is used only when the immediate peer is explicitly trusted
    through ``MEDIAMOP_TRUSTED_PROXY_IPS``.
    """

    peer = request.client.host if request.client and request.client.host else "unknown"
    xff = (request.headers.get("x-forwarded-for") or "").strip()
    settings = getattr(getattr(request, "app", None), "state", None)
    trusted_raw = tuple(getattr(getattr(settings, "settings", None), "trusted_proxy_ips", ()) or ())
    if not xff:
        return peer
    if not trusted_raw:
        _warn_forwarded_headers_ignored()
        return peer
    trusted = [_parse_proxy_network(value) for value in trusted_raw]
    trusted = [item for item in trusted if item is not None]
    if not _ip_in_networks(peer, trusted):
        return peer
    chain = [item.strip() for item in xff.split(",") if item.strip()]
    for candidate in reversed(chain):
        if not _ip_in_networks(candidate, trusted):
            return candidate
    return chain[0] if chain else peer


def _parse_proxy_network(raw: str):
    try:
        return ipaddress.ip_network(raw, strict=False)
    except ValueError:
        logger.warning("Ignoring invalid MEDIAMOP_TRUSTED_PROXY_IPS entry: %s", raw)
        return None


def _ip_in_networks(raw: str, networks) -> bool:
    try:
        ip = ipaddress.ip_address(raw)
    except ValueError:
        return False
    return any(ip in network for network in networks)


def _warn_forwarded_headers_ignored() -> None:
    global _forwarded_without_trust_warned
    if _forwarded_without_trust_warned:
        return
    _forwarded_without_trust_warned = True
    logger.warning(
        "X-Forwarded-For was present but MEDIAMOP_TRUSTED_PROXY_IPS is not configured; "
        "rate limiting will use the immediate peer address."
    )
