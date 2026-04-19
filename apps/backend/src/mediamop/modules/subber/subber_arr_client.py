"""Sonarr / Radarr HTTP API client (urllib only)."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

USER_AGENT = "MediaMop/1.0"
_DEFAULT_TIMEOUT_SEC = 120


class SubberArrClientError(Exception):
    """Raised on HTTP errors, timeouts, or malformed JSON from *arr APIs."""


def _get_json(url: str, api_key: str, *, timeout: int = _DEFAULT_TIMEOUT_SEC) -> Any:
    req = urllib.request.Request(  # noqa: S310
        url,
        headers={"X-Api-Key": api_key, "User-Agent": USER_AGENT},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            code = int(getattr(resp, "status", 200))
            if code >= 400:
                raise SubberArrClientError(f"HTTP {code}")
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:500]
        raise SubberArrClientError(f"HTTP {e.code}: {body}") from e
    except urllib.error.URLError as e:
        reason = getattr(e, "reason", e)
        raise SubberArrClientError(str(reason)) from e
    except TimeoutError as e:
        raise SubberArrClientError("timeout") from e
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise SubberArrClientError("invalid JSON response") from e


def get_radarr_movies(base_url: str, api_key: str) -> list[dict]:
    """GET /api/v3/movie — returns list of movie objects.

    Each has: id, title, year, hasFile, movieFile.path (when hasFile)
    """
    url = base_url.rstrip("/") + "/api/v3/movie"
    data = _get_json(url, api_key)
    if not isinstance(data, list):
        raise SubberArrClientError("expected JSON array from Radarr /api/v3/movie")
    return [x for x in data if isinstance(x, dict)]


def get_sonarr_series(base_url: str, api_key: str) -> list[dict]:
    """GET /api/v3/series — returns list of series objects.

    Each has: id, title
    """
    url = base_url.rstrip("/") + "/api/v3/series"
    data = _get_json(url, api_key)
    if not isinstance(data, list):
        raise SubberArrClientError("expected JSON array from Sonarr /api/v3/series")
    return [x for x in data if isinstance(x, dict)]


def get_sonarr_episodes(base_url: str, api_key: str, series_id: int) -> list[dict]:
    """GET /api/v3/episode?seriesId={id} — returns episodes.

    Each has: id, title, seasonNumber, episodeNumber,
    hasFile, episodeFile.path (when hasFile)
    """
    q = urllib.parse.urlencode({"seriesId": str(int(series_id))})
    url = base_url.rstrip("/") + "/api/v3/episode?" + q
    data = _get_json(url, api_key)
    if not isinstance(data, list):
        raise SubberArrClientError("expected JSON array from Sonarr /api/v3/episode")
    return [x for x in data if isinstance(x, dict)]


def get_sonarr_episode_files(base_url: str, api_key: str, series_id: int) -> list[dict]:
    """GET /api/v3/episodefile?seriesId={id} — returns episode files.

    Each has: id, path, seriesId
    """
    q = urllib.parse.urlencode({"seriesId": str(int(series_id))})
    url = base_url.rstrip("/") + "/api/v3/episodefile?" + q
    data = _get_json(url, api_key)
    if not isinstance(data, list):
        raise SubberArrClientError("expected JSON array from Sonarr /api/v3/episodefile")
    return [x for x in data if isinstance(x, dict)]
