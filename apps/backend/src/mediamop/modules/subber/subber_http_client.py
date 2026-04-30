"""Shared HTTP helpers for Subber provider clients."""

from __future__ import annotations

import base64
import ipaddress
import json
from typing import Any
from urllib.parse import urlparse

import httpx

DEFAULT_USER_AGENT = "MediaMop/1.0"
HTML_USER_AGENT = "Mozilla/5.0 (compatible; MediaMop/1.0)"
_SHARED_CLIENT = httpx.Client(follow_redirects=True, max_redirects=5)


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
    validate_provider_url: bool = False,
) -> tuple[int, bytes]:
    request_url = safe_provider_url(url) if validate_provider_url else url
    response = _SHARED_CLIENT.request(
        method=method,
        url=request_url,
        headers=headers,
        content=data,
        timeout=timeout,
    )
    response.raise_for_status()
    return response.status_code, response.content


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


def decode_http_error_json(exc: httpx.HTTPStatusError) -> dict[str, Any] | None:
    raw = exc.response.text
    if not raw.strip():
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {"raw": raw}
    return parsed if isinstance(parsed, dict) else {"raw": raw}


def safe_provider_url(url: str) -> str:
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"}:
        raise ValueError(f"Blocked provider URL scheme: {parsed.scheme or '<missing>'}")
    host = (parsed.hostname or "").strip().lower()
    if not host:
        raise ValueError("Blocked provider URL host: <missing>")
    if host in {"localhost", "127.0.0.1", "::1", "0.0.0.0"}:
        raise ValueError(f"Blocked provider URL host: {host}")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return url
    if ip.is_loopback or ip.is_link_local or ip.is_private or ip.is_multicast or ip.is_reserved or ip.is_unspecified:
        raise ValueError(f"Blocked provider URL host: {host}")
    return url
