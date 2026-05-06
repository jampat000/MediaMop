"""Minimal synchronous Sonarr/Radarr v3 JSON client (stdlib urllib) for *arr* automation."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from mediamop.platform.outbound_http import normalize_local_service_base_url


class ArrLibraryV3HttpError(RuntimeError):
    """Raised when an Arr HTTP call fails."""


def _validated_base_url(raw: str) -> str:
    try:
        return normalize_local_service_base_url(raw)
    except ValueError as exc:
        raise ArrLibraryV3HttpError(str(exc)) from exc


class ArrLibraryV3Client:
    """Narrow surface: health, wanted pages, catalog walks, tags, commands."""

    def __init__(self, base_url: str, api_key: str, *, timeout_seconds: float = 30.0) -> None:
        self._base = _validated_base_url(base_url)
        self._api_key = api_key
        self._timeout = timeout_seconds

    def _url(self, path: str, params: dict[str, str] | None = None) -> str:
        if urllib.parse.urlsplit(path).scheme:
            raise ArrLibraryV3HttpError("Sonarr/Radarr API path must be relative.")
        p = path if path.startswith("/") else f"/{path}"
        u = f"{self._base}{p}"
        if params:
            u = f"{u}?{urllib.parse.urlencode(params)}"
        return u

    def get_json(self, path: str, *, params: dict[str, Any] | None = None) -> Any:
        flat = {k: str(int(v)) if isinstance(v, bool) else str(v) for k, v in (params or {}).items()}
        url = self._url(path, flat if flat else None)
        req = urllib.request.Request(url, headers={"X-Api-Key": self._api_key})
        return self._read_json(req)

    def post_json(self, path: str, body: dict[str, Any]) -> Any:
        data = json.dumps(body).encode("utf-8")
        url = self._url(path, None)
        req = urllib.request.Request(
            url,
            data=data,
            method="POST",
            headers={"X-Api-Key": self._api_key, "Content-Type": "application/json"},
        )
        return self._read_json(req)

    def put_json(self, path: str, body: dict[str, Any]) -> None:
        data = json.dumps(body).encode("utf-8")
        url = self._url(path, None)
        req = urllib.request.Request(
            url,
            data=data,
            method="PUT",
            headers={"X-Api-Key": self._api_key, "Content-Type": "application/json"},
        )
        self._read_json(req, allow_empty=True)

    def _read_json(self, req: urllib.request.Request, *, allow_empty: bool = False) -> Any:
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                raw = resp.read()
                if not raw and allow_empty:
                    return None
                if resp.status not in (200, 201, 204):
                    raise ArrLibraryV3HttpError(f"unexpected HTTP {resp.status}")
                if not raw:
                    return None
                return json.loads(raw.decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8", errors="replace")[:500]
            except Exception:
                pass
            raise ArrLibraryV3HttpError(f"HTTP {e.code}: {body}") from e

    def health_ok(self) -> None:
        self.get_json("/api/v3/system/status")
