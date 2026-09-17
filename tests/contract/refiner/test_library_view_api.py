"""Issue #568's Library view, judged from outside a running server.

The scan index is seeded straight into ``library_files`` (with the derived columns and facet rows a scan
writes) while the server is stopped, because what is under test here is the reading of that index: the
Overview's totals and breakdowns, the Files table's paging, sorting and facet filters, and the Problems
grouping. Running a real scan needs real media files and is covered by the .NET suite instead.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from tests.contract.refiner import _helpers as h
from tests.contract.support import seed
from tests.contract.support.client import API, WeirClient

LIBRARIES = f"{API}/refiner/libraries"

FILM_PROBE = json.dumps(
    {
        "streams": [
            {"codec_type": "video", "codec_name": "hevc", "width": 3840, "height": 2160},
            {
                "codec_type": "audio",
                "codec_name": "eac3",
                "channels": 6,
                "channel_layout": "5.1(side)",
                "tags": {"language": "eng"},
            },
            {"codec_type": "audio", "codec_name": "aac", "channels": 2, "tags": {"language": "jpn"}},
            {"codec_type": "subtitle", "codec_name": "subrip", "tags": {"language": "eng"}},
        ]
    }
)

SHOW_PROBE = json.dumps(
    {
        "streams": [
            {"codec_type": "video", "codec_name": "h264", "width": 1920, "height": 1080},
            {"codec_type": "audio", "codec_name": "ac3", "channels": 6, "tags": {"language": "eng"}},
        ]
    }
)


#: One seeded row: the columns a scan derives from the probe JSON, and the facet rows it writes with them.
#: Kept in the test rather than computed, so a change to the server's own derivation shows up here as a
#: failure instead of being mirrored automatically.
FACTS: dict[str, dict[str, Any]] = {
    FILM_PROBE: {
        "video_codec": "hevc",
        "video_height": 2160,
        "resolution_class": "4k",
        "audio_track_count": 2,
        "subtitle_track_count": 1,
        "audio_summary": "eng eac3 5.1, jpn aac stereo",
        "subtitle_summary": "eng",
        "facets": [
            ("video_codec", "hevc"),
            ("resolution", "4k"),
            ("audio", "eac3 5.1"),
            ("audio", "aac stereo"),
            ("audio_language", "eng"),
            ("audio_language", "jpn"),
            ("subtitle_language", "eng"),
        ],
    },
    SHOW_PROBE: {
        "video_codec": "h264",
        "video_height": 1080,
        "resolution_class": "1080p",
        "audio_track_count": 1,
        "subtitle_track_count": 0,
        "audio_summary": "eng ac3 5.1",
        "subtitle_summary": None,
        "facets": [
            ("video_codec", "h264"),
            ("resolution", "1080p"),
            ("audio", "ac3 5.1"),
            ("audio_language", "eng"),
        ],
    },
    "": {
        "video_codec": "unknown",
        "video_height": None,
        "resolution_class": "unknown",
        "audio_track_count": 0,
        "subtitle_track_count": 0,
        "audio_summary": None,
        "subtitle_summary": None,
        "facets": [("video_codec", "unknown"), ("resolution", "unknown")],
    },
}


def _insert_file(
    conn: Any,
    *,
    library_id: int,
    path: str,
    classification: str,
    probe_json: str,
    size_bytes: int = 1_000_000,
    link_count: int | None = None,
    problem_kind: str | None = None,
    manager_kind: str | None = None,
    manager_title: str | None = None,
) -> None:
    facts = FACTS[probe_json]
    cur = conn.execute(
        "INSERT INTO library_files (library_id, path, size_bytes, mtime, classification, "
        "removed_audio_tracks, removed_subtitle_tracks, estimated_bytes_saved, probe_json, video_codec, "
        "video_height, resolution_class, audio_track_count, subtitle_track_count, audio_summary, "
        "subtitle_summary, link_count, problem_kind, manager_kind, manager_title) "
        "VALUES (?, ?, ?, 1700000000, ?, 0, 0, 0, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            library_id,
            path,
            size_bytes,
            classification,
            probe_json,
            facts["video_codec"],
            facts["video_height"],
            facts["resolution_class"],
            facts["audio_track_count"],
            facts["subtitle_track_count"],
            facts["audio_summary"],
            facts["subtitle_summary"],
            link_count,
            problem_kind,
            manager_kind,
            manager_title,
        ),
    )
    file_id = int(cur.lastrowid or 0)
    for facet, value in facts["facets"]:
        conn.execute(
            "INSERT OR IGNORE INTO library_file_facets (library_id, library_file_id, facet, value) VALUES (?, ?, ?, ?)",
            (library_id, file_id, facet, value),
        )


@pytest.fixture
def scanned(server, client_factory) -> tuple[WeirClient, int]:
    """
    A library with a small, deliberately varied scan index already recorded, and a client signed in
    afterwards: ``seed.stopped`` restarts the server on a new port, so a client made before it would be
    pointing at a port nothing is listening on any more.
    """

    with seed.stopped(server) as conn:
        library_id = h.first_library_id(conn)
        conn.execute("DELETE FROM library_files WHERE library_id = ?", (library_id,))
        _insert_file(
            conn,
            library_id=library_id,
            path="/lib/film.mkv",
            classification="would_change",
            probe_json=FILM_PROBE,
            size_bytes=3_000,
            manager_kind="radarr",
            manager_title="Blade Runner 2049",
        )
        _insert_file(
            conn,
            library_id=library_id,
            path="/lib/show.mkv",
            classification="matches",
            probe_json=SHOW_PROBE,
            size_bytes=1_000,
        )
        _insert_file(
            conn,
            library_id=library_id,
            path="/lib/seeding.mkv",
            classification="would_change",
            probe_json=SHOW_PROBE,
            size_bytes=2_000,
            link_count=2,
        )
        _insert_file(
            conn,
            library_id=library_id,
            path="/lib/broken.mkv",
            classification="cannot_process",
            probe_json="",
            size_bytes=500,
            problem_kind="unreadable",
        )
    return h.signed_in_admin(server, client_factory), library_id


def _overview(c: WeirClient, library_id: int) -> dict[str, Any]:
    r = c.get(f"{LIBRARIES}/{library_id}/library-overview")
    assert r.status_code == 200, r.text
    return r.json()


def _files(c: WeirClient, library_id: int, query: str = "") -> dict[str, Any]:
    r = c.get(f"{LIBRARIES}/{library_id}/library-files" + (f"?{query}" if query else ""))
    assert r.status_code == 200, r.text
    return r.json()


def _paths(body: dict[str, Any]) -> list[str]:
    return [f["path"] for f in body["files"]]


def test_the_library_view_endpoints_need_a_signed_in_user(server, client_factory, scanned) -> None:
    _admin, scanned_library = scanned
    # Built after `scanned`, which restarts the server on a new port.
    anonymous = client_factory(server)
    for suffix in ("library-overview", "library-problems", "library-files"):
        assert anonymous.get(f"{LIBRARIES}/{scanned_library}/{suffix}").status_code == 401


def test_a_library_that_does_not_exist_is_a_404(scanned) -> None:
    admin, scanned_library = scanned
    missing = scanned_library + 9_000
    for suffix in ("library-overview", "library-problems"):
        assert admin.get(f"{LIBRARIES}/{missing}/{suffix}").status_code == 404


def test_the_overview_totals_count_every_scanned_file_and_its_size(scanned) -> None:
    admin, scanned_library = scanned
    totals = _overview(admin, scanned_library)["totals"]

    assert totals["files"] == 4
    assert totals["size_bytes"] == 6_500
    assert totals["matches"] == 1
    assert totals["would_change"] == 2
    assert totals["cannot_process"] == 1


def test_every_breakdown_is_returned_with_counts_and_shares(scanned) -> None:
    admin, scanned_library = scanned
    breakdowns = _overview(admin, scanned_library)["breakdowns"]

    assert set(breakdowns) == {
        "video_codec",
        "resolution",
        "audio",
        "audio_language",
        "subtitle_language",
    }

    codecs = {row["value"]: row for row in breakdowns["video_codec"]}
    assert codecs["h264"]["files"] == 2
    assert codecs["hevc"]["files"] == 1
    assert codecs["unknown"]["files"] == 1
    assert codecs["h264"]["share"] == pytest.approx(0.5)
    # Biggest group first, so the bars read top-down.
    assert breakdowns["video_codec"][0]["value"] == "h264"

    languages = {row["value"]: row["files"] for row in breakdowns["audio_language"]}
    # A file with two English audio tracks still counts once.
    assert languages == {"eng": 3, "jpn": 1}

    audio = {row["value"]: row["files"] for row in breakdowns["audio"]}
    assert audio == {"ac3 5.1": 2, "aac stereo": 1, "eac3 5.1": 1}


def test_a_file_reports_the_media_facts_the_table_shows(scanned) -> None:
    admin, scanned_library = scanned
    film = next(f for f in _files(admin, scanned_library)["files"] if f["path"] == "/lib/film.mkv")

    assert film["video_codec"] == "hevc"
    assert film["resolution_class"] == "4k"
    assert film["video_height"] == 2160
    assert film["audio_track_count"] == 2
    assert film["audio_summary"] == "eng eac3 5.1, jpn aac stereo"
    assert film["subtitle_summary"] == "eng"
    assert film["manager_title"] == "Blade Runner 2049"


def test_a_file_with_no_cached_probe_reads_unknown(scanned) -> None:
    admin, scanned_library = scanned
    broken = next(f for f in _files(admin, scanned_library)["files"] if f["path"] == "/lib/broken.mkv")

    assert broken["video_codec"] == "unknown"
    assert broken["resolution_class"] == "unknown"
    assert broken["audio_summary"] is None
    assert broken["problem_kind"] == "unreadable"


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("audio_language=jpn", ["/lib/film.mkv"]),
        ("resolution=1080p", ["/lib/seeding.mkv", "/lib/show.mkv"]),
        ("video_codec=h264&resolution=1080p", ["/lib/seeding.mkv", "/lib/show.mkv"]),
        ("video_codec=hevc&resolution=1080p", []),
        ("subtitle_language=eng", ["/lib/film.mkv"]),
        ("audio=ac3 5.1", ["/lib/seeding.mkv", "/lib/show.mkv"]),
        ("classification=would_change", ["/lib/film.mkv", "/lib/seeding.mkv"]),
        ("problem=seeding", ["/lib/seeding.mkv"]),
        ("problem=unreadable", ["/lib/broken.mkv"]),
        ("manager=radarr", ["/lib/film.mkv"]),
        ("q=runner", ["/lib/film.mkv"]),
        ("q=seed", ["/lib/seeding.mkv"]),
        # An unknown facet name is ignored rather than narrowing (or reaching) the query.
        ("not_a_facet=hevc", ["/lib/broken.mkv", "/lib/film.mkv", "/lib/seeding.mkv", "/lib/show.mkv"]),
    ],
)
def test_a_facet_filter_narrows_the_files_listing(scanned, query, expected) -> None:
    admin, scanned_library = scanned
    assert _paths(_files(admin, scanned_library, query)) == expected


def test_a_filter_narrows_the_filtered_totals_but_not_the_header_summary(scanned) -> None:
    admin, scanned_library = scanned
    body = _files(admin, scanned_library, "audio_language=jpn")

    assert body["total"] == 1
    assert body["filtered"]["files"] == 1
    assert body["filtered"]["size_bytes"] == 3_000
    assert body["summary"]["files"] == 4
    assert body["summary"]["size_bytes"] == 6_500


def test_files_are_sorted_by_the_named_column_in_both_directions(scanned) -> None:
    admin, scanned_library = scanned
    ascending = _files(admin, scanned_library, "sort=size&direction=asc")
    descending = _files(admin, scanned_library, "sort=size&direction=desc")

    assert ascending["sort"] == "size"
    assert ascending["direction"] == "asc"
    assert _paths(ascending) == [
        "/lib/broken.mkv",
        "/lib/show.mkv",
        "/lib/seeding.mkv",
        "/lib/film.mkv",
    ]
    assert _paths(descending) == list(reversed(_paths(ascending)))


def test_an_unknown_sort_falls_back_to_the_path_rather_than_failing(scanned) -> None:
    admin, scanned_library = scanned
    body = _files(admin, scanned_library, "sort=size_bytes;DROP+TABLE+library_files")

    assert body["sort"] == "path"
    assert _paths(body) == ["/lib/broken.mkv", "/lib/film.mkv", "/lib/seeding.mkv", "/lib/show.mkv"]
    # Proof the rejected text never reached the database: the rows are all still there.
    assert body["summary"]["files"] == 4


def test_paging_returns_every_row_exactly_once(scanned) -> None:
    admin, scanned_library = scanned
    first = _files(admin, scanned_library, "page_size=3")
    second = _files(admin, scanned_library, "page_size=3&page=2")

    assert first["page"] == 1
    assert first["page_size"] == 3
    assert first["total"] == 4
    assert len(first["files"]) == 3
    assert _paths(second) == ["/lib/show.mkv"]
    assert sorted(_paths(first) + _paths(second)) == [
        "/lib/broken.mkv",
        "/lib/film.mkv",
        "/lib/seeding.mkv",
        "/lib/show.mkv",
    ]


def test_a_page_size_beyond_the_cap_is_clamped(scanned) -> None:
    admin, scanned_library = scanned
    body = _files(admin, scanned_library, "page_size=100000&page=0")

    assert body["page_size"] == 200
    assert body["page"] == 1


def test_problems_are_grouped_by_reason_with_something_to_do_about_each(scanned) -> None:
    admin, scanned_library = scanned
    r = admin.get(f"{LIBRARIES}/{scanned_library}/library-problems")
    assert r.status_code == 200, r.text
    body = r.json()

    groups = {g["kind"]: g for g in body["groups"]}
    assert set(groups) == {"seeding", "unreadable"}
    assert body["total"] == 2
    assert groups["seeding"]["files"] == 1
    assert groups["seeding"]["sample_paths"] == ["/lib/seeding.mkv"]
    assert groups["seeding"]["what_to_do"]
    assert groups["unreadable"]["title"]
    # The same groups reach the Overview, so its "N files need a look" line agrees with this view.
    assert {g["kind"] for g in _overview(admin, scanned_library)["problems"]} == set(groups)


def test_allowing_hardlinked_files_stops_seeding_being_reported_as_a_problem(scanned) -> None:
    admin, scanned_library = scanned
    settings = admin.get(f"{LIBRARIES}/{scanned_library}/library-settings").json()
    r = admin.put_csrf(
        f"{LIBRARIES}/{scanned_library}/library-settings",
        {
            "library_folders": settings["library_folders"],
            "clean_hardlinked_files": True,
        },
    )
    assert r.status_code == 200, r.text

    kinds = {g["kind"] for g in admin.get(f"{LIBRARIES}/{scanned_library}/library-problems").json()["groups"]}
    assert kinds == {"unreadable"}


def test_an_unscanned_library_answers_with_empty_totals(admin, server) -> None:
    r = admin.post_csrf(
        LIBRARIES,
        {
            "enabled": False,
            "name": "Never scanned",
            "media_type": "movie",
            "watched_folder": "/srv/never/in",
            "output_folder": "/srv/never/out",
        },
    )
    assert r.status_code == 201, r.text
    library_id = r.json()["id"]

    body = _overview(admin, library_id)

    assert body["totals"]["files"] == 0
    assert body["folders_configured"] == 0
    assert body["scan"] is None
    assert body["breakdowns"]["video_codec"] == []
    assert body["problems"] == []
    assert _files(admin, library_id)["files"] == []


def test_the_new_views_are_in_the_published_openapi_document(client) -> None:
    documented = client.get("/openapi.json").json()["paths"]

    for path in (
        "/api/v1/refiner/libraries/{library_id}/library-overview",
        "/api/v1/refiner/libraries/{library_id}/library-problems",
    ):
        assert path in documented, f"{path} is not in the served OpenAPI document"
        assert "get" in documented[path]
