"""Outbound media manager dialects: what each kind can be asked, and how it answers."""

from __future__ import annotations

from typing import Any

import pytest

from mediamop.platform.media_managers.manager_dialects import (
    capabilities_for_kind,
    kinds_serving_scope,
    port_for_kind,
)
from mediamop.platform.media_managers.manager_http import (
    MediaManagerHttpError,
    MediaManagerRateLimitedError,
)
from mediamop.platform.media_managers.manager_port import ManagerConnection, label_for_connection

_DIALECTS = "mediamop.platform.media_managers.manager_dialects"


def _connection(kind: str = "radarr", name: str = "Main") -> ManagerConnection:
    return ManagerConnection(kind=kind, name=name, base_url="http://manager.local", api_key="k", connection_id=1)


class _FakeClient:
    """Stands in for the HTTP client: one canned answer, or one exception, per path."""

    def __init__(self, answers: dict[str, Any]) -> None:
        self._answers = answers
        self.calls: list[tuple[str, dict[str, Any] | None]] = []

    def get_json(self, path: str, *, params: dict[str, Any] | None = None) -> Any:
        self.calls.append((path, params))
        answer = self._answers[path]
        if isinstance(answer, Exception):
            raise answer
        return answer


def _patch_client(monkeypatch: pytest.MonkeyPatch, answers: dict[str, Any]) -> _FakeClient:
    client = _FakeClient(answers)
    monkeypatch.setattr(f"{_DIALECTS}._client", lambda _connection, *, timeout_seconds: client)
    return client


def test_label_names_the_connection_not_just_the_vendor() -> None:
    assert label_for_connection("deluno", "Main") == "Deluno (Main)"
    assert label_for_connection("radarr", "4K") == "Radarr (4K)"
    # A connection named after its own product is not said twice.
    assert label_for_connection("deluno", "Deluno") == "Deluno"
    assert label_for_connection("native", "Home") == "Media manager (Home)"


def test_scope_capabilities_are_static_so_binding_costs_no_requests() -> None:
    assert set(kinds_serving_scope("movie")) == {"radarr", "deluno", "native"}
    assert set(kinds_serving_scope("tv")) == {"sonarr", "deluno", "native"}
    deluno = capabilities_for_kind("deluno")
    assert deluno is not None
    assert deluno.scopes == frozenset({"movie", "tv"})
    assert deluno.reports_queue is True
    # Deluno describes its libraries, not its individual files, so it cannot clear a delete.
    assert deluno.reports_library_truth is False


def test_arr_queue_reads_the_records_envelope(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _patch_client(monkeypatch, {"/api/v3/queue": {"records": [{"status": "downloading"}, "junk"]}})
    port = port_for_kind("radarr")
    assert port is not None
    signal = port.queue_rows(_connection())
    assert signal.status == "reported"
    assert [row.scope for row in signal.rows] == ["movie"]
    assert client.calls[0][0] == "/api/v3/queue"


def test_arr_library_truth_reads_the_nested_movie_file(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_client(
        monkeypatch,
        {"/api/v3/movie": [{"movieFile": {"path": "/media/Solaris/f.mkv"}}, {"movieFile": None}, {}]},
    )
    port = port_for_kind("radarr")
    assert port is not None
    truth = port.library_truth(_connection(), media_scope="movie")
    assert truth.status == "reported"
    assert truth.library_file_paths == ("/media/Solaris/f.mkv",)


def test_arr_library_truth_reads_the_flat_episode_file(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_client(monkeypatch, {"/api/v3/episodefile": [{"path": "/tv/Show/S01/e.mkv"}]})
    port = port_for_kind("sonarr")
    assert port is not None
    truth = port.library_truth(_connection(kind="sonarr", name="Main"), media_scope="tv")
    assert truth.library_file_paths == ("/tv/Show/S01/e.mkv",)


def test_a_manager_asked_about_the_wrong_scope_says_no_signal_not_empty() -> None:
    port = port_for_kind("radarr")
    assert port is not None
    truth = port.library_truth(_connection(), media_scope="tv")
    assert truth.status == "no_signal"
    assert truth.library_file_paths == ()


def test_unreachable_manager_is_reported_with_the_connection_named(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_client(monkeypatch, {"/api/v3/queue": OSError("connection refused")})
    port = port_for_kind("radarr")
    assert port is not None
    signal = port.queue_rows(_connection(name="4K"))
    assert signal.status == "unreachable"
    assert signal.detail is not None
    assert "Radarr (4K)" in signal.detail


def test_a_refused_key_says_which_key_to_go_and_fix(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_client(monkeypatch, {"/api/v3/queue": MediaManagerHttpError("HTTP 401: nope")})
    port = port_for_kind("radarr")
    assert port is not None
    signal = port.queue_rows(_connection(name="4K"))
    assert signal.status == "unreachable"
    assert signal.detail is not None
    assert "refused MediaMop's API key" in signal.detail


def test_rate_limited_manager_backs_off_rather_than_retrying(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_client(
        monkeypatch,
        {
            "/api/integrations/external/queue": MediaManagerRateLimitedError(
                "HTTP 429",
                retry_after_seconds=30.0,
            )
        },
    )
    port = port_for_kind("deluno")
    assert port is not None
    signal = port.queue_rows(_connection(kind="deluno", name="Main"))
    assert signal.status == "unreachable"
    assert signal.detail is not None
    assert "rate limiting MediaMop" in signal.detail
    assert "about 30s" in signal.detail
    assert "backed off rather than retrying straight away" in signal.detail


def test_deluno_queue_covers_jobs_and_recent_dispatches(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_client(
        monkeypatch,
        {
            "/api/integrations/external/queue": {
                "jobs": [
                    {
                        "mediaType": "movie",
                        "status": "downloading",
                        "targetPath": "/media/movies/Solaris.mkv",
                        "title": "Solaris",
                        "year": 1972,
                    }
                ],
                "dispatches": [
                    {"mediaType": "series", "state": "completed", "path": "/tv/Show/S01E01.mkv", "id": 7},
                ],
            }
        },
    )
    port = port_for_kind("deluno")
    assert port is not None
    signal = port.queue_rows(_connection(kind="deluno", name="Main"))
    assert signal.status == "reported"
    assert [row.scope for row in signal.rows] == ["movie", "tv"]
    movie, episode = signal.rows
    assert movie.payload["outputPath"] == "/media/movies/Solaris.mkv"
    assert movie.payload["media"] == {"title": "Solaris", "year": 1972}
    assert movie.payload["status"] == "downloading"
    # A settled dispatch keeps the manager's own word and does not read as active.
    assert episode.payload["status"] == "completed"
    assert episode.payload["entityId"] == 7


@pytest.mark.parametrize(
    ("reported_state", "expected"),
    [
        ("running", "downloading"),
        ("queued", "downloading"),
        ("importing", "importpending"),
        ("failed", "failed"),
        ("something MediaMop has never heard of", "downloading"),
    ],
)
def test_an_unrecognised_deluno_state_reads_as_still_in_progress(
    monkeypatch: pytest.MonkeyPatch,
    reported_state: str,
    expected: str,
) -> None:
    _patch_client(
        monkeypatch,
        {
            "/api/integrations/external/queue": [
                {"mediaType": "movie", "status": reported_state, "path": "/media/x.mkv"},
            ]
        },
    )
    port = port_for_kind("deluno")
    assert port is not None
    signal = port.queue_rows(_connection(kind="deluno"))
    assert signal.rows[0].payload["status"] == expected


def test_a_deluno_row_without_a_media_type_is_dropped(monkeypatch: pytest.MonkeyPatch) -> None:
    """No scope means no dialect can read it; guessing one would invent a verdict."""

    _patch_client(monkeypatch, {"/api/integrations/external/queue": [{"status": "running", "path": "/x.mkv"}]})
    port = port_for_kind("deluno")
    assert port is not None
    assert port.queue_rows(_connection(kind="deluno")).rows == ()


def test_deluno_cannot_clear_a_delete_and_says_so() -> None:
    port = port_for_kind("deluno")
    assert port is not None
    truth = port.library_truth(_connection(kind="deluno", name="Main"), media_scope="movie")
    assert truth.status == "no_signal"
    assert truth.detail is not None
    assert "Deluno (Main)" in truth.detail


def test_deluno_manifest_narrows_the_scopes_this_connection_is_asked_about(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_client(
        monkeypatch,
        {
            "/api/integrations/external/manifest": {
                "libraries": [{"mediaType": "movie", "path": "/media/movies"}],
            }
        },
    )
    port = port_for_kind("deluno")
    assert port is not None
    described = port.describe(_connection(kind="deluno", name="Main"))
    assert described.status == "reported"
    assert described.capabilities.scopes == frozenset({"movie"})
    assert described.library_roots == ("/media/movies",)


def test_describe_degrades_to_the_static_profile_when_the_manager_is_down(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_client(monkeypatch, {"/api/integrations/external/manifest": OSError("no route to host")})
    port = port_for_kind("deluno")
    assert port is not None
    described = port.describe(_connection(kind="deluno", name="Main"))
    assert described.status == "unreachable"
    assert described.capabilities.scopes == frozenset({"movie", "tv"})
    assert described.detail is not None
    assert "Deluno (Main)" in described.detail


def test_native_speaks_mediamops_own_payload_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_client(
        monkeypatch,
        {
            "/api/integrations/external/queue": {
                "items": [
                    {
                        "media_scope": "tv",
                        "state": "importing",
                        "file_path": "/tv/Show/S01E01.mkv",
                        "release_name": "Show S01E01",
                        "entity_id": 4,
                    }
                ]
            }
        },
    )
    port = port_for_kind("native")
    assert port is not None
    signal = port.queue_rows(_connection(kind="native", name="Home"))
    row = signal.rows[0]
    assert row.scope == "tv"
    assert row.payload["status"] == "importpending"
    assert row.payload["outputPath"] == "/tv/Show/S01E01.mkv"
    assert row.payload["entityId"] == 4
