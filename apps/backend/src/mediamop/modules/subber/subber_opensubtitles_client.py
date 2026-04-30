"""OpenSubtitles.com REST API v1 client."""

from __future__ import annotations

import json
import urllib.parse
from typing import Any

import httpx

from mediamop.modules.subber.subber_http_client import (
    DEFAULT_USER_AGENT,
    decode_http_error_json,
    request_bytes,
    request_json,
)

OS_BASE = "https://api.opensubtitles.com/api/v1"
USER_AGENT = DEFAULT_USER_AGENT


class SubberRateLimitError(Exception):
    """OpenSubtitles returned HTTP 429."""


def _request(
    method: str,
    path: str,
    *,
    api_key: str,
    body: dict[str, Any] | None = None,
    token: str | None = None,
) -> tuple[int, dict[str, Any] | list[Any] | None]:
    url = f"{OS_BASE}{path}"
    headers = {
        "User-Agent": USER_AGENT,
        "Api-Key": api_key.strip(),
        "Accept": "application/json",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        return request_json(url, method=method, headers=headers, body=body, timeout=60)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 429:
            raise SubberRateLimitError from exc
        try:
            parsed = decode_http_error_json(exc)
        except json.JSONDecodeError:
            parsed = None
        return int(exc.response.status_code), parsed


def login(username: str, password: str, api_key: str) -> str:
    code, body = _request(
        "POST",
        "/login",
        api_key=api_key,
        body={"username": username.strip(), "password": password},
    )
    if code != 200 or not isinstance(body, dict):
        msg = f"OpenSubtitles login failed (HTTP {code})"
        raise ValueError(msg)
    tok = body.get("token")
    if not tok and isinstance(body.get("data"), dict):
        tok = body.get("data", {}).get("token")
    if not tok:
        tok = str(body.get("user", {}).get("token") or "") if isinstance(body.get("user"), dict) else ""
    tok = str(tok).strip()
    if not tok:
        msg = "OpenSubtitles login response missing token"
        raise ValueError(msg)
    return tok


def fetch_user_info(token: str, api_key: str) -> dict[str, Any]:
    code, body = _request("GET", "/infos/user", api_key=api_key, token=token)
    if code == 429:
        raise SubberRateLimitError()
    if code != 200 or not isinstance(body, dict):
        return {}
    data = body.get("data")
    return data if isinstance(data, dict) else body


def logout(token: str, api_key: str) -> None:
    try:
        _request("DELETE", "/logout", api_key=api_key, token=token)
    except Exception:
        pass


def search(
    token: str,
    api_key: str,
    *,
    query: str,
    season_number: int | None,
    episode_number: int | None,
    languages: list[str],
    media_scope: str,
) -> list[dict[str, Any]]:
    """Return subtitle result dicts (raw API ``data`` items)."""

    params: list[str] = [f"query={urllib.parse.quote(query)}"]
    if languages:
        params.append(f"languages={urllib.parse.quote(','.join(languages))}")
    if media_scope == "tv" and season_number is not None:
        params.append(f"season_number={int(season_number)}")
    if media_scope == "tv" and episode_number is not None:
        params.append(f"episode_number={int(episode_number)}")
    path = "/subtitles?" + "&".join(params)
    code, body = _request("GET", path, api_key=api_key, token=token)
    if code == 429:
        raise SubberRateLimitError()
    if code != 200 or not isinstance(body, dict):
        return []
    data = body.get("data")
    if not isinstance(data, list):
        return []
    out: list[dict[str, Any]] = []
    for item in data:
        if isinstance(item, dict):
            out.append(item)
    return out


def download(token: str, api_key: str, *, file_id: int) -> bytes:
    code, body = _request(
        "POST",
        "/download",
        api_key=api_key,
        token=token,
        body={"file_id": int(file_id)},
    )
    if code == 429:
        raise SubberRateLimitError()
    if code != 200 or not isinstance(body, dict):
        msg = f"OpenSubtitles download failed (HTTP {code})"
        raise ValueError(msg)
    link = body.get("link") or body.get("data", {}).get("link")
    if isinstance(body.get("data"), dict) and not link:
        link = body["data"].get("link")
    link = str(link or "").strip()
    if not link:
        msg = "OpenSubtitles download response missing link"
        raise ValueError(msg)
    _code, data = request_bytes(link, headers={"User-Agent": USER_AGENT}, timeout=120, validate_provider_url=True)
    return data
