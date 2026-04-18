"""OpenSubtitles.com REST API v1 client (urllib)."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

OS_BASE = "https://api.opensubtitles.com/api/v1"
USER_AGENT = "MediaMop/1.0"


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
    data_bytes = None
    headers = {
        "User-Agent": USER_AGENT,
        "Api-Key": api_key.strip(),
        "Accept": "application/json",
    }
    if body is not None:
        data_bytes = json.dumps(body, separators=(",", ":")).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data_bytes, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310 — controlled URL
            raw = resp.read().decode("utf-8", errors="replace")
            code = int(getattr(resp, "status", 200))
            if not raw.strip():
                return code, None
            parsed = json.loads(raw)
            return code, parsed if isinstance(parsed, (dict, list)) else None
    except urllib.error.HTTPError as e:
        if e.code == 429:
            raise SubberRateLimitError from e
        try:
            err_body = e.read().decode("utf-8", errors="replace")
            parsed = json.loads(err_body) if err_body.strip() else None
        except json.JSONDecodeError:
            parsed = None
        return int(e.code), parsed if isinstance(parsed, dict) else {"raw": err_body}


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
    req = urllib.request.Request(  # noqa: S310
        link,
        headers={"User-Agent": USER_AGENT},
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return resp.read()