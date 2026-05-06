"""Shared outbound HTTP URL policy helpers used by Pruner/Refiner/Subber and ARR clients."""

from __future__ import annotations

import ipaddress
from urllib.parse import urlsplit, urlunsplit


def normalize_local_service_base_url(raw: str) -> str:
    """Normalize base URL for locally configured services (Arr, Plex, Jellyfin, Emby)."""

    parsed = urlsplit(raw.strip().rstrip("/"))
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("URL must be a valid http(s) URL.")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("URL must not include credentials, query strings, or fragments.")
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", ""))


def validate_external_provider_url(raw: str) -> str:
    """Validate provider URLs that must never target localhost/private addresses."""

    parsed = urlsplit(raw.strip())
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
        return raw
    if ip.is_loopback or ip.is_link_local or ip.is_private or ip.is_multicast or ip.is_reserved or ip.is_unspecified:
        raise ValueError(f"Blocked provider URL host: {host}")
    return raw
