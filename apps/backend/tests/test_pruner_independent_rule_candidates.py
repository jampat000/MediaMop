"""Independent genre / studio / people / year preview collectors (Jellyfin/Emby + Plex)."""

from __future__ import annotations

from unittest.mock import patch

import mediamop.modules.pruner.pruner_media_library as pruner_media_library
from mediamop.modules.pruner.pruner_constants import (
    MEDIA_SCOPE_MOVIES,
    MEDIA_SCOPE_TV,
    RULE_FAMILY_GENRE_MATCH_REPORTED,
    RULE_FAMILY_PEOPLE_MATCH_REPORTED,
    RULE_FAMILY_STUDIO_MATCH_REPORTED,
    RULE_FAMILY_YEAR_RANGE_MATCH_REPORTED,
)
from mediamop.modules.pruner.pruner_independent_rule_candidates import (
    list_jf_emby_genre_match_candidates,
    list_jf_emby_people_match_candidates,
    list_jf_emby_studio_match_candidates,
    list_jf_emby_year_range_match_candidates,
    list_plex_genre_match_candidates,
    list_plex_people_match_candidates,
    list_plex_studio_match_candidates,
    list_plex_year_range_match_candidates,
)
from mediamop.modules.pruner.pruner_media_library import preview_payload_json


def test_preview_payload_independent_rules_empty_selection_unsupported() -> None:
    out, msg, cands, trunc = preview_payload_json(
        provider="jellyfin",
        base_url="http://jf",
        media_scope=MEDIA_SCOPE_TV,
        secrets={"api_key": "k"},
        max_items=10,
        rule_family_id=RULE_FAMILY_GENRE_MATCH_REPORTED,
        preview_include_genres=[],
    )
    assert out == "unsupported" and cands == [] and not trunc
    assert "No genres selected" in msg

    out, msg, cands, trunc = preview_payload_json(
        provider="jellyfin",
        base_url="http://jf",
        media_scope=MEDIA_SCOPE_TV,
        secrets={"api_key": "k"},
        max_items=10,
        rule_family_id=RULE_FAMILY_STUDIO_MATCH_REPORTED,
        preview_include_studios=[],
    )
    assert out == "unsupported" and "No studios selected" in msg

    out, msg, cands, trunc = preview_payload_json(
        provider="jellyfin",
        base_url="http://jf",
        media_scope=MEDIA_SCOPE_TV,
        secrets={"api_key": "k"},
        max_items=10,
        rule_family_id=RULE_FAMILY_PEOPLE_MATCH_REPORTED,
        preview_include_people=[],
    )
    assert out == "unsupported" and "No people entered" in msg

    out, msg, cands, trunc = preview_payload_json(
        provider="plex",
        base_url="http://plex",
        media_scope=MEDIA_SCOPE_MOVIES,
        secrets={"auth_token": "t"},
        max_items=10,
        rule_family_id=RULE_FAMILY_YEAR_RANGE_MATCH_REPORTED,
        preview_year_min=None,
        preview_year_max=None,
    )
    assert out == "unsupported" and "No year range set" in msg


def test_list_jf_emby_genre_match_tv_and_movies() -> None:
    def page_tv(*, start_index: int, **_kw: object) -> dict:
        if start_index > 0:
            return {"Items": [], "TotalRecordCount": 1}
        return {
            "Items": [
                {
                    "Id": "ep1",
                    "Name": "Pilot",
                    "SeriesName": "S",
                    "ParentIndexNumber": 1,
                    "IndexNumber": 1,
                    "Genres": ["Drama"],
                },
            ],
            "TotalRecordCount": 1,
        }

    def page_mov(*, start_index: int, **_kw: object) -> dict:
        if start_index > 0:
            return {"Items": [], "TotalRecordCount": 1}
        return {
            "Items": [
                {"Id": "m1", "Name": "Film", "ProductionYear": 2005, "Genres": ["Comedy"]},
            ],
            "TotalRecordCount": 1,
        }

    with patch.object(pruner_media_library, "_items_page", page_tv):
        rows, trunc = list_jf_emby_genre_match_candidates(
            base_url="http://jf",
            api_key="k",
            media_scope=MEDIA_SCOPE_TV,
            max_items=10,
            preview_include_genres=["drama"],
        )
    assert not trunc and len(rows) == 1
    assert rows[0]["granularity"] == "episode" and rows[0]["item_id"] == "ep1"

    with patch.object(pruner_media_library, "_items_page", page_mov):
        rows, trunc = list_jf_emby_genre_match_candidates(
            base_url="http://jf",
            api_key="k",
            media_scope=MEDIA_SCOPE_MOVIES,
            max_items=10,
            preview_include_genres=["comedy"],
        )
    assert not trunc and len(rows) == 1
    assert rows[0]["granularity"] == "movie_item" and rows[0]["item_id"] == "m1"


def test_list_jf_emby_studio_match_tv_and_movies() -> None:
    def page_tv(*, start_index: int, **_kw: object) -> dict:
        if start_index > 0:
            return {"Items": [], "TotalRecordCount": 1}
        return {
            "Items": [
                {
                    "Id": "e",
                    "Name": "E",
                    "SeriesName": "S",
                    "ParentIndexNumber": 1,
                    "IndexNumber": 2,
                    "Studios": [{"Name": "Acme"}],
                },
            ],
            "TotalRecordCount": 1,
        }

    def page_mov(*, start_index: int, **_kw: object) -> dict:
        if start_index > 0:
            return {"Items": [], "TotalRecordCount": 1}
        return {
            "Items": [{"Id": "mv", "Name": "M", "ProductionYear": 2011, "Studios": [{"Name": "Beta"}]}],
            "TotalRecordCount": 1,
        }

    with patch.object(pruner_media_library, "_items_page", page_tv):
        rows, _ = list_jf_emby_studio_match_candidates(
            base_url="http://jf",
            api_key="k",
            media_scope=MEDIA_SCOPE_TV,
            max_items=10,
            preview_include_studios=["acme"],
        )
    assert rows[0]["granularity"] == "episode"

    with patch.object(pruner_media_library, "_items_page", page_mov):
        rows, _ = list_jf_emby_studio_match_candidates(
            base_url="http://jf",
            api_key="k",
            media_scope=MEDIA_SCOPE_MOVIES,
            max_items=10,
            preview_include_studios=["beta"],
        )
    assert rows[0]["granularity"] == "movie_item"


def test_list_jf_emby_people_match_tv_and_movies() -> None:
    def page_tv(*, start_index: int, **_kw: object) -> dict:
        if start_index > 0:
            return {"Items": [], "TotalRecordCount": 1}
        return {
            "Items": [
                {
                    "Id": "e",
                    "Name": "E",
                    "SeriesName": "S",
                    "ParentIndexNumber": 1,
                    "IndexNumber": 1,
                    "People": [{"Name": "Pat Example", "Type": "Actor"}],
                },
            ],
            "TotalRecordCount": 1,
        }

    def page_mov(*, start_index: int, **_kw: object) -> dict:
        if start_index > 0:
            return {"Items": [], "TotalRecordCount": 1}
        return {
            "Items": [
                {
                    "Id": "m",
                    "Name": "M",
                    "ProductionYear": 2000,
                    "People": [{"Name": "Pat Example", "Type": "Director"}],
                },
            ],
            "TotalRecordCount": 1,
        }

    with patch.object(pruner_media_library, "_items_page", page_tv):
        rows, _ = list_jf_emby_people_match_candidates(
            base_url="http://jf",
            api_key="k",
            media_scope=MEDIA_SCOPE_TV,
            max_items=10,
            preview_include_people=["pat example"],
            preview_include_people_roles=["cast"],
        )
    assert rows[0]["granularity"] == "episode"

    with patch.object(pruner_media_library, "_items_page", page_mov):
        rows, _ = list_jf_emby_people_match_candidates(
            base_url="http://jf",
            api_key="k",
            media_scope=MEDIA_SCOPE_MOVIES,
            max_items=10,
            preview_include_people=["pat example"],
            preview_include_people_roles=["director"],
        )
    assert rows[0]["granularity"] == "movie_item"


def test_list_jf_emby_year_range_tv_and_movies() -> None:
    def page_tv(*, start_index: int, **_kw: object) -> dict:
        if start_index > 0:
            return {"Items": [], "TotalRecordCount": 1}
        return {
            "Items": [
                {
                    "Id": "e",
                    "Name": "E",
                    "SeriesName": "S",
                    "ParentIndexNumber": 1,
                    "IndexNumber": 1,
                    "ProductionYear": 2015,
                },
            ],
            "TotalRecordCount": 1,
        }

    def page_mov(*, start_index: int, **_kw: object) -> dict:
        if start_index > 0:
            return {"Items": [], "TotalRecordCount": 1}
        return {
            "Items": [{"Id": "m", "Name": "M", "ProductionYear": 1999}],
            "TotalRecordCount": 1,
        }

    with patch.object(pruner_media_library, "_items_page", page_tv):
        rows, _ = list_jf_emby_year_range_match_candidates(
            base_url="http://jf",
            api_key="k",
            media_scope=MEDIA_SCOPE_TV,
            max_items=10,
            preview_year_min=2010,
            preview_year_max=2020,
        )
    assert rows[0]["granularity"] == "episode"

    with patch.object(pruner_media_library, "_items_page", page_mov):
        rows, _ = list_jf_emby_year_range_match_candidates(
            base_url="http://jf",
            api_key="k",
            media_scope=MEDIA_SCOPE_MOVIES,
            max_items=10,
            preview_year_min=None,
            preview_year_max=2000,
        )
    assert rows[0]["granularity"] == "movie_item"


def _plex_fake_get_for_leaves(meta_ep: dict, meta_mov: dict, *, movies: bool) -> object:
    def fake_get(url: str, headers: dict[str, str]) -> tuple[int, dict]:  # noqa: ARG001
        if "sections" in url and "allLeaves" not in url:
            return 200, {"MediaContainer": {"Directory": [{"type": "show" if not movies else "movie", "key": "1"}]}}
        return (
            200,
            {
                "MediaContainer": {
                    "Metadata": [meta_ep if not movies else meta_mov],
                    "totalSize": 1,
                },
            },
        )

    return fake_get


def test_list_plex_genre_match_tv_and_movies() -> None:
    ep = {
        "type": "episode",
        "ratingKey": "10",
        "grandparentTitle": "Show",
        "parentIndex": 1,
        "index": 2,
        "title": "Ep",
        "Genre": [{"tag": "Drama"}],
    }
    mov = {
        "type": "movie",
        "ratingKey": "20",
        "title": "Film",
        "year": 2001,
        "Genre": [{"tag": "Comedy"}],
    }
    with patch(
        "mediamop.modules.pruner.pruner_independent_rule_candidates.http_get_json",
        _plex_fake_get_for_leaves(ep, mov, movies=False),
    ):
        rows, _ = list_plex_genre_match_candidates(
            base_url="http://plex",
            auth_token="t",
            media_scope=MEDIA_SCOPE_TV,
            max_items=10,
            preview_include_genres=["drama"],
        )
    assert rows[0]["granularity"] == "episode" and rows[0]["item_id"] == "10"

    with patch(
        "mediamop.modules.pruner.pruner_independent_rule_candidates.http_get_json",
        _plex_fake_get_for_leaves(ep, mov, movies=True),
    ):
        rows, _ = list_plex_genre_match_candidates(
            base_url="http://plex",
            auth_token="t",
            media_scope=MEDIA_SCOPE_MOVIES,
            max_items=10,
            preview_include_genres=["comedy"],
        )
    assert rows[0]["granularity"] == "movie_item" and rows[0]["item_id"] == "20"


def test_list_plex_studio_match_tv_and_movies() -> None:
    ep = {
        "type": "episode",
        "ratingKey": "1",
        "grandparentTitle": "S",
        "parentIndex": 1,
        "index": 1,
        "title": "E",
        "Studio": [{"tag": "Acme"}],
    }
    mov = {"type": "movie", "ratingKey": "2", "title": "M", "year": 2010, "Studio": [{"tag": "Beta"}]}
    with patch(
        "mediamop.modules.pruner.pruner_independent_rule_candidates.http_get_json",
        _plex_fake_get_for_leaves(ep, mov, movies=False),
    ):
        rows, _ = list_plex_studio_match_candidates(
            base_url="http://plex",
            auth_token="t",
            media_scope=MEDIA_SCOPE_TV,
            max_items=10,
            preview_include_studios=["acme"],
        )
    assert rows[0]["granularity"] == "episode"

    with patch(
        "mediamop.modules.pruner.pruner_independent_rule_candidates.http_get_json",
        _plex_fake_get_for_leaves(ep, mov, movies=True),
    ):
        rows, _ = list_plex_studio_match_candidates(
            base_url="http://plex",
            auth_token="t",
            media_scope=MEDIA_SCOPE_MOVIES,
            max_items=10,
            preview_include_studios=["beta"],
        )
    assert rows[0]["granularity"] == "movie_item"


def test_list_plex_people_match_tv_and_movies() -> None:
    ep = {
        "type": "episode",
        "ratingKey": "3",
        "grandparentTitle": "S",
        "parentIndex": 1,
        "index": 1,
        "title": "E",
        "Role": [{"tag": "Pat Actor"}],
    }
    mov = {
        "type": "movie",
        "ratingKey": "4",
        "title": "M",
        "year": 2000,
        "Writer": [{"tag": "Pat Actor"}],
    }
    with patch(
        "mediamop.modules.pruner.pruner_independent_rule_candidates.http_get_json",
        _plex_fake_get_for_leaves(ep, mov, movies=False),
    ):
        rows, _ = list_plex_people_match_candidates(
            base_url="http://plex",
            auth_token="t",
            media_scope=MEDIA_SCOPE_TV,
            max_items=10,
            preview_include_people=["pat actor"],
            preview_include_people_roles=["cast"],
        )
    assert rows[0]["granularity"] == "episode"

    with patch(
        "mediamop.modules.pruner.pruner_independent_rule_candidates.http_get_json",
        _plex_fake_get_for_leaves(ep, mov, movies=True),
    ):
        rows, _ = list_plex_people_match_candidates(
            base_url="http://plex",
            auth_token="t",
            media_scope=MEDIA_SCOPE_MOVIES,
            max_items=10,
            preview_include_people=["pat actor"],
            preview_include_people_roles=None,
        )
    assert rows[0]["granularity"] == "movie_item"


def test_list_plex_year_range_tv_and_movies() -> None:
    ep = {
        "type": "episode",
        "ratingKey": "5",
        "grandparentTitle": "S",
        "parentIndex": 1,
        "index": 1,
        "title": "E",
        "year": 2012,
    }
    mov = {"type": "movie", "ratingKey": "6", "title": "M", "year": 1995}
    with patch(
        "mediamop.modules.pruner.pruner_independent_rule_candidates.http_get_json",
        _plex_fake_get_for_leaves(ep, mov, movies=False),
    ):
        rows, _ = list_plex_year_range_match_candidates(
            base_url="http://plex",
            auth_token="t",
            media_scope=MEDIA_SCOPE_TV,
            max_items=10,
            preview_year_min=2010,
            preview_year_max=2020,
        )
    assert rows[0]["granularity"] == "episode"

    with patch(
        "mediamop.modules.pruner.pruner_independent_rule_candidates.http_get_json",
        _plex_fake_get_for_leaves(ep, mov, movies=True),
    ):
        rows, _ = list_plex_year_range_match_candidates(
            base_url="http://plex",
            auth_token="t",
            media_scope=MEDIA_SCOPE_MOVIES,
            max_items=10,
            preview_year_min=None,
            preview_year_max=2000,
        )
    assert rows[0]["granularity"] == "movie_item"
