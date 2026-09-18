"""Port of the retired Python backend's tests/test_direct_play.py (the HTTP parts)."""

from __future__ import annotations

from tests.contract.libraries import _helpers as h
from tests.contract.support import seed
from tests.contract.support.client import API

DEVICES = f"{API}/processing/direct-play/devices"
FILES = f"{API}/processing/files"


def test_choosing_devices_changes_only_the_badge(server_factory, client_factory) -> None:
    sut = server_factory()
    with seed.stopped(sut) as conn:
        conn.execute("DELETE FROM files")
        # What a pass records after probing: record_measured_media_facts lower-cases and joins codecs.
        h.insert_file(
            conn,
            library_id=h.first_library_id(conn),
            relative_path="Heat/heat.mkv",
            video_width=3840,
            video_height=2160,
            video_codec="hevc",
            audio_codecs="truehd,ac3",
            video_bit_depth=10,
        )

    client = h.signed_in_admin(sut, client_factory)
    listed = client.get(DEVICES)
    assert listed.status_code == 200, listed.text
    assert not any(d["selected"] for d in listed.json()["devices"])
    assert client.get(FILES).json()["files"][0]["direct_play"] == []

    saved = client.put_csrf(DEVICES, {"selected": ["apple_tv_4k", "lg_webos", "no_such_device"]})
    assert saved.status_code == 200, saved.text
    assert [d["id"] for d in saved.json()["devices"] if d["selected"]] == ["apple_tv_4k", "lg_webos"]

    badge = {d["device_id"]: d for d in client.get(FILES).json()["files"][0]["direct_play"]}
    assert badge["apple_tv_4k"]["verdict"] == "no"
    assert "cannot play MKV files" in badge["apple_tv_4k"]["reasons"]
    assert badge["lg_webos"]["verdict"] == "maybe"

    cleared = client.put_csrf(DEVICES, {"selected": []})
    assert cleared.status_code == 200, cleared.text
    assert not any(d["selected"] for d in cleared.json()["devices"])
