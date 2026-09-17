"""The read-only Direct Play badge (#467).

Two properties matter most. The answers must be honest: a device's list names its source, a fact
nobody measured is "unknown" rather than "no", and partial support is "maybe". And the feature must
never grow teeth: nothing that processes a file may import it.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from sqlalchemy import delete, select
from starlette.testclient import TestClient

import mediamop.refiner as refiner_pkg
from mediamop.core.config import MediaMopSettings
from mediamop.core.db import create_db_engine, create_session_factory
from mediamop.refiner.direct_play import (
    MediaFacts,
    container_for_path,
    evaluate,
    load_device_profiles,
)
from mediamop.refiner.file_remux_pass.run import _video_bit_depth
from mediamop.refiner.refiner_file_state_model import RefinerFileRow
from mediamop.refiner.refiner_file_state_service import record_measured_media_facts
from mediamop.refiner.refiner_library_model import RefinerLibraryRow
from tests.integration_helpers import auth_post, auth_put
from tests.integration_helpers import csrf as fetch_csrf

# --- the device list ------------------------------------------------------------------------------------


def test_every_shipped_device_names_its_source_and_is_unique() -> None:
    profiles = load_device_profiles(None)
    assert {p.id for p in profiles} >= {
        "apple_tv_4k",
        "lg_webos",
        "samsung_tizen_2024",
        "iphone_ipad",
        "chromecast_google_tv",
        "fire_tv",
        "roku",
        "web_browser",
    }
    assert len({p.id for p in profiles}) == len(profiles)
    for profile in profiles:
        assert profile.source.startswith("https://"), profile.id
        assert profile.containers_yes, profile.id


def test_an_operators_own_list_replaces_the_shipped_one_without_a_release(tmp_path: Path) -> None:
    (tmp_path / "direct-play-devices.json").write_text(
        json.dumps(
            {
                "devices": [
                    {
                        "id": "shield",
                        "name": "Shield",
                        "source": "https://example.test/shield",
                        "containers": {"yes": ["mkv"]},
                        "video": {"hevc": {}},
                        "audio": {"yes": ["truehd"]},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    assert [p.id for p in load_device_profiles(str(tmp_path))] == ["shield"]


def test_an_unreadable_own_list_falls_back_to_the_shipped_one(tmp_path: Path) -> None:
    (tmp_path / "direct-play-devices.json").write_text("{not json", encoding="utf-8")
    assert "apple_tv_4k" in {p.id for p in load_device_profiles(str(tmp_path))}


# --- the answers -----------------------------------------------------------------------------------------


def _device(device_id: str):  # type: ignore[no-untyped-def]
    return next(p for p in load_device_profiles(None) if p.id == device_id)


def _facts(**over: object) -> MediaFacts:
    base: dict[str, object] = {
        "container": "mp4",
        "video_codec": "hevc",
        "video_height": 2160,
        "video_bit_depth": 10,
        "audio_codecs": ("aac",),
    }
    base.update(over)
    return MediaFacts(**base)  # type: ignore[arg-type]


def test_a_file_that_fits_plays_directly() -> None:
    assert evaluate(_device("iphone_ipad"), _facts()).verdict == "yes"


def test_apple_tvs_own_player_does_not_play_mkv_and_says_so() -> None:
    verdict = evaluate(_device("apple_tv_4k"), _facts(container="mkv"))
    assert verdict.verdict == "no"
    assert verdict.reasons == ("cannot play MKV files",)


def test_dts_is_named_as_the_reason_on_a_2024_samsung() -> None:
    verdict = evaluate(_device("samsung_tizen_2024"), _facts(container="mkv", audio_codecs=("dts",)))
    assert verdict.verdict == "no"
    assert verdict.reasons == ("cannot play DTS audio",)


def test_model_dependent_support_is_maybe_not_yes() -> None:
    assert evaluate(_device("lg_webos"), _facts(container="mkv", audio_codecs=("dts",))).verdict == "maybe"
    assert evaluate(_device("roku"), _facts(container="mkv")).verdict == "maybe"


def test_one_unplayable_track_among_playable_ones_is_maybe() -> None:
    verdict = evaluate(_device("iphone_ipad"), _facts(audio_codecs=("aac", "truehd")))
    assert verdict.verdict == "maybe"
    assert verdict.reasons == ("may not play Dolby TrueHD audio on some tracks",)


def test_a_limit_the_source_states_is_applied() -> None:
    verdict = evaluate(_device("apple_tv_4k"), _facts(video_codec="h264", video_bit_depth=10))
    assert verdict.verdict == "no"
    assert "10-bit video is above 8-bit" in verdict.reasons[0]


def test_samsung_plays_hevc_only_in_the_containers_it_names() -> None:
    verdict = evaluate(_device("samsung_tizen_2024"), _facts(container="avi"))
    assert verdict.verdict == "no"
    assert "only in MKV, MP4, TS" in verdict.reasons[0]


def test_a_fact_nobody_measured_is_unknown_never_no() -> None:
    verdict = evaluate(
        _device("roku"), _facts(container="mp4", video_codec="h264", video_bit_depth=8, audio_codecs=None)
    )
    assert verdict.verdict == "unknown"


def test_pcm_variants_count_as_pcm_and_containers_come_from_the_file_name() -> None:
    assert evaluate(_device("apple_tv_4k"), _facts(audio_codecs=("pcm_s24le",))).verdict == "yes"
    assert container_for_path("Film/Film.2020.MKV") == "mkv"
    assert container_for_path("Film/no-extension") is None


@pytest.mark.parametrize(
    ("stream", "expected"),
    [
        ({"bits_per_raw_sample": "10"}, 10),
        ({"pix_fmt": "yuv420p10le"}, 10),
        ({"pix_fmt": "yuv420p"}, 8),
        ({}, None),
    ],
)
def test_bit_depth_is_read_from_the_probe(stream: dict, expected: int | None) -> None:
    assert _video_bit_depth(stream) == expected


# --- it never grows teeth --------------------------------------------------------------------------------


def test_nothing_that_processes_a_file_imports_direct_play() -> None:
    """The badge is information only (#467, #472). Only the read APIs may use it."""

    allowed = {"refiner_files_api.py", "router.py"}
    root = Path(refiner_pkg.__file__).parent
    offenders = sorted(
        str(path.relative_to(root))
        for path in root.rglob("*.py")
        if "direct_play" not in path.parts
        and path.name not in allowed
        and re.search(
            r"^\s*(from|import)\s+mediamop\.modules\.refiner\.direct_play",
            path.read_text(encoding="utf-8"),
            re.MULTILINE,
        )
    )
    assert offenders == [], f"Direct Play must never feed processing: {offenders}"


# --- storing facts and the API ----------------------------------------------------------------------------


def _factory():  # type: ignore[no-untyped-def]
    return create_session_factory(create_db_engine(MediaMopSettings.load()))


@pytest.fixture
def seeded_file() -> None:
    with _factory()() as db:
        db.execute(delete(RefinerFileRow))
        library = db.scalars(select(RefinerLibraryRow).order_by(RefinerLibraryRow.id)).first()
        assert library is not None
        db.add(RefinerFileRow(library_id=library.id, relative_path="Heat/heat.mkv", status="unprocessed"))
        db.commit()
        record_measured_media_facts(
            db,
            relative_path="Heat/heat.mkv",
            video_width=3840,
            video_height=2160,
            video_codec="hevc",
            audio_codecs=["TrueHD", "ac3"],
            video_bit_depth=10,
        )
        db.commit()
        row = db.scalars(select(RefinerFileRow)).one()
        assert (row.audio_codecs, row.video_bit_depth) == ("truehd,ac3", 10)


def _login(client: TestClient) -> TestClient:
    r = auth_post(
        client,
        "/api/v1/auth/login",
        json={"username": "alice", "password": "test-password-strong", "csrf_token": fetch_csrf(client)},
    )
    assert r.status_code == 200, r.text
    return client


def test_choosing_devices_changes_only_the_badge(client_with_admin: TestClient, seeded_file: None) -> None:
    client = _login(client_with_admin)
    listed = client.get("/api/v1/refiner/direct-play/devices")
    assert listed.status_code == 200, listed.text
    assert not any(d["selected"] for d in listed.json()["devices"])
    assert client.get("/api/v1/refiner/files").json()["files"][0]["direct_play"] == []

    saved = auth_put(
        client,
        "/api/v1/refiner/direct-play/devices",
        json={"csrf_token": fetch_csrf(client), "selected": ["apple_tv_4k", "lg_webos", "no_such_device"]},
    )
    assert saved.status_code == 200, saved.text
    assert [d["id"] for d in saved.json()["devices"] if d["selected"]] == ["apple_tv_4k", "lg_webos"]

    badge = {d["device_id"]: d for d in client.get("/api/v1/refiner/files").json()["files"][0]["direct_play"]}
    assert badge["apple_tv_4k"]["verdict"] == "no"
    assert "cannot play MKV files" in badge["apple_tv_4k"]["reasons"]
    assert badge["lg_webos"]["verdict"] == "maybe"

    auth_put(client, "/api/v1/refiner/direct-play/devices", json={"csrf_token": fetch_csrf(client), "selected": []})
