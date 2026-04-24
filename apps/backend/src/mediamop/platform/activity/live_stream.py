"""Commit-time activity freshness broadcaster for the SSE stream."""

from __future__ import annotations

import asyncio
import threading


class ActivityLatestNotifier:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._latest_id: int | None = None
        self._version = 0
        self._loop: asyncio.AbstractEventLoop | None = None
        self._event: asyncio.Event | None = None

    def snapshot(self) -> tuple[int | None, int]:
        with self._lock:
            return self._latest_id, self._version

    def notify(self, latest_id: int) -> None:
        with self._lock:
            self._latest_id = latest_id
            self._version += 1
            loop = self._loop
            event = self._event
        if loop is not None and event is not None:
            try:
                loop.call_soon_threadsafe(event.set)
            except RuntimeError:
                with self._lock:
                    if self._loop is loop:
                        self._loop = None
                    if self._event is event:
                        self._event = None

    async def wait_for_change(self, previous_version: int, *, timeout: float) -> tuple[int | None, int] | None:
        loop = asyncio.get_running_loop()
        with self._lock:
            if self._version != previous_version:
                return self._latest_id, self._version
            if self._loop is not loop or self._event is None:
                self._loop = loop
                self._event = asyncio.Event()
            event = self._event
        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            return None
        finally:
            event.clear()
        with self._lock:
            return self._latest_id, self._version

    def reset_for_tests(self) -> None:
        with self._lock:
            self._latest_id = None
            self._version = 0
            self._loop = None
            self._event = None


activity_latest_notifier = ActivityLatestNotifier()
