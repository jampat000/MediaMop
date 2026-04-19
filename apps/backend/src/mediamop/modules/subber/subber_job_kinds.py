"""Durable Subber job kinds (``subber_jobs`` lane only)."""

from __future__ import annotations

SUBBER_JOB_KIND_SUBTITLE_SEARCH_TV = "subber.subtitle_search.tv.v1"
SUBBER_JOB_KIND_SUBTITLE_SEARCH_MOVIES = "subber.subtitle_search.movies.v1"
SUBBER_JOB_KIND_LIBRARY_SCAN_TV = "subber.library_scan.tv.v1"
SUBBER_JOB_KIND_LIBRARY_SCAN_MOVIES = "subber.library_scan.movies.v1"
SUBBER_JOB_KIND_LIBRARY_SYNC_TV = "subber.library_sync.tv.v1"
SUBBER_JOB_KIND_LIBRARY_SYNC_MOVIES = "subber.library_sync.movies.v1"
SUBBER_JOB_KIND_WEBHOOK_IMPORT_TV = "subber.webhook_import.tv.v1"
SUBBER_JOB_KIND_WEBHOOK_IMPORT_MOVIES = "subber.webhook_import.movies.v1"
SUBBER_JOB_KIND_SUBTITLE_UPGRADE = "subber.subtitle_upgrade.v1"

ALL_SUBBER_PRODUCTION_JOB_KINDS: frozenset[str] = frozenset(
    {
        SUBBER_JOB_KIND_SUBTITLE_SEARCH_TV,
        SUBBER_JOB_KIND_SUBTITLE_SEARCH_MOVIES,
        SUBBER_JOB_KIND_LIBRARY_SCAN_TV,
        SUBBER_JOB_KIND_LIBRARY_SCAN_MOVIES,
        SUBBER_JOB_KIND_LIBRARY_SYNC_TV,
        SUBBER_JOB_KIND_LIBRARY_SYNC_MOVIES,
        SUBBER_JOB_KIND_WEBHOOK_IMPORT_TV,
        SUBBER_JOB_KIND_WEBHOOK_IMPORT_MOVIES,
        SUBBER_JOB_KIND_SUBTITLE_UPGRADE,
    },
)
