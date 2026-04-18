"""Unit and narrow integration checks for preview-only year, studio, and collection filters."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import pytest
from alembic import command
from alembic.config import Config

import mediamop.modules.pruner.pruner_jobs_model  # noqa: F401
import mediamop.modules.pruner.pruner_preview_run_model  # noqa: F401
import mediamop.modules.pruner.pruner_scope_settings_model  # noqa: F401
import mediamop.modules.pruner.pruner_server_instance_model  # noqa: F401
import mediamop.platform.activity.models  # noqa: F401
import mediamop.platform.auth.models  # noqa: F401
from mediamop.modules.pruner.pruner_constants import MEDIA_SCOPE_MOVIES, RULE_FAMILY_MISSING_PRIMARY_MEDIA_REPORTED
from mediamop.modules.pruner.pruner_genre_filters import plex_leaf_collection_tags, plex_leaf_studio_tags
from mediamop.modules.pruner.pruner_media_library import jf_emby_pruner_preview_items_fields_csv, preview_payload_json
from mediamop.modules.pruner.pruner_preview_item_filters import jf_emby_item_passes_preview_filters
from mediamop.modules.pruner.pruner_preview_year_filters import (
    item_matches_preview_year_filter,
    jellyfin_emby_item_production_year_int,
    plex_leaf_release_year_int,
)
from mediamop.modules.pruner.pruner_studio_collection_filters import (
    jellyfin_emby_item_studio_names,
    preview_collection_filters_from_db_column,
    preview_studio_filters_from_db_column,
)
from tests.integration_app_runtime_quiesce import (
    integration_test_quiesce_in_process_workers,
    integration_test_quiesce_periodic_enqueue,
    integration_test_set_home,
)
@pytest.fixture(autouse=True)
def _iso(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    integration_test_set_home(tmp_path, monkeypatch, "mmhome_pruner_ysc_filters")
    integration_test_quiesce_in_process_workers(monkeypatch)
    integration_test_quiesce_periodic_enqueue(monkeypatch)
    backend = Path(__file__).resolve().parents[1]
    command.upgrade(Config(str(backend / "alembic.ini")), "head")


def test_item_matches_preview_year_filter_inactive_when_unbounded() -> None:
    assert item_matches_preview_year_filter(1999, None, None) is True


def test_item_matches_preview_year_filter_missing_year_never_matches() -> None:
    assert item_matches_preview_year_filter(None, 2000, None) is False
    assert item_matches_preview_year_filter(None, None, 2000) is False


def test_item_matches_preview_year_filter_inclusive_range() -> None:
    assert item_matches_preview_year_filter(2000, 2000, 2000) is True
    assert item_matches_preview_year_filter(1999, 2000, 2010) is False
    assert item_matches_preview_year_filter(2011, 2000, 2010) is False


def test_jellyfin_emby_item_production_year_int_honors_int_only() -> None:
    assert jellyfin_emby_item_production_year_int({"ProductionYear": 2015}) == 2015
    assert jellyfin_emby_item_production_year_int({"ProductionYear": "2015"}) is None


def test_plex_leaf_release_year_int_accepts_digit_string() -> None:
    assert plex_leaf_release_year_int({"year": 2012}) == 2012
    assert plex_leaf_release_year_int({"year": "  2012 "}) == 2012


def test_preview_studio_filters_from_db_column_malformed_json_fails_open() -> None:
    assert preview_studio_filters_from_db_column("{not json") == []


def test_preview_collection_filters_from_db_column_too_many_tokens_fails_open() -> None:
    raw = '["' + '","'.join([f"c{i}" for i in range(30)]) + '"]'
    assert preview_collection_filters_from_db_column(raw) == []


def test_jellyfin_emby_item_studio_names_reads_name_objects() -> None:
    item = {"Studios": [{"Name": " Acme "}, {"Name": ""}, "x", {"foo": 1}]}
    assert jellyfin_emby_item_studio_names(item) == ["Acme"]


def test_jf_emby_item_passes_preview_filters_and_semantics() -> None:
    item = {
        "Genres": ["Drama"],
        "People": [{"Name": "Ada Lovelace"}],
        "ProductionYear": 2015,
        "Studios": [{"Name": "BBC"}],
    }
    assert jf_emby_item_passes_preview_filters(
        item,
        preview_include_genres=["drama"],
        preview_include_people=["ada lovelace"],
        preview_year_min=2010,
        preview_year_max=2020,
        preview_include_studios=["bbc"],
    )
    assert not jf_emby_item_passes_preview_filters(
        item,
        preview_include_genres=["drama"],
        preview_include_people=["ada lovelace"],
        preview_year_min=2010,
        preview_year_max=2020,
        preview_include_studios=["hbo"],
    )


def test_jf_emby_pruner_preview_items_fields_csv_includes_production_year_and_studios() -> None:
    csv = jf_emby_pruner_preview_items_fields_csv()
    assert "ProductionYear" in csv
    assert "Studios" in csv


def test_preview_payload_jellyfin_missing_primary_ignores_year_and_studio_params() -> None:
    captured: list[str] = []

    def fake_get_json(url: str, headers: dict[str, str]) -> tuple[int, dict]:  # noqa: ARG001
        captured.append(url)
        q = parse_qs(urlparse(url).query)
        fields = (q.get("Fields") or [""])[0]
        assert "Studios" in fields
        assert "ProductionYear" in fields
        si = int(q.get("StartIndex", ["0"])[0])
        if si > 0:
            return 200, {"Items": [], "TotalRecordCount": 2}
        return (
            200,
            {
                "Items": [
                    {
                        "Id": "a",
                        "Name": "M1",
                        "Genres": ["Drama"],
                        "ImageTags": {},
                        "ProductionYear": 2015,
                        "Studios": [{"Name": "Acme"}],
                    },
                    {
                        "Id": "b",
                        "Name": "M2",
                        "Genres": ["Drama"],
                        "ImageTags": {},
                        "ProductionYear": 1999,
                        "Studios": [{"Name": "Acme"}],
                    },
                ],
                "TotalRecordCount": 2,
            },
        )

    with patch("mediamop.modules.pruner.pruner_media_library.http_get_json", fake_get_json):
        out, detail, cands, trunc = preview_payload_json(
            provider="jellyfin",
            base_url="http://jf.test",
            media_scope=MEDIA_SCOPE_MOVIES,
            secrets={"api_key": "k"},
            max_items=50,
            rule_family_id=RULE_FAMILY_MISSING_PRIMARY_MEDIA_REPORTED,
            preview_year_min=2010,
            preview_year_max=2020,
            preview_include_studios=["acme"],
        )
    assert out == "success" and not detail
    assert len(cands) == 2
    assert {c["item_id"] for c in cands} == {"a", "b"}
    assert trunc is False


def test_plex_leaf_collection_tags_reads_collection_key() -> None:
    meta = {"Collection": [{"tag": "MCU"}, {"Tag": "Other"}]}
    assert plex_leaf_collection_tags(meta) == ["MCU", "Other"]


def test_plex_leaf_studio_tags_reads_studio_key() -> None:
    meta = {"Studio": [{"tag": "Acme"}]}
    assert plex_leaf_studio_tags(meta) == ["Acme"]


def test_preview_payload_plex_missing_primary_ignores_collection_params() -> None:
    def fake_list(**kwargs: object) -> tuple[list[dict], bool]:
        assert "preview_include_collections" not in kwargs
        return ([{"granularity": "movie_item", "item_id": "9", "title": "X", "year": 2015}], False)

    with patch(
        "mediamop.modules.pruner.pruner_media_library.list_plex_missing_thumb_candidates",
        fake_list,
    ):
        out, detail, cands, trunc = preview_payload_json(
            provider="plex",
            base_url="http://plex.test",
            media_scope=MEDIA_SCOPE_MOVIES,
            secrets={"auth_token": "t"},
            max_items=50,
            rule_family_id=RULE_FAMILY_MISSING_PRIMARY_MEDIA_REPORTED,
        )
    assert out == "success" and not detail
    assert cands[0]["item_id"] == "9"
    assert trunc is False
