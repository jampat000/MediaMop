"""Basic contract coverage for Refiner endpoints no original backend test exercised over HTTP.

Files, file log and why-held, hardware, maintenance, rule sets, reject support, metadata provider
and Direct Play devices: auth, viewer versus operator, status codes, response keys, round-trips.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from tests.contract.refiner import _helpers as h
from tests.contract.support import seed
from tests.contract.support.client import API, WeirClient

FILES = f"{API}/refiner/files"
RULE_SETS = f"{API}/refiner/rule-sets"
MAINTENANCE = f"{API}/refiner/maintenance"
METADATA = f"{API}/refiner/metadata-provider"
DEVICES = f"{API}/refiner/direct-play/devices"

FILE_KEYS = {
    "id",
    "library_id",
    "library_name",
    "relative_path",
    "status",
    "status_reason",
    "blocked_by_connection",
    "size_bytes",
    "video_codec",
    "video_width",
    "video_height",
    "audio_track_count",
    "subtitle_track_count",
    "duration_seconds",
    "direct_play",
    "progress_percent",
    "progress_message",
    "progress_eta_seconds",
    "failure_class",
    "failure_attempts",
    "quarantined",
    "next_retry_at",
    "output_collision_policy",
    "output_collision_action",
    "output_collision_reason",
    "hold_until",
    "size_changed_at",
    "created_at",
    "updated_at",
    "last_seen_at",
    "last_attempt_at",
}


@pytest.fixture(scope="module", autouse=True)
def seeded(server) -> None:
    """A viewer, and file rows across both seeded libraries (seeded while the server is stopped)."""

    with seed.stopped(server) as conn:
        seed.insert_user(conn, username=h.VIEWER_USERNAME, password=h.VIEWER_PASSWORD, role="viewer")
        movies = int(seed.scalar(conn, "SELECT id FROM refiner_libraries WHERE name = 'Movies'"))
        tv = int(seed.scalar(conn, "SELECT id FROM refiner_libraries WHERE name = 'TV'"))
        alpha = h.insert_file(
            conn,
            library_id=movies,
            relative_path="Alpha/alpha.mkv",
            status="on_hold",
            status_reason="Held for the test.",
            failure_class="execution",
            failure_attempts=3,
            size_bytes=4096,
            last_seen_at=seed.utc_text(),
        )
        h.insert_file(
            conn,
            library_id=movies,
            relative_path="Beta/beta.mkv",
            status="processed",
            last_seen_at=seed.utc_text(datetime.now(UTC) - timedelta(days=400)),
        )
        h.insert_file(conn, library_id=tv, relative_path="Show/S01E01.mkv", status="skipped")
        h.insert_file(
            conn,
            library_id=tv,
            relative_path="Requeue/one.mkv",
            status="processing_failed",
            failure_class="execution",
            failure_attempts=2,
        )
        h.insert_file(conn, library_id=movies, relative_path="BulkRequeue/x1.mkv", status="processing_failed")
        h.insert_file(conn, library_id=movies, relative_path="BulkRequeue/x2.mkv", status="processing_failed")
        conn.execute(
            "INSERT INTO refiner_file_logs (file_id, library_id, relative_path, library_name, outcome, title, "
            "detail_json, recorded_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                alpha,
                movies,
                "Alpha/alpha.mkv",
                "Movies",
                "failed",
                "Remux failed",
                json.dumps({"outcome": "failed", "reason": "boom"}),
                seed.utc_text(),
            ),
        )


@pytest.fixture
def viewer(server, client_factory) -> WeirClient:
    return h.signed_in_viewer(server, client_factory)


def _file(c: WeirClient, relative_path: str) -> dict:
    r = c.get(FILES, params={"path_contains": relative_path})
    assert r.status_code == 200, r.text
    matches = [f for f in r.json()["files"] if f["relative_path"] == relative_path]
    assert len(matches) == 1, r.text
    return matches[0]


# --- files ------------------------------------------------------------------------------------------


def test_files_require_a_session(client) -> None:
    assert client.get(FILES).status_code == 401


def test_files_list_shape(viewer) -> None:
    r = viewer.get(FILES)
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) >= {"files", "status_counts", "returned", "limit"}
    assert body["limit"] == 200
    assert body["returned"] == len(body["files"]) >= 6
    assert isinstance(body["status_counts"], dict)
    assert set(body["files"][0]) >= FILE_KEYS

    alpha = _file(viewer, "Alpha/alpha.mkv")
    assert alpha["library_name"] == "Movies"
    assert alpha["status"] == "on_hold"
    assert alpha["status_reason"] == "Held for the test."
    assert alpha["size_bytes"] == 4096
    assert alpha["failure_attempts"] == 3
    assert alpha["quarantined"] is True
    assert alpha["direct_play"] == []


def test_files_filters(admin) -> None:
    libraries = {row["name"]: row["id"] for row in admin.get(f"{API}/refiner/libraries").json()}

    by_library = admin.get(FILES, params={"library_id": libraries["TV"]}).json()
    assert by_library["files"]
    assert {f["library_id"] for f in by_library["files"]} == {libraries["TV"]}

    processed = admin.get(FILES, params={"file_status": "processed"}).json()
    assert [f["relative_path"] for f in processed["files"]] == ["Beta/beta.mkv"]

    by_path = admin.get(FILES, params={"path_contains": "Alpha"}).json()
    assert [f["relative_path"] for f in by_path["files"]] == ["Alpha/alpha.mkv"]

    # within_days filters on when a scan last saw the file.
    recent = {f["relative_path"] for f in admin.get(FILES, params={"within_days": 30}).json()["files"]}
    assert "Alpha/alpha.mkv" in recent
    assert "Beta/beta.mkv" not in recent
    assert "Show/S01E01.mkv" not in recent

    limited = admin.get(FILES, params={"limit": 1}).json()
    assert limited["returned"] == 1
    assert limited["limit"] == 1
    assert len(limited["files"]) == 1


@pytest.mark.parametrize(
    "params",
    [{"file_status": "not_a_status"}, {"limit": 0}, {"limit": 1001}, {"library_id": 0}, {"within_days": 0}],
)
def test_files_reject_invalid_filters(admin, params: dict) -> None:
    assert admin.get(FILES, params=params).status_code == 422


def test_requeue_one_file(admin, viewer, client_factory, server) -> None:
    target = _file(admin, "Requeue/one.mkv")
    path = f"{FILES}/{target['id']}/requeue"

    anonymous = client_factory(server)
    assert anonymous.post_csrf(path).status_code == 401
    assert viewer.post_csrf(path).status_code == 403
    assert admin.post_csrf(f"{FILES}/999999/requeue").status_code == 404

    r = admin.post_csrf(path)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["requeued"] == 1
    assert body["skipped"] == 0
    assert body["detail"]

    after = _file(admin, "Requeue/one.mkv")
    assert after["status"] == "unprocessed"
    assert after["failure_attempts"] == 0
    assert after["failure_class"] is None
    assert after["status_reason"] == body["detail"]


def test_requeue_without_a_csrf_token_is_refused(admin) -> None:
    target = _file(admin, "Requeue/one.mkv")
    assert admin.post(f"{FILES}/{target['id']}/requeue", json={}).status_code == 422
    assert admin.post(f"{FILES}/{target['id']}/requeue", json={"csrf_token": "forged"}).status_code == 400


def test_bulk_requeue(admin, viewer) -> None:
    bulk = f"{FILES}/requeue"
    assert viewer.post_csrf(bulk, {"path_contains": "BulkRequeue"}).status_code == 403

    nothing = admin.post_csrf(bulk, {"path_contains": "no-file-has-this-in-its-path"})
    assert nothing.status_code == 200, nothing.text
    assert nothing.json()["requeued"] == 0
    assert nothing.json()["skipped"] == 0

    r = admin.post_csrf(bulk, {"path_contains": "BulkRequeue", "file_status": "processing_failed"})
    assert r.status_code == 200, r.text
    assert r.json()["requeued"] == 2
    assert r.json()["skipped"] == 0
    for relative_path in ("BulkRequeue/x1.mkv", "BulkRequeue/x2.mkv"):
        assert _file(admin, relative_path)["status"] == "unprocessed"


def test_file_log(viewer) -> None:
    assert viewer.get(f"{FILES}/999999/log").status_code == 404

    alpha = _file(viewer, "Alpha/alpha.mkv")
    r = viewer.get(f"{FILES}/{alpha['id']}/log")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["file_id"] == alpha["id"]
    assert body["relative_path"] == "Alpha/alpha.mkv"
    assert isinstance(body["retention_days"], int)
    assert len(body["entries"]) == 1
    entry = body["entries"][0]
    assert set(entry) >= {"id", "recorded_at", "outcome", "title", "library_name", "detail", "story"}
    assert entry["outcome"] == "failed"
    assert entry["title"] == "Remux failed"
    assert entry["library_name"] == "Movies"
    assert entry["detail"]["reason"] == "boom"
    assert isinstance(entry["story"], list)

    beta = _file(viewer, "Beta/beta.mkv")
    empty = viewer.get(f"{FILES}/{beta['id']}/log").json()
    assert empty["entries"] == []


def test_file_log_needs_a_session(client) -> None:
    assert client.get(f"{FILES}/1/log").status_code == 401


def test_why_held(viewer, client) -> None:
    assert client.get(f"{FILES}/1/why-held").status_code == 401
    assert viewer.get(f"{FILES}/999999/why-held").status_code == 404

    alpha = _file(viewer, "Alpha/alpha.mkv")
    r = viewer.get(f"{FILES}/{alpha['id']}/why-held")
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) >= {
        "file_id",
        "relative_path",
        "library_name",
        "recorded_status",
        "recorded_reason",
        "verdict",
        "owned",
        "blocked_upstream",
        "blocked_by_connection",
        "queue_row_count",
        "managers_consulted",
        "managers_reporting",
        "managers_without_queue_signal",
        "reasons",
    }
    assert body["file_id"] == alpha["id"]
    assert body["relative_path"] == "Alpha/alpha.mkv"
    assert body["library_name"] == "Movies"
    assert body["recorded_status"] == "on_hold"
    assert body["recorded_reason"] == "Held for the test."
    assert body["verdict"] in {"proceed", "wait_upstream", "not_held", "no_upstream_signal"}
    # No media manager is connected on this install, so nobody was asked.
    assert body["managers_consulted"] == 0
    assert isinstance(body["reasons"], list)


# --- hardware ---------------------------------------------------------------------------------------


def test_hardware_report_from_the_configured_ffmpeg(server_factory, client_factory, fake_ffmpeg) -> None:
    sut = server_factory(env=fake_ffmpeg.env)
    assert client_factory(sut).get(f"{API}/refiner/hardware").status_code == 401

    c = h.signed_in_admin(sut, client_factory)
    r = c.get(f"{API}/refiner/hardware")
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) >= {
        "detected",
        "available_methods",
        "vendors",
        "selectable_vendors",
        "strictness_levels",
        "detail",
    }
    # The fake ffmpeg answers but lists no acceleration methods: asked successfully, nothing on offer.
    assert body["detected"] is True
    assert body["available_methods"] == []
    assert body["vendors"] == []
    assert body["selectable_vendors"] == sorted(body["selectable_vendors"])
    assert body["selectable_vendors"]
    assert body["strictness_levels"]
    assert body["detail"]
    assert any("-hwaccels" in call.get("argv", []) for call in fake_ffmpeg.calls(tool="ffmpeg"))


# --- maintenance ------------------------------------------------------------------------------------


def test_maintenance_state_shape(viewer) -> None:
    r = viewer.get(MAINTENANCE)
    assert r.status_code == 200, r.text
    families = r.json()["families"]
    assert [f["family"] for f in families] == ["work_temp_stale_sweep", "failure_cleanup"]
    for family in families:
        assert set(family) >= {
            "family",
            "enabled",
            "description",
            "pending",
            "running",
            "last_completed_at",
            "last_failed_at",
            "last_error",
        }
        assert isinstance(family["enabled"], bool)
        assert isinstance(family["pending"], int)


def test_maintenance_run_needs_an_operator(viewer, client_factory, server) -> None:
    body = {"family": "work_temp_stale_sweep", "media_scope": "tv"}
    assert client_factory(server).post_csrf(f"{MAINTENANCE}/run", body).status_code == 401
    assert viewer.post_csrf(f"{MAINTENANCE}/run", body).status_code == 403


def test_maintenance_failure_cleanup_is_queued_once(admin) -> None:
    first = admin.post_csrf(f"{MAINTENANCE}/run", {"family": "failure_cleanup", "media_scope": "tv"})
    assert first.status_code == 200, first.text
    assert first.json()["queued"] is True
    assert isinstance(first.json()["job_id"], int)
    assert first.json()["detail"]

    second = admin.post_csrf(f"{MAINTENANCE}/run", {"family": "failure_cleanup", "media_scope": "tv"})
    assert second.status_code == 200, second.text
    assert second.json()["queued"] is False
    assert second.json()["job_id"] == first.json()["job_id"]

    state = {f["family"]: f for f in admin.get(MAINTENANCE).json()["families"]}
    assert state["failure_cleanup"]["pending"] >= 1


def test_maintenance_run_rejects_an_unknown_scope(admin) -> None:
    r = admin.post_csrf(f"{MAINTENANCE}/run", {"family": "work_temp_stale_sweep", "media_scope": "music"})
    assert r.status_code == 422


# --- rule sets --------------------------------------------------------------------------------------


def test_rule_sets_need_a_session(client) -> None:
    assert client.get(RULE_SETS).status_code == 401


def test_rule_set_round_trip(admin, viewer) -> None:
    assert viewer.post_csrf(RULE_SETS, {"name": "Viewer set"}).status_code == 403

    made = admin.post_csrf(
        RULE_SETS, {"name": "Contract round trip", "primary_audio_lang": "eng", "subtitle_mode": "remove_all"}
    )
    assert made.status_code == 201, made.text
    row = made.json()
    assert set(row) >= {
        "id",
        "name",
        "primary_audio_lang",
        "secondary_audio_lang",
        "tertiary_audio_lang",
        "default_audio_slot",
        "remove_commentary",
        "subtitle_mode",
        "subtitle_langs_csv",
        "preserve_forced_subs",
        "preserve_default_subs",
        "audio_preference_mode",
        "audio_sorters_json",
        "subtitle_sorters_json",
        "keep_original_language",
        "remove_images",
        "used_by_library_count",
        "updated_at",
    }
    assert row["name"] == "Contract round trip"
    assert row["primary_audio_lang"] == "eng"
    assert row["subtitle_mode"] == "remove_all"
    assert row["used_by_library_count"] == 0

    listed = {x["id"]: x for x in viewer.get(RULE_SETS).json()}
    assert listed[row["id"]]["name"] == "Contract round trip"

    duplicate = admin.post_csrf(RULE_SETS, {"name": "Contract round trip"})
    assert duplicate.status_code == 400
    assert "already exists" in duplicate.json()["detail"]

    updated = admin.put_csrf(
        f"{RULE_SETS}/{row['id']}", {"name": "Contract round trip", "primary_audio_lang": "jpn", "remove_title": True}
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["primary_audio_lang"] == "jpn"
    assert updated.json()["remove_title"] is True
    assert viewer.put_csrf(f"{RULE_SETS}/{row['id']}", {"name": "x"}).status_code == 403
    assert admin.put_csrf(f"{RULE_SETS}/999999", {"name": "Nope"}).status_code == 404

    assert h.delete_with_body_csrf(viewer, f"{RULE_SETS}/{row['id']}").status_code == 403
    deleted = h.delete_with_body_csrf(admin, f"{RULE_SETS}/{row['id']}")
    assert deleted.status_code == 204, deleted.text
    assert all(x["id"] != row["id"] for x in admin.get(RULE_SETS).json())
    assert h.delete_with_body_csrf(admin, f"{RULE_SETS}/{row['id']}").status_code == 404


def test_rule_set_rejects_invalid_fields(admin) -> None:
    assert admin.post_csrf(RULE_SETS, {"name": "Bad mode", "subtitle_mode": "shred"}).status_code == 422
    assert admin.post_csrf(RULE_SETS, {"name": ""}).status_code == 422
    assert admin.post_csrf(RULE_SETS, {"name": "Extra", "not_a_field": 1}).status_code == 422


# --- reject support ---------------------------------------------------------------------------------


def test_reject_support_for_a_viewer_and_unknown_connections(viewer) -> None:
    r = viewer.get(f"{API}/refiner/reject-support")
    assert r.status_code == 200, r.text
    assert set(r.json()) >= {"available", "reason"}
    unknown = viewer.get(f"{API}/refiner/reject-support", params={"connection_ids": [4242]})
    assert unknown.status_code == 200, unknown.text
    assert unknown.json()["available"] is False
    assert unknown.json()["reason"]


# --- metadata provider ------------------------------------------------------------------------------


def test_metadata_provider_needs_a_session(client) -> None:
    assert client.get(METADATA).status_code == 401


def test_metadata_provider_shape_and_permissions(admin, viewer) -> None:
    r = viewer.get(METADATA)
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) >= {"provider", "base_url", "key_configured", "known_providers"}
    assert "tmdb" in body["known_providers"]
    assert isinstance(body["key_configured"], bool)
    assert body["base_url"]

    assert viewer.put_csrf(METADATA, {"provider": "tmdb", "base_url": "https://x.example"}).status_code == 403
    assert admin.put_csrf(METADATA, {"provider": "imdb"}).status_code == 422
    assert admin.put_csrf(METADATA, {"provider": "tmdb", "surprise": True}).status_code == 422


def test_metadata_provider_cleared_reports_not_configured_without_asking_anyone(admin, viewer) -> None:
    saved = admin.put_csrf(METADATA, {"provider": "", "base_url": "", "api_key": ""})
    assert saved.status_code == 200, saved.text
    assert saved.json()["provider"] == ""
    assert saved.json()["key_configured"] is False
    # An empty base URL falls back to the default provider address.
    assert saved.json()["base_url"]

    assert viewer.post_csrf(f"{METADATA}/test", {}).status_code == 403
    tested = admin.post_csrf(f"{METADATA}/test", {})
    assert tested.status_code == 200, tested.text
    assert tested.json()["status"] == "not_configured"
    assert tested.json()["detail"]


# --- Direct Play devices ----------------------------------------------------------------------------


def test_direct_play_devices_need_a_session(client) -> None:
    assert client.get(DEVICES).status_code == 401


def test_direct_play_devices_shape_and_permissions(admin, viewer) -> None:
    r = viewer.get(DEVICES)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["customised"] is False
    ids = {d["id"] for d in body["devices"]}
    assert {"apple_tv_4k", "lg_webos", "roku", "web_browser"} <= ids
    for device in body["devices"]:
        assert set(device) >= {"id", "name", "source", "note", "selected"}
        assert device["source"].startswith("https://")

    assert viewer.put_csrf(DEVICES, {"selected": ["roku"]}).status_code == 403
    assert admin.put(DEVICES, json={"csrf_token": "forged", "selected": ["roku"]}).status_code == 400

    saved = admin.put_csrf(DEVICES, {"selected": ["roku"]})
    assert saved.status_code == 200, saved.text
    assert [d["id"] for d in saved.json()["devices"] if d["selected"]] == ["roku"]
    assert [d["id"] for d in viewer.get(DEVICES).json()["devices"] if d["selected"]] == ["roku"]
    assert admin.put_csrf(DEVICES, {"selected": []}).status_code == 200
