"""Read-only probe of a standalone Fetcher instance (legacy app) — no DB or scheduler coupling."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


@dataclass(frozen=True, slots=True)
class FetcherHealthProbe:
    reachable: bool
    http_status: int | None
    latency_ms: float | None
    fetcher_app: str | None
    fetcher_version: str | None
    error_summary: str | None


def probe_fetcher_healthz(base_url: str, *, timeout_sec: float = 3.0) -> FetcherHealthProbe:
    """GET ``{base_url}/healthz`` — matches Fetcher ``app/routers/api.py`` liveness JSON."""

    root = base_url.rstrip("/")
    url = f"{root}/healthz"
    t0 = time.perf_counter()
    try:
        req = Request(url, method="GET", headers={"Accept": "application/json"})
        with urlopen(req, timeout=timeout_sec) as resp:
            latency_ms = round((time.perf_counter() - t0) * 1000, 1)
            raw = resp.read().decode("utf-8", errors="replace")
            code = getattr(resp, "status", None) or 200
            app_n: str | None = None
            ver: str | None = None
            if raw.strip():
                try:
                    data = json.loads(raw)
                    if isinstance(data, dict):
                        a = data.get("app")
                        v = data.get("version")
                        app_n = str(a) if a is not None else None
                        ver = str(v) if v is not None else None
                except json.JSONDecodeError:
                    pass
            return FetcherHealthProbe(
                reachable=True,
                http_status=int(code),
                latency_ms=latency_ms,
                fetcher_app=app_n,
                fetcher_version=ver,
                error_summary=None,
            )
    except HTTPError as e:
        latency_ms = round((time.perf_counter() - t0) * 1000, 1)
        return FetcherHealthProbe(
            reachable=False,
            http_status=int(e.code),
            latency_ms=latency_ms,
            fetcher_app=None,
            fetcher_version=None,
            error_summary=(e.reason or f"HTTP {e.code}")[:200],
        )
    except URLError as e:
        reason = e.reason
        msg = str(reason) if reason is not None else "connection failed"
        return FetcherHealthProbe(
            reachable=False,
            http_status=None,
            latency_ms=None,
            fetcher_app=None,
            fetcher_version=None,
            error_summary=msg[:200],
        )
    except TimeoutError:
        return FetcherHealthProbe(
            reachable=False,
            http_status=None,
            latency_ms=None,
            fetcher_app=None,
            fetcher_version=None,
            error_summary="Timed out waiting for Fetcher.",
        )
    except OSError as e:
        return FetcherHealthProbe(
            reachable=False,
            http_status=None,
            latency_ms=None,
            fetcher_app=None,
            fetcher_version=None,
            error_summary=str(e)[:200],
        )
