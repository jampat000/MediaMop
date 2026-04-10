"""Refiner HTTP routes (reserved for Refiner-native surfaces).

Queue-driven Radarr/Sonarr download-queue failed-import operations are exposed under
``mediamop.modules.fetcher.failed_imports_api`` (Fetcher product ownership).
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["refiner"])
