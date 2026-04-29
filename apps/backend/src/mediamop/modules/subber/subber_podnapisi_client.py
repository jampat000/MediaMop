"""Podnapisi.NET JSON API client (urllib)."""

from __future__ import annotations

import io
import logging
import urllib.parse
import zipfile
from typing import Any

from mediamop.modules.subber.subber_http_client import DEFAULT_USER_AGENT, basic_auth_header, request_bytes, request_json

USER_AGENT = DEFAULT_USER_AGENT
LIST_BASE = "https://www.podnapisi.net/api/v2/subtitles/list"

logger = logging.getLogger(__name__)


def _request_json(url: str, *, username: str | None = None, password: str | None = None) -> dict[str, Any] | list[Any] | None:
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    auth = basic_auth_header(username, password)
    if auth:
        headers["Authorization"] = auth
    try:
        _code, parsed = request_json(url, headers=headers, timeout=60)
        return parsed
    except Exception:
        logger.exception("Podnapisi request failed url=%s", url)
        return None


def _item_hearing_impaired(item: dict[str, Any]) -> bool:
    flags = item.get("flags")
    if isinstance(flags, list):
        for f in flags:
            if str(f).lower() in ("hearing_impaired", "hearing impaired"):
                return True
    attrs = item.get("attributes")
    if isinstance(attrs, dict):
        if attrs.get("hearing_impaired") or attrs.get("from_hearing_impaired"):
            return True
    return False


def _item_id_lang(item: dict[str, Any]) -> tuple[str | None, str]:
    pid = item.get("id") or item.get("subtitle_id")
    if pid is None and isinstance(item.get("attributes"), dict):
        pid = item["attributes"].get("id") or item["attributes"].get("subtitle_id")
    sid = str(pid).strip() if pid is not None else None
    lang = ""
    if isinstance(item.get("attributes"), dict):
        lang = str(item["attributes"].get("language") or item["attributes"].get("lang") or "").strip().lower()
    if not lang:
        lang = str(item.get("language") or "").strip().lower()
    return sid, lang[:10]


def search(
    *,
    query: str,
    season_number: int | None,
    episode_number: int | None,
    languages: list[str],
    media_scope: str,
    username: str | None = None,
    password: str | None = None,
) -> list[dict[str, Any]]:
    """Return raw-ish dict items with ``id``, ``language``, ``hearing_impaired`` hints."""

    params: list[str] = [f"keywords={urllib.parse.quote(query.strip())}"]
    if languages:
        langs = "|".join(urllib.parse.quote(x.strip().lower(), safe="") for x in languages if x.strip())
        if langs:
            params.append(f"languages={langs}")
    if media_scope == "tv":
        if season_number is not None:
            params.append(f"season={int(season_number)}")
        if episode_number is not None:
            params.append(f"episode={int(episode_number)}")
    url = LIST_BASE + "?" + "&".join(params)
    body = _request_json(url, username=username, password=password)
    if not isinstance(body, dict):
        return []
    data = body.get("data")
    if not isinstance(data, list):
        return []
    out: list[dict[str, Any]] = []
    for raw in data:
        if not isinstance(raw, dict):
            continue
        sid, lang = _item_id_lang(raw)
        if not sid:
            continue
        out.append(
            {
                "id": sid,
                "language": lang,
                "hearing_impaired": _item_hearing_impaired(raw),
                "raw": raw,
            },
        )
    return out


def download(*, subtitle_id: str, username: str | None = None, password: str | None = None) -> bytes:
    """Download subtitle package (ZIP); caller extracts ``.srt``."""

    sid = urllib.parse.quote(str(subtitle_id).strip(), safe="")
    url = f"https://www.podnapisi.net/api/v2/subtitles/{sid}/download"
    headers = {"User-Agent": USER_AGENT, "Accept": "*/*"}
    auth = basic_auth_header(username, password)
    if auth:
        headers["Authorization"] = auth
    _code, data = request_bytes(url, headers=headers, timeout=120)
    bio = io.BytesIO(data)
    if zipfile.is_zipfile(bio):
        bio.seek(0)
        with zipfile.ZipFile(bio) as zf:
            for name in zf.namelist():
                if name.lower().endswith(".srt"):
                    return zf.read(name)
    return data


def extract_first_srt_from_zip(data: bytes) -> bytes:
    """If ``data`` is a ZIP containing an ``.srt``, return that file's bytes; else return ``data``."""

    bio = io.BytesIO(data)
    if zipfile.is_zipfile(bio):
        bio.seek(0)
        with zipfile.ZipFile(bio) as zf:
            for name in zf.namelist():
                if name.lower().endswith(".srt"):
                    return zf.read(name)
    return data
