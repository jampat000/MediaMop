"""Commit-time activity freshness broadcaster for the SSE stream."""

from __future__ import annotations

import asyncio
import threading


class ActivityLatestNotifier:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._latest_id: int | None = None
        self._version = 0
        self._waiters: dict[asyncio.AbstractEventLoop, set[asyncio.Future[tuple[int | None, int]]]] = {}

    def snapshot(self) -> tuple[int | None, int]:
        with self._lock:
            return self._latest_id, self._version

    def notify(self, latest_id: int) -> None:
        with self._lock:
            self._latest_id = latest_id
            self._version += 1
            latest = (self._latest_id, self._version)
            waiters = [(loop, future) for loop, futures in self._waiters.items() for future in list(futures)]
        for loop, future in waiters:
            if future.done():
                continue
            try:
                loop.call_soon_threadsafe(self._resolve_waiter, future, latest)
            except RuntimeError:
                self._discard_waiter(loop, future)

    def _resolve_waiter(
        self,
        future: asyncio.Future[tuple[int | None, int]],
        latest: tuple[int | None, int],
    ) -> None:
        if not future.done():
            future.set_result(latest)

    def _discard_waiter(
        self,
        loop: asyncio.AbstractEventLoop,
        future: asyncio.Future[tuple[int | None, int]],
    ) -> None:
        with self._lock:
            futures = self._waiters.get(loop)
            if futures is None:
                return
            futures.discard(future)
            if not futures:
                self._waiters.pop(loop, None)

    async def wait_for_change(self, previous_version: int, *, timeout: float) -> tuple[int | None, int] | None:
        loop = asyncio.get_running_loop()
        future: asyncio.Future[tuple[int | None, int]] = loop.create_future()
        with self._lock:
            if self._version != previous_version:
                return self._latest_id, self._version
            self._waiters.setdefault(loop, set()).add(future)
        try:
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            return None
        finally:
            self._discard_waiter(loop, future)

    def waiter_count_for_tests(self) -> int:
        with self._lock:
            return sum(len(futures) for futures in self._waiters.values())

    def reset_for_tests(self) -> None:
        with self._lock:
            for futures in self._waiters.values():
                for future in futures:
                    if not future.done():
                        future.cancel()
            self._latest_id = None
            self._version = 0
            self._waiters = {}


activity_latest_notifier = ActivityLatestNotifier()
