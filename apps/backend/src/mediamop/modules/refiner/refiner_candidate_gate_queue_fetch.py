"""Refiner-owned live *arr queue fetch (stdlib HTTP only; does not import Fetcher)."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Literal


def fetch_arr_v3_queue_rows(
    *,
    base_url: str,
    api_key: str,
    app: Literal["radarr", "sonarr"],
    timeout_seconds: float = 30.0,
) -> list[dict[str, Any]]:
    """GET ``/api/v3/queue`` for Radarr or Sonarr (same v3 shape)."""

    base = base_url.rstrip("/")
    url = f"{base}/api/v3/queue?pageSize=1000"
    req = urllib.request.Request(
        url,
        method="GET",
        headers={"X-Api-Key": api_key, "Accept": "application/json"},
    )
    label = "Radarr" if app == "radarr" else "Sonarr"
    try:
        with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        msg = f"{label} queue fetch failed: HTTP {e.code} for {url!r}"
        raise RuntimeError(msg) from e
    data = json.loads(raw)
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        rec = data.get("records")
        if isinstance(rec, list):
            return [x for x in rec if isinstance(x, dict)]
    return []
