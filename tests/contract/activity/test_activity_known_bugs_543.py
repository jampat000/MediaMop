"""Correct-behaviour proof for #543 items 1-3, fixed in the .NET server only (ADR-0017: Python is retiring).

Each test asserts what ``/api/v1/activity/recent`` should do; Python still has the underlying bug
(the README section of ``apps/server`` documents the fix), so these are marked ``known_bug`` for
``backends=("python",)`` — dotnet must pass them now, and the marker comes off once (if ever)
Python is fixed too.

Two things every test here works around:

- ``seed.stopped`` restarts the server on a new port, so every client is created *after* the
  seeding block, the way ``tests/contract/refiner/_helpers.py``'s ``ensure_viewer`` does — a client
  built beforehand would still be pointed at the old, now-dead port.
- The server's own activity-retention sweep prunes events older than 90 days (the default), and
  runs against real wall-clock time even in a test server, so seeded rows are dated close to
  ``datetime.now(UTC)`` rather than a fixed past date that the sweep could delete out from under
  the test.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from tests.contract.activity._helpers import insert_event
from tests.contract.support import seed
from tests.contract.support.client import API, WeirClient
from tests.contract.support.launcher import ServerUnderTest


@pytest.mark.known_bug(issue=543, backends=("python",))
def test_recent_total_and_has_more_count_every_matching_row_with_no_filter(
    server: ServerUnderTest, client_factory: Callable[..., WeirClient]
) -> None:
    """Item 1: Python's unfiltered count query drops its FROM (``SELECT count(*)``, which is 1)."""

    now = datetime.now(UTC)
    with seed.stopped(server) as conn:
        conn.execute("DELETE FROM activity_events")
        for offset in range(5):
            insert_event(conn, event_type="a.event", module="refiner", title=f"row {offset}", created_at=now)
    client = client_factory(server)
    client.ensure_admin()

    # A page that holds everything tells us the real total without relying on the bug being fixed
    # (max(total, len(items)) already hides the bug when nothing is truncated) — it also counts the
    # admin sign-in's own event, however many that turns out to be, without hard-coding it.
    whole_page = client.get(f"{API}/activity/recent", params={"limit": 100}).json()
    total = len(whole_page["items"])
    assert total >= 5
    assert whole_page["total"] == total
    assert whole_page["has_more"] is False

    small_page = client.get(f"{API}/activity/recent", params={"limit": 2}).json()
    assert small_page["total"] == total
    assert small_page["has_more"] is True
    assert len(small_page["items"]) == 2


def _offset_text(instant: datetime, offset: timedelta) -> str:
    """``instant`` (UTC) written in the wall clock of a timezone ``offset`` east of UTC."""

    local = instant + offset
    sign = "+" if offset >= timedelta() else "-"
    hours, minutes = divmod(int(abs(offset).total_seconds()) // 60, 60)
    return f"{local:%Y-%m-%dT%H:%M:%S}{sign}{hours:02d}:{minutes:02d}"


@pytest.mark.known_bug(issue=543, backends=("python",))
def test_recent_date_filters_normalize_stored_timestamps_and_honor_offsets(
    server: ServerUnderTest, client_factory: Callable[..., WeirClient]
) -> None:
    """Item 2: a query offset must be honored, and a stored exact-second row must not be excluded."""

    exact_second = datetime.now(UTC).replace(microsecond=0)
    with seed.stopped(server) as conn:
        conn.execute("DELETE FROM activity_events")
        # A whole second: seed.utc_text (like SQLAlchemy) writes this with no fractional part.
        insert_event(conn, event_type="a.exact", module="custom", title="exact second", created_at=exact_second)
    client = client_factory(server)
    client.ensure_admin()

    # The naive filter names the same second the row is stored at, just formatted without a fraction
    # of its own: comparing raw text against "...05.000000" would wrongly exclude it.
    naive_boundary = exact_second.strftime("%Y-%m-%dT%H:%M:%S")
    body = client.get(f"{API}/activity/recent", params={"module": "custom", "date_from": naive_boundary}).json()
    assert [item["title"] for item in body["items"]] == ["exact second"]

    body = client.get(f"{API}/activity/recent", params={"module": "custom", "date_to": naive_boundary}).json()
    assert [item["title"] for item in body["items"]] == ["exact second"]

    # The same instant, named with a +02:00 offset: an ignored offset would compare the shifted
    # wall-clock digits against the stored UTC ones and wrongly exclude the row.
    same_instant_offset = _offset_text(exact_second, timedelta(hours=2))
    body = client.get(f"{API}/activity/recent", params={"module": "custom", "date_from": same_instant_offset}).json()
    assert [item["title"] for item in body["items"]] == ["exact second"]

    # One second later in the same offset: now past the row, in either timezone.
    past_it = _offset_text(exact_second + timedelta(seconds=1), timedelta(hours=2))
    body = client.get(f"{API}/activity/recent", params={"module": "custom", "date_from": past_it}).json()
    assert body["items"] == []


@pytest.mark.known_bug(issue=543, backends=("python",))
def test_recent_paging_by_before_id_never_skips_or_repeats_a_tied_or_out_of_order_row(
    server: ServerUnderTest, client_factory: Callable[..., WeirClient]
) -> None:
    """Item 3: ordered by (created_at DESC, id DESC); before_id pages by that same key, not id alone."""

    now = datetime.now(UTC)
    with seed.stopped(server) as conn:
        conn.execute("DELETE FROM activity_events")
        # Row 2 is chronologically the oldest despite its small id; rows 1 and 3 tie on created_at.
        # Plain "id < before_id" paging (Python's) loses that ordering: it can repeat row 4 on a later
        # page (small id, but already returned) or skip rows entirely.
        insert_event(conn, event_type="a.1", module="custom", title="A", created_at=now - timedelta(seconds=1))
        insert_event(conn, event_type="a.2", module="custom", title="B", created_at=now - timedelta(seconds=6))
        insert_event(conn, event_type="a.3", module="custom", title="C", created_at=now - timedelta(seconds=1))
        insert_event(conn, event_type="a.4", module="custom", title="D", created_at=now - timedelta(seconds=10))
    client = client_factory(server)
    client.ensure_admin()

    first = client.get(f"{API}/activity/recent", params={"module": "custom", "limit": 2}).json()
    assert [item["title"] for item in first["items"]] == ["C", "A"]  # the tie broken by id DESC: 3 before 1

    second = client.get(
        f"{API}/activity/recent",
        params={"module": "custom", "limit": 2, "before_id": first["items"][-1]["id"]},
    ).json()
    assert [item["title"] for item in second["items"]] == ["B", "D"]  # never A again, never loses B or D

    seen_ids = [item["id"] for item in first["items"]] + [item["id"] for item in second["items"]]
    assert len(seen_ids) == len(set(seen_ids)) == 4
