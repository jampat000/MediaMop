"""TMDb, reachable directly or through a gateway.

The base URL is configurable rather than hardcoded, because an operator may already put a
cache or proxy in front of TMDb — a Cloudflare worker is the common shape — and hardcoding
``api.themoviedb.org`` would make that setup unusable. It is validated with
``validate_external_provider_url``, so a gateway on a public host is fine and a URL
pointing at localhost, a private range, or a cloud metadata endpoint is refused.

Results are cached, because the alternative is one HTTP call per file per pass, and a
library re-scan would spend its time on lookups it already made. The cache is in-process
and bounded: a metadata answer is stable enough that a restart re-fetching it costs
nothing, and a persistent cache would be a schema to migrate for no gain.
"""

from __future__ import annotations

import json
import logging
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import OrderedDict
from typing import Any

from mediamop.integrations.metadata.provider_port import LookupResult, TitleMetadata
from mediamop.platform.outbound_http import validate_external_provider_url

logger = logging.getLogger(__name__)

DEFAULT_TMDB_BASE_URL = "https://api.themoviedb.org/3"

_TIMEOUT_SECONDS = 15.0
#: Enough for a large library's distinct titles without holding a meaningful amount of
#: memory. Evicted oldest-first.
_CACHE_MAX_ENTRIES = 2000
#: TMDb publishes no hard per-second limit any more, but hammering a gateway is rude and
#: a cache miss storm on a first scan is the realistic case. One call per interval.
_MIN_SECONDS_BETWEEN_CALLS = 0.25


class _Cache:
    """Bounded, thread-safe, oldest-first. Shared across passes within one process."""

    def __init__(self, max_entries: int = _CACHE_MAX_ENTRIES) -> None:
        self._lock = threading.Lock()
        self._entries: OrderedDict[str, LookupResult] = OrderedDict()
        self._max = max_entries

    def get(self, key: str) -> LookupResult | None:
        with self._lock:
            found = self._entries.get(key)
            if found is not None:
                self._entries.move_to_end(key)
            return found

    def put(self, key: str, value: LookupResult) -> None:
        with self._lock:
            self._entries[key] = value
            self._entries.move_to_end(key)
            while len(self._entries) > self._max:
                self._entries.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)


#: Process-wide, so two libraries scanning the same title do not both pay for it.
_SHARED_CACHE = _Cache()


def clear_metadata_cache() -> None:
    """Drop everything. Used by tests, and by a credential change."""

    _SHARED_CACHE.clear()


class TmdbMetadataProvider:
    """TMDb over its v3 API, or anything speaking the same shape."""

    name = "tmdb"

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = DEFAULT_TMDB_BASE_URL,
        cache: _Cache | None = None,
    ) -> None:
        self._api_key = (api_key or "").strip()
        self._base_url = (base_url or DEFAULT_TMDB_BASE_URL).strip().rstrip("/")
        self._cache = cache if cache is not None else _SHARED_CACHE
        self._last_call_at = 0.0
        self._rate_lock = threading.Lock()

    # --- public ----------------------------------------------------------------

    def lookup_movie(self, *, title: str, year: int | None) -> LookupResult:
        """Resolve a title. Never raises; every failure is a status."""

        cleaned = (title or "").strip()
        if not cleaned:
            return LookupResult(status="no_match", detail="There was no title to look up.")
        if not self._api_key:
            return LookupResult(
                status="not_configured",
                detail="No metadata provider key is configured, so MediaMop used the language preference list.",
            )

        key = f"{self._base_url}|{cleaned.lower()}|{year or ''}"
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        params: dict[str, str] = {"api_key": self._api_key, "query": cleaned}
        if year:
            params["year"] = str(year)
        result = self._search(params, subject=f"{cleaned} ({year})" if year else cleaned)
        # Negative answers are cached too. A title the provider does not know will still
        # be unknown on the next file in the same folder, and re-asking is the storm this
        # cache exists to prevent.
        self._cache.put(key, result)
        return result

    def test_connection(self) -> LookupResult:
        """A cheap real query, so a saved key is proven rather than assumed."""

        if not self._api_key:
            return LookupResult(status="not_configured", detail="No metadata provider key is configured.")
        probe = self._search(
            {"api_key": self._api_key, "query": "Blade Runner", "year": "1982"},
            subject="the connection test",
            use_rate_limit=False,
        )
        if probe.status == "matched":
            return LookupResult(status="matched", metadata=probe.metadata, detail="The metadata provider answered.")
        return probe

    # --- internals -------------------------------------------------------------

    def _wait_for_rate_limit(self) -> None:
        with self._rate_lock:
            elapsed = time.monotonic() - self._last_call_at
            if elapsed < _MIN_SECONDS_BETWEEN_CALLS:
                time.sleep(_MIN_SECONDS_BETWEEN_CALLS - elapsed)
            self._last_call_at = time.monotonic()

    def _search(self, params: dict[str, str], *, subject: str, use_rate_limit: bool = True) -> LookupResult:
        try:
            base = validate_external_provider_url(self._base_url)
        except ValueError as exc:
            return LookupResult(
                status="not_configured",
                detail=f"The metadata provider address is not usable ({exc}).",
            )

        if use_rate_limit:
            self._wait_for_rate_limit()

        url = f"{base}/search/movie?{urllib.parse.urlencode(params)}"
        request = urllib.request.Request(url, headers={"Accept": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:  # noqa: S310 - validated above
                raw = response.read()
        except urllib.error.HTTPError as exc:
            # A bad key is a configuration problem, not an outage, and saying so saves an
            # operator looking at their network.
            if exc.code in (401, 403):
                return LookupResult(
                    status="not_configured",
                    detail="The metadata provider rejected the configured key.",
                )
            return LookupResult(
                status="unreachable",
                detail=f"The metadata provider returned HTTP {exc.code} for {subject}.",
            )
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            return LookupResult(status="unreachable", detail=f"MediaMop could not reach the metadata provider ({exc}).")

        try:
            payload: Any = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return LookupResult(status="unreachable", detail="The metadata provider returned something unreadable.")

        results = payload.get("results") if isinstance(payload, dict) else None
        if not isinstance(results, list) or not results:
            return LookupResult(status="no_match", detail=f"The metadata provider had no match for {subject}.")

        first = results[0]
        if not isinstance(first, dict):
            return LookupResult(status="no_match", detail=f"The metadata provider had no usable match for {subject}.")

        release = str(first.get("release_date") or "")
        parsed_year: int | None = None
        if len(release) >= 4 and release[:4].isdigit():
            parsed_year = int(release[:4])

        return LookupResult(
            status="matched",
            metadata=TitleMetadata(
                original_language=str(first.get("original_language") or "").strip().lower(),
                title=str(first.get("title") or first.get("original_title") or "").strip(),
                year=parsed_year,
                provider_id=str(first.get("id") or ""),
            ),
            detail=f"The metadata provider matched {subject}.",
        )
