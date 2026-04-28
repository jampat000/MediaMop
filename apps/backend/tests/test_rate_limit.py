from __future__ import annotations

from mediamop.platform.auth.rate_limit import SlidingWindowLimiter


def test_sliding_window_limiter_removes_empty_expired_buckets(monkeypatch) -> None:
    now = 1000.0
    monkeypatch.setattr("mediamop.platform.auth.rate_limit.time.monotonic", lambda: now)
    limiter = SlidingWindowLimiter(max_events=2, window_seconds=10)

    assert limiter.allow("one") is True
    assert limiter.allow("two") is True
    assert len(limiter._buckets) == 2

    now = 1011.0
    assert limiter.allow("three") is True

    assert set(limiter._buckets) == {"three"}
