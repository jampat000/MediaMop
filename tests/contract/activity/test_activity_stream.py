"""Contract port of apps/backend/tests/test_activity_stream.py (the activity SSE freshness stream)."""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from tests.contract.activity._helpers import insert_event
from tests.contract.support import seed
from tests.contract.support.client import API, WeirClient

# Short enough that a stream that never sends fails the test quickly instead of hanging it.
_STREAM_TIMEOUT = httpx.Timeout(10.0, read=10.0)


class _SseReader:
    """Reads one SSE stream block by block (blocks end with a blank line)."""

    def __init__(self, response: httpx.Response) -> None:
        self.response = response
        self._lines = response.iter_lines()

    def next_block(self) -> list[str]:
        block: list[str] = []
        for line in self._lines:
            if line == "":
                if block:
                    return block
                continue
            block.append(line)
        raise AssertionError(f"The stream ended; partial block {block!r}")

    def next_event(self) -> tuple[str, dict[str, Any]]:
        """The next named event, skipping ``retry:`` and ``: keepalive`` blocks."""

        while True:
            block = self.next_block()
            event = next((line[len("event:") :].strip() for line in block if line.startswith("event:")), None)
            if event is None:
                continue
            data = "\n".join(line[len("data:") :].strip() for line in block if line.startswith("data:"))
            return event, json.loads(data)


@contextmanager
def _open_stream(server, client: WeirClient) -> Iterator[_SseReader]:
    with (
        httpx.Client(base_url=server.base_url, cookies=client.cookies, timeout=_STREAM_TIMEOUT) as http,
        http.stream("GET", f"{API}/activity/stream") as response,
    ):
        yield _SseReader(response)


def _latest_activity_id(client: WeirClient) -> int:
    r = client.get(f"{API}/activity/recent", params={"limit": 100})
    assert r.status_code == 200, r.text
    return max(int(item["id"]) for item in r.json()["items"])


def test_activity_stream_requires_authentication(client: WeirClient) -> None:
    r = client.get(f"{API}/activity/stream", timeout=_STREAM_TIMEOUT)
    assert r.status_code == 401


def test_activity_stream_authenticated_emits_latest_format(server, admin: WeirClient) -> None:
    with _open_stream(server, admin) as stream:
        assert stream.response.status_code == 200
        assert stream.response.headers["content-type"].startswith("text/event-stream")
        assert "no-store" in stream.response.headers["cache-control"]
        assert stream.response.headers["x-accel-buffering"] == "no"

        assert stream.next_block() == ["retry: 5000"]
        event, data = stream.next_event()
        assert event == "activity.latest"
        assert set(data) == {"latest_event_id", "activity_revision"}
        assert data["latest_event_id"] == _latest_activity_id(admin)
        assert isinstance(data["activity_revision"], int)


def test_activity_stream_emits_a_newer_id_and_revision_after_a_new_event(
    server, admin: WeirClient, client_factory
) -> None:
    with _open_stream(server, admin) as stream:
        _event, first = stream.next_event()
        # Signing in again records an Activity event while the stream is open. The stream holds no
        # database session, so the write is not blocked by it.
        other = client_factory(server)
        other.login()
        latest = _latest_activity_id(admin)
        assert latest > first["latest_event_id"]

        event, data = stream.next_event()
        while data["latest_event_id"] < latest:
            event, data = stream.next_event()
        assert event == "activity.latest"
        assert data["latest_event_id"] == latest
        assert data["activity_revision"] > first["activity_revision"]


def test_record_activity_event_does_not_prune_history_using_log_retention(server_factory, client_factory) -> None:
    sut = server_factory()
    client = client_factory(sut)
    client.ensure_admin()
    current = client.get(f"{API}/suite/settings").json()
    saved = client.put_csrf(
        f"{API}/suite/settings",
        json={
            "product_display_name": current["product_display_name"],
            "app_timezone": current["app_timezone"],
            "log_retention_days": 1,
            "activity_retention_days": current["activity_retention_days"],
        },
    )
    assert saved.status_code == 200, saved.text

    title = "Old Refiner result that still backs overview history"
    with seed.stopped(sut) as conn:
        insert_event(
            conn,
            event_type="refiner.file_remux_pass_completed",
            module="refiner",
            title=title,
            detail="{}",
            created_at=datetime.now(UTC) - timedelta(days=10),
            result="success",
        )
    client = client_factory(sut)
    client.login()  # records a new sign-in event

    r = client.get(f"{API}/activity/recent", params={"limit": 100})
    assert r.status_code == 200, r.text
    titles = [item["title"] for item in r.json()["items"]]
    assert title in titles
    assert any(item["module"] == "auth" for item in r.json()["items"])
