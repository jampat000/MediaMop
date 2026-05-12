"""Plex movie rule preview collectors: token-scoped watched state, audienceRating, addedAt (allLeaves only)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from mediamop.modules.pruner.pruner_constants import (
    MEDIA_SCOPE_MOVIES,
    RULE_FAMILY_UNWATCHED_MOVIE_STALE_REPORTED,
    RULE_FAMILY_WATCHED_MOVIE_LOW_RATING_REPORTED,
    RULE_FAMILY_WATCHED_MOVIES_REPORTED,
)
from mediamop.modules.pruner.pruner_media_library import preview_payload_json
from mediamop.modules.pruner.pruner_plex_movie_rule_candidates import (
    list_plex_unwatched_movie_stale_candidates,
    list_plex_watched_movie_candidates,
    list_plex_watched_movie_low_rating_candidates,
    plex_leaf_added_at_utc,
    plex_leaf_audience_rating_float,
    plex_movie_leaf_unwatched_for_token,
    plex_movie_leaf_watched_for_token,
)


def test_plex_movie_leaf_watched_view_count() -> None:
    assert plex_movie_leaf_watched_for_token({"viewCount": 1}) is True
    assert plex_movie_leaf_watched_for_token({"viewCount": "2"}) is True
    assert plex_movie_leaf_watched_for_token({"viewCount": 0, "lastViewedAt": 1}) is True


def test_plex_movie_leaf_unwatched_empty() -> None:
    assert plex_movie_leaf_unwatched_for_token({}) is True
    assert plex_movie_leaf_unwatched_for_token({"viewCount": 0}) is True


def test_plex_leaf_audience_rating_float() -> None:
    assert plex_leaf_audience_rating_float({"audienceRating": 3.5}) == 3.5
    assert plex_leaf_audience_rating_float({"audienceRating": "4"}) == 4.0
    assert plex_leaf_audience_rating_float({}) is None


def test_plex_leaf_added_at_utc_seconds_and_ms() -> None:
    dt = plex_leaf_added_at_utc({"addedAt": 1_450_147_195})
    assert dt is not None
    assert dt.tzinfo == UTC
    dt_ms = plex_leaf_added_at_utc({"addedAt": 1_450_147_195_000})
    assert dt_ms is not None
    assert abs((dt_ms - dt).total_seconds()) < 2


def test_list_plex_watched_movie_candidates_filters_thumb_not_required() -> None:
    """Watched movies include rows even when thumb is present (unlike missing-primary)."""

    def fake_get_json(url: str, headers: dict[str, str]) -> tuple[int, dict]:  # noqa: ARG001
        if "allLeaves" not in url:
            return (
                200,
                {
                    "MediaContainer": {
                        "Directory": [{"type": "movie", "key": "2"}],
                    },
                },
            )
        return (
            200,
            {
                "MediaContainer": {
                    "Metadata": [
                        {
                            "type": "movie",
                            "ratingKey": "99",
                            "title": "Watched Thumb",
                            "thumb": "/library/metadata/99/thumb/1",
                            "viewCount": 1,
                            "year": 2010,
                        },
                    ],
                    "totalSize": 1,
                },
            },
        )

    with patch("mediamop.modules.pruner.pruner_plex_movie_rule_candidates.http_get_json", fake_get_json):
        rows, trunc = list_plex_watched_movie_candidates(
            base_url="http://plex.test",
            auth_token="tok",
            max_items=10,
        )
    assert not trunc
    assert len(rows) == 1
    assert rows[0]["item_id"] == "99"


def test_preview_payload_plex_watched_movies_success() -> None:
    def fake_get_json(url: str, headers: dict[str, str]) -> tuple[int, dict]:  # noqa: ARG001
        if "sections" in url and "allLeaves" not in url:
            return 200, {"MediaContainer": {"Directory": [{"type": "movie", "key": "1"}]}}
        return (
            200,
            {
                "MediaContainer": {
                    "Metadata": [
                        {"type": "movie", "ratingKey": "7", "title": "M", "viewCount": 1, "year": 2001},
                    ],
                    "totalSize": 1,
                },
            },
        )

    with patch("mediamop.modules.pruner.pruner_plex_movie_rule_candidates.http_get_json", fake_get_json):
        out, detail, cands, trunc = preview_payload_json(
            provider="plex",
            base_url="http://plex.test",
            media_scope=MEDIA_SCOPE_MOVIES,
            secrets={"auth_token": "t"},
            max_items=10,
            rule_family_id=RULE_FAMILY_WATCHED_MOVIES_REPORTED,
        )
    assert out == "success" and detail == ""
    assert len(cands) == 1 and cands[0]["item_id"] == "7"
    assert not trunc


def test_list_plex_low_rating_requires_audience_rating() -> None:
    def fake_get_json(url: str, headers: dict[str, str]) -> tuple[int, dict]:  # noqa: ARG001
        if "allLeaves" not in url:
            return 200, {"MediaContainer": {"Directory": [{"type": "movie", "key": "1"}]}}
        return (
            200,
            {
                "MediaContainer": {
                    "Metadata": [
                        {
                            "type": "movie",
                            "ratingKey": "a",
                            "title": "No AR",
                            "viewCount": 1,
                        },
                        {
                            "type": "movie",
                            "ratingKey": "b",
                            "title": "Low",
                            "viewCount": 1,
                            "audienceRating": 2.0,
                        },
                    ],
                    "totalSize": 2,
                },
            },
        )

    with patch("mediamop.modules.pruner.pruner_plex_movie_rule_candidates.http_get_json", fake_get_json):
        rows, _ = list_plex_watched_movie_low_rating_candidates(
            base_url="http://plex.test",
            auth_token="tok",
            max_items=10,
            audience_rating_max_inclusive=4.0,
        )
    assert len(rows) == 1
    assert rows[0]["item_id"] == "b"
    assert rows[0]["plex_audience_rating"] == 2.0


def test_list_plex_unwatched_stale_uses_added_at() -> None:
    old_ts = int((datetime.now(UTC) - timedelta(days=100)).timestamp())

    def fake_get_json(url: str, headers: dict[str, str]) -> tuple[int, dict]:  # noqa: ARG001
        if "allLeaves" not in url:
            return 200, {"MediaContainer": {"Directory": [{"type": "movie", "key": "1"}]}}
        return (
            200,
            {
                "MediaContainer": {
                    "Metadata": [
                        {
                            "type": "movie",
                            "ratingKey": "u1",
                            "title": "Stale",
                            "addedAt": old_ts,
                        },
                    ],
                    "totalSize": 1,
                },
            },
        )

    with patch("mediamop.modules.pruner.pruner_plex_movie_rule_candidates.http_get_json", fake_get_json):
        rows, _ = list_plex_unwatched_movie_stale_candidates(
            base_url="http://plex.test",
            auth_token="tok",
            max_items=10,
            min_age_days=30,
        )
    assert len(rows) == 1
    assert rows[0]["item_id"] == "u1"


def test_preview_payload_plex_low_rating_rejects_tv_scope() -> None:
    out, detail, cands, trunc = preview_payload_json(
        provider="plex",
        base_url="http://plex.test",
        media_scope="tv",
        secrets={"auth_token": "t"},
        max_items=10,
        rule_family_id=RULE_FAMILY_WATCHED_MOVIE_LOW_RATING_REPORTED,
        watched_movie_low_rating_max_jellyfin_emby_community_rating=4.0,
        watched_movie_low_rating_max_plex_audience_rating=4.0,
    )
    assert out == "unsupported"
    assert "movies tab" in detail.lower()
    assert cands == [] and not trunc


def test_preview_payload_plex_unwatched_stale_requires_age_param() -> None:
    with pytest.raises(ValueError, match="unwatched_movie_stale_min_age_days"):
        preview_payload_json(
            provider="plex",
            base_url="http://plex.test",
            media_scope=MEDIA_SCOPE_MOVIES,
            secrets={"auth_token": "t"},
            max_items=10,
            rule_family_id=RULE_FAMILY_UNWATCHED_MOVIE_STALE_REPORTED,
            unwatched_movie_stale_min_age_days=None,
        )
