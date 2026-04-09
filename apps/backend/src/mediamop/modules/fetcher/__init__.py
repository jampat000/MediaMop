"""Fetcher module — read-only bridge to the legacy Fetcher app until migration."""

from mediamop.modules.fetcher.probe import FetcherHealthProbe, probe_fetcher_healthz

__all__ = ["FetcherHealthProbe", "probe_fetcher_healthz"]
