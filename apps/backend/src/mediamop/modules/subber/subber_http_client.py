"""Shared HTTP helpers for Subber provider clients."""

from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request
from typing import Any

DEFAULT_USER_AGENT = "MediaMop/1.0"
HTML_USER_AGENT = "Mozilla/5.0 (compatible; MediaMop/1.0)"


def basic_auth_header(username: str | None, password: str | None) -> str | None:
    user = (username or "").strip()
    secret = (password or "").strip()
    if not user or not secret:
        return None
    token = base64.b64encode(f"{user}:{secret}".encode()).decode("ascii")
    return f"Basic {token}"


def request_bytes(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    data: bytes | None = None,
    timeout: float = 60,
) -> tuple[int, bytes]:
    req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)  # noqa: S310
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        return int(getattr(resp, "status", 200)), resp.read()


def request_text(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    data: bytes | None = None,
    timeout: float = 60,
) -> tuple[int, str]:
    code, raw = request_bytes(url, method=method, headers=headers, data=data, timeout=timeout)
    return code, raw.decode("utf-8", errors="replace")


def request_json(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    body: dict[str, Any] | None = None,
    timeout: float = 60,
) -> tuple[int, dict[str, Any] | list[Any] | None]:
    merged = dict(headers or {})
    data = None
    if body is not None:
        data = json.dumps(body, separators=(",", ":")).encode("utf-8")
        merged.setdefault("Content-Type", "application/json")
    code, text = request_text(url, method=method, headers=merged, data=data, timeout=timeout)
    if not text.strip():
        return code, None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return code, None
    return code, parsed if isinstance(parsed, (dict, list)) else None


def decode_http_error_json(exc: urllib.error.HTTPError) -> dict[str, Any] | None:
    raw = exc.read().decode("utf-8", errors="replace")
    if not raw.strip():
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {"raw": raw}
    return parsed if isinstance(parsed, dict) else {"raw": raw}
