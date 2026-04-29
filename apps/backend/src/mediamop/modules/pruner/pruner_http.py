"""Small synchronous HTTP helpers for Pruner (stdlib urllib)."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


DEFAULT_TIMEOUT_SEC = 20.0


class PrunerHttpStatusError(RuntimeError):
    """Typed non-2xx response for collectors that need status-aware fallback."""

    def __init__(self, *, url: str, status_code: int, body: object | None = None) -> None:
        super().__init__(f"HTTP {status_code} from {url}")
        self.url = url
        self.status_code = int(status_code)
        self.body = body


def _read_http_error(e: urllib.error.HTTPError) -> str | None:
    try:
        raw = e.read().decode("utf-8", errors="replace").strip()
    except Exception:
        raw = ""
    return raw if raw else None


def _parse_json_error_body(raw: str | None) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def http_get_json(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout_sec: float = DEFAULT_TIMEOUT_SEC,
) -> tuple[int, Any]:
    """GET JSON; returns ``(status_code, parsed_json_or_error_body)``."""

    req = urllib.request.Request(url, headers=headers or {}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:  # noqa: S310
            status = int(resp.status)
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return int(e.code), _parse_json_error_body(_read_http_error(e))
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
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:  # noqa: S310
            status = int(resp.status)
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return int(e.code), _read_http_error(e) or ""
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
        raw = _read_http_error(e)
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
