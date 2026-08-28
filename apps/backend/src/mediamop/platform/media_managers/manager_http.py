"""Minimal synchronous JSON client for talking to a media manager (stdlib urllib).

Kept deliberately narrow, and kept guarded: the base URL must be a plain http(s)
address with no credentials, query or fragment, and a request path must be relative.
Together those stop a saved connection from being turned into a request against an
arbitrary host — a cloud metadata endpoint being the obvious one.
"""

from __future__ import annotations

import contextlib
import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from mediamop.platform.outbound_http import normalize_local_service_base_url


class MediaManagerHttpError(RuntimeError):
    """Raised when a call to a media manager fails."""


class MediaManagerRateLimitedError(MediaManagerHttpError):
    """The manager returned 429. Back off; never retry inside the same call.

    Deluno publishes a limit of 3000 requests per 60s per key and answers a breach with
    ``Retry-After``. Retrying immediately would spend the rest of the window on the
    retry rather than on the work, so this is surfaced to the caller as a degraded
    answer instead of being swallowed by a loop.
    """

    def __init__(self, message: str, *, retry_after_seconds: float | None = None) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


def _retry_after_seconds(raw: str | None) -> float | None:
    """Seconds from a ``Retry-After`` header, when it is expressed as a delay."""

    if raw is None:
        return None
    text = raw.strip()
    if not text:
        return None
    try:
        seconds = float(text)
    except ValueError:
        # The HTTP-date form is legal but nothing MediaMop needs to act on: the caller
        # degrades either way, and the next scheduled pass is minutes out.
        return None
    return seconds if seconds >= 0 else None


def _validated_base_url(raw: str) -> str:
    try:
        return normalize_local_service_base_url(raw)
    except ValueError as exc:
        raise MediaManagerHttpError(str(exc)) from exc


class MediaManagerHttpClient:
    """Narrow surface: whatever a module needs from a manager, over a validated base URL."""

    def __init__(self, base_url: str, api_key: str, *, timeout_seconds: float = 30.0) -> None:
        self._base = _validated_base_url(base_url)
        self._api_key = api_key
        self._timeout = timeout_seconds

    def _url(self, path: str, params: dict[str, str] | None = None) -> str:
        if urllib.parse.urlsplit(path).scheme:
            raise MediaManagerHttpError("A media manager API path must be relative.")
        p = path if path.startswith("/") else f"/{path}"
        u = f"{self._base}{p}"
        if params:
            u = f"{u}?{urllib.parse.urlencode(params)}"
        return u

    def get_json(self, path: str, *, params: dict[str, Any] | None = None) -> Any:
        flat = {k: str(int(v)) if isinstance(v, bool) else str(v) for k, v in (params or {}).items()}
        url = self._url(path, flat if flat else None)
        req = urllib.request.Request(
            url,
            headers={"X-Api-Key": self._api_key, "Accept": "application/json"},
        )
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
                    raise MediaManagerHttpError(f"unexpected HTTP {resp.status}")
                if not raw:
                    return None
                return json.loads(raw.decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = ""
            with contextlib.suppress(Exception):
                body = e.read().decode("utf-8", errors="replace")[:500]
            if e.code == 429:
                raise MediaManagerRateLimitedError(
                    f"HTTP 429: {body}",
                    retry_after_seconds=_retry_after_seconds(e.headers.get("Retry-After")),
                ) from e
            raise MediaManagerHttpError(f"HTTP {e.code}: {body}") from e

    def health_ok(self, path: str) -> None:
        """Ask the manager whether it is there, at whichever path it answers on."""

        self.get_json(path)
