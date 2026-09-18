"""Correct-behaviour contract tests for issue #544 (media manager defects found while porting).

Each test proves the *fixed* behaviour, which the .NET server implements.
"""

from __future__ import annotations

import http.server
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import httpx
import pytest

from tests.contract.media_managers._helpers import (
    NO_WEBHOOK_SECRET,
    LibraryFolders,
    clear_connections,
    create_connection,
    ensure_library,
)
from tests.contract.support import seed
from tests.contract.support.client import API, WeirClient
from tests.contract.support.launcher import ServerUnderTest

WEBHOOK_SECRET_VALUE = "issue-544-instance-secret"
WEBHOOK_SECRET = {"X-Webhook-Secret": WEBHOOK_SECRET_VALUE}


@pytest.fixture(scope="module")
def server_env() -> dict[str, str]:
    # An instance-wide secret is configured so the item 5 test's webhook and hand-off-status calls
    # authenticate; it never masks item 6's per-connection secrets (those win whenever any enabled
    # connection of the kind has its own secret — see MediaManagerIntake.AuthoriseAsync).
    return {**NO_WEBHOOK_SECRET, "WEIR_MEDIA_MANAGER_WEBHOOK_SECRET": WEBHOOK_SECRET_VALUE}


@pytest.fixture
def operator(admin: WeirClient) -> WeirClient:
    """A signed-in operator with no media manager connections left over."""

    clear_connections(admin)
    return admin


def _create(client: WeirClient, **overrides: Any) -> dict[str, Any]:
    response = create_connection(client, **overrides)
    assert response.status_code == 201, response.text
    return response.json()


# --- item 1: a manager answering 2xx with a body that is not JSON ----------------------------
#
# json.loads on a non-JSON 2xx body (an HTML login page from a reverse proxy, most often) raises
# ValueError uncaught in both the connection test and the capabilities list, answering 500. Fixed:
# classified as "did not give Weir the answer it expected" with a plain message, like any other
# manager that answers oddly.


class _RawHtmlHandler(http.server.BaseHTTPRequestHandler):
    """Answers every request with a fixed 200 OK body that is not JSON at all."""

    body = b"<html><body>Please sign in to continue</body></html>"

    def log_message(self, *_args: object) -> None:
        return

    def _answer(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(self.body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(self.body)

    do_GET = do_POST = do_PUT = do_DELETE = do_HEAD = _answer  # noqa: N815 - http.server's naming


@contextmanager
def not_a_media_manager() -> Iterator[str]:
    """A real HTTP server that answers every request 2xx with a body that is not JSON."""

    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _RawHtmlHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_address[1]}"
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_a_connection_test_classifies_a_2xx_non_json_answer(operator: WeirClient) -> None:
    with not_a_media_manager() as base_url:
        row = _create(operator, kind="radarr", name="Radarr", base_url=base_url, api_key="k")
        tested = operator.post_csrf(f"{API}/media-managers/connections/{row['id']}/test")
        assert tested.status_code == 200, tested.text
        body = tested.json()
        assert body["ok"] is False
        assert "did not get the answer it expected" in body["detail"]


def test_capabilities_classifies_a_2xx_non_json_answer(operator: WeirClient) -> None:
    with not_a_media_manager() as base_url:
        _create(operator, kind="radarr", name="Radarr", base_url=base_url, api_key="k")
        response = operator.get(f"{API}/media-managers/capabilities")
        assert response.status_code == 200, response.text
        row = response.json()[0]
        assert row["reachable"] is False


# --- item 2: an invalid lane time is a 400 naming the field -----------------------------------


def test_an_invalid_lane_time_is_a_400_naming_the_field(operator: WeirClient) -> None:
    row = _create(operator)

    def lane(start: str, end: str) -> dict[str, object]:
        return {
            "enabled": True,
            "max_items_per_run": 25,
            "retry_delay_minutes": 60,
            "schedule_enabled": True,
            "schedule_days": "Mon",
            "schedule_start": start,
            "schedule_end": end,
            "schedule_interval_seconds": 900,
        }

    bad_hour = operator.put_csrf(f"{API}/media-managers/connections/{row['id']}/lanes/missing", lane("25:00", "23:59"))
    assert bad_hour.status_code == 400, bad_hour.text
    assert bad_hour.json()["detail"].startswith("schedule_start:")

    not_a_time = operator.put_csrf(f"{API}/media-managers/connections/{row['id']}/lanes/missing", lane("00:00", "9"))
    assert not_a_time.status_code == 400, not_a_time.text
    assert not_a_time.json()["detail"].startswith("schedule_end:")

    # Refused, not half-saved: the lane still holds its untouched default.
    unchanged = operator.get(f"{API}/media-managers/connections/{row['id']}")
    saved_lane = next(item for item in unchanged.json()["lanes"] if item["lane"] == "missing")
    assert (saved_lane["schedule_start"], saved_lane["schedule_end"]) == ("00:00", "23:59")


# --- item 5: hand-off ledger prefix matching is exact, not a SQL wildcard ---------------------


@pytest.fixture(scope="module")
def issue_544_movies(tmp_path_factory: pytest.TempPathFactory) -> LibraryFolders:
    root = tmp_path_factory.mktemp("issue_544_libraries")
    return LibraryFolders.make(root / "movies")


def test_hand_off_ledger_prefix_matching_is_exact_not_a_sql_wildcard(
    server: ServerUnderTest, admin: WeirClient, issue_544_movies: LibraryFolders
) -> None:
    """SQLAlchemy's ``Column.startswith()`` compiles to plain SQL ``LIKE`` with no escaping, so a
    hand-off folder named with a ``_`` matches an unrelated sibling folder whose name merely
    resembles it (``_`` matching any one character), and SQLite's default ``LIKE`` also ignores
    case regardless of platform. Fixed: exact prefix comparison, so the sibling folder's file is
    never folded into this hand-off's status.
    """

    ensure_library(admin, name="Issue544Movies", media_type="movie", folders=issue_544_movies)
    folder = issue_544_movies.watched / "Foo_Bar"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "film.mkv").write_bytes(b"12345")

    handoff_id = "h-544-item-5"
    handed_off = admin.post(
        f"{API}/intake/webhook/deluno",
        json={
            "eventType": "deluno.processor-handoff",
            "handoffId": handoff_id,
            "mediaType": "movies",
            "sourcePath": str(folder),
        },
        headers=WEBHOOK_SECRET,
    )
    assert handed_off.status_code == 200, handed_off.text

    with seed.stopped(server) as conn:
        ledger = seed.rows(
            conn,
            "SELECT library_id FROM media_manager_handoffs WHERE source_key = 'deluno' AND handoff_id = ?",
            (handoff_id,),
        )
        assert ledger, "no ledger row was recorded for the hand-off"
        library_id = ledger[0]["library_id"]
        # Under SQL LIKE, "Foo_Bar/%" wildcards the "_" and matches this unrelated sibling folder's
        # file too — it is "mid-import" (processing), so a buggy match changes the reported state.
        conn.execute(
            "INSERT INTO files (library_id, relative_path, status) VALUES (?, ?, 'processing')",
            (library_id, "FooXBar/other.mkv"),
        )

    # seed.stopped() restarts the server on a fresh port, so this reads server.base_url again
    # rather than reusing a client bound to the port that was live before the restart.
    status = httpx.get(
        f"{server.base_url}{API}/intake/handoffs/deluno/{handoff_id}", headers=WEBHOOK_SECRET, timeout=30
    )
    assert status.status_code == 200, status.text
    assert status.json()["state"] == "queued", (
        "an unrelated sibling folder's file must not be folded into this hand-off's status"
    )


# --- item 6: several enabled connections of one kind each authenticate with their own secret --


def test_two_radarr_connections_each_authenticate_with_their_own_secret(operator: WeirClient) -> None:
    """The webhook only checked the first enabled connection of a kind (by id), so a second Radarr
    (a 4K instance alongside a 1080p one, say) with its own secret could never authenticate. Fixed:
    the presented secret is matched against every enabled connection of the kind.
    """

    row_1080p = _create(operator, kind="radarr", name="1080p", base_url="http://10.1.1.5:7878")
    row_4k = _create(operator, kind="radarr", name="4K", base_url="http://10.1.1.6:7878")
    secret_1080p = operator.post_csrf(f"{API}/media-managers/connections/{row_1080p['id']}/webhook-secret").json()[
        "webhook_secret"
    ]
    secret_4k = operator.post_csrf(f"{API}/media-managers/connections/{row_4k['id']}/webhook-secret").json()[
        "webhook_secret"
    ]
    assert secret_1080p != secret_4k

    body = {"eventType": "Grab"}
    accepted_1080p = operator.post(
        f"{API}/intake/webhook/radarr", json=body, headers={"X-Webhook-Secret": secret_1080p}
    )
    assert accepted_1080p.status_code == 200, accepted_1080p.text
    accepted_4k = operator.post(f"{API}/intake/webhook/radarr", json=body, headers={"X-Webhook-Secret": secret_4k})
    assert accepted_4k.status_code == 200, accepted_4k.text

    refused = operator.post(
        f"{API}/intake/webhook/radarr", json=body, headers={"X-Webhook-Secret": "neither connections secret"}
    )
    assert refused.status_code == 401, refused.text
