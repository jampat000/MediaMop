"""Refiner HTTP routes (reserved for Refiner-native surfaces).

Radarr/Sonarr download-queue failed-import cleanup and related Fetcher operator APIs live under
``mediamop.modules.fetcher`` (e.g. ``failed_imports_api`` for policy/runtime/drives, ``fetcher_jobs_api`` for persisted
``fetcher_jobs`` inspection, ``fetcher_arr_search_api`` for manual Arr search enqueue).
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["refiner"])
