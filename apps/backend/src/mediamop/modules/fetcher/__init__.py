"""Fetcher module — read-only bridge to the separate Fetcher application until migration completes."""

from mediamop.modules.fetcher.probe import FetcherHealthProbe, probe_fetcher_healthz

__all__ = ["FetcherHealthProbe", "probe_fetcher_healthz"]
