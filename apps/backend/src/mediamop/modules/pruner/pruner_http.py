"""Small synchronous HTTP helpers for Pruner (stdlib urllib — matches Fetcher Arr client style)."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


DEFAULT_TIMEOUT_SEC = 20.0


def http_get_json(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout_sec: float = DEFAULT_TIMEOUT_SEC,
) -> tuple[int, Any]:
    """GET JSON; returns ``(status_code, parsed_json)`` or raises on non-JSON success."""

    req = urllib.request.Request(url, headers=headers or {}, method="GET")
    with urllib.request.urlopen(req, timeout=timeout_sec) as resp:  # noqa: S310 — operator-controlled base URLs
        status = int(resp.status)
        raw = resp.read().decode("utf-8", errors="replace")
    if not raw.strip():
        return status, None
    return status, json.loads(raw)


def http_get_text(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout_sec: float = DEFAULT_TIMEOUT_SEC,
) -> tuple[int, str]:
    req = urllib.request.Request(url, headers=headers or {}, method="GET")
    with urllib.request.urlopen(req, timeout=timeout_sec) as resp:  # noqa: S310
        status = int(resp.status)
        raw = resp.read().decode("utf-8", errors="replace")
    return status, raw


def http_delete(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout_sec: float = DEFAULT_TIMEOUT_SEC,
) -> tuple[int, str | None]:
    """DELETE; returns ``(status, body_or_none)``. Treats HTTP error responses as status + optional body."""

    req = urllib.request.Request(url, headers=headers or {}, method="DELETE")
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:  # noqa: S310
            status = int(resp.status)
            raw = resp.read().decode("utf-8", errors="replace").strip()
            return status, raw if raw else None
    except urllib.error.HTTPError as e:
        raw = ""
        try:
            raw = e.read().decode("utf-8", errors="replace").strip()
        except Exception:
            pass
        return int(e.code), raw if raw else None


def join_base_path(base_url: str, path: str, params: dict[str, str] | None = None) -> str:
    root = base_url.rstrip("/") + "/"
    rel = path.lstrip("/")
    u = urllib.parse.urljoin(root, rel)
    if params:
        q = urllib.parse.urlencode(params)
        sep = "&" if "?" in u else "?"
        u = f"{u}{sep}{q}"
    return u
