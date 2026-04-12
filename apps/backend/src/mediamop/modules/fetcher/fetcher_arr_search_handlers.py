"""Fetcher worker handlers for Sonarr/Radarr missing and upgrade search ``job_kind`` values."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any, Mapping

from sqlalchemy.orm import Session, sessionmaker

from mediamop.core.config import MediaMopSettings
from mediamop.modules.fetcher.fetcher_arr_search_activity import (
    record_missing_search_dispatched,
    record_missing_search_zero_manual,
    record_upgrade_search_dispatched,
    record_upgrade_search_zero_manual,
)
from mediamop.modules.fetcher.fetcher_arr_search_execution import (
    best_effort_tag_radarr_missing,
    best_effort_tag_radarr_upgrade,
    best_effort_tag_sonarr_missing,
    best_effort_tag_sonarr_upgrade,
    radarr_movie_title_lines,
    sonarr_episode_title_lines,
    trigger_radarr_movies_search,
    trigger_sonarr_episode_search,
)
from mediamop.modules.fetcher.fetcher_arr_search_selection import (
    drain_monitored_missing_with_cooldown,
    iter_radarr_monitored_missing_movies,
    iter_sonarr_monitored_missing_episodes,
    paginate_wanted_cutoff,
    prune_fetcher_arr_action_log,
    utc_now,
    wanted_queue_total_records,
)
from mediamop.modules.fetcher.fetcher_arr_v3_http import FetcherArrV3Client
from mediamop.modules.fetcher.fetcher_arr_search_schedule_window import fetcher_arr_search_schedule_in_window
from mediamop.modules.fetcher.fetcher_search_job_kinds import (
    FETCHER_ARR_SEARCH_JOB_KINDS,
    JOB_KIND_MISSING_SEARCH_RADARR_MONITORED_MOVIES_V1,
    JOB_KIND_MISSING_SEARCH_SONARR_MONITORED_EPISODES_V1,
    JOB_KIND_UPGRADE_SEARCH_RADARR_CUTOFF_UNMET_V1,
    JOB_KIND_UPGRADE_SEARCH_SONARR_CUTOFF_UNMET_V1,
)
from mediamop.modules.fetcher.fetcher_search_schedule_state_model import FetcherSearchScheduleStateRow
from mediamop.modules.fetcher.fetcher_worker_loop import FetcherJobWorkContext

logger = logging.getLogger(__name__)


def _parse_manual(payload_json: str | None) -> bool:
    try:
        blob = json.loads(payload_json or "{}")
    except json.JSONDecodeError:
        return False
    return blob.get("manual") is True


def _touch_schedule_state(session: Session, *, field: str, when: Any) -> None:
    row = session.get(FetcherSearchScheduleStateRow, 1)
    if row is None:
        row = FetcherSearchScheduleStateRow(id=1)
        session.add(row)
    setattr(row, field, when)


def build_fetcher_arr_search_job_handlers(
    settings: MediaMopSettings,
    session_factory: sessionmaker[Session],
) -> dict[str, Callable[[FetcherJobWorkContext], None]]:
    """Handlers keyed by :data:`FETCHER_ARR_SEARCH_JOB_KINDS`."""

    def _missing_sonarr(ctx: FetcherJobWorkContext) -> None:
        if not settings.fetcher_sonarr_missing_search_enabled:
            return
        manual = _parse_manual(ctx.payload_json)
        now = utc_now()
        if not manual and not fetcher_arr_search_schedule_in_window(
            schedule_enabled=settings.fetcher_sonarr_missing_search_schedule_enabled,
            schedule_days=settings.fetcher_sonarr_missing_search_schedule_days,
            schedule_start=settings.fetcher_sonarr_missing_search_schedule_start,
            schedule_end=settings.fetcher_sonarr_missing_search_schedule_end,
            timezone_name=settings.fetcher_arr_search_schedule_timezone,
            now=now,
        ):
            return
        base = settings.fetcher_sonarr_base_url
        key = settings.fetcher_sonarr_api_key
        if not base or not key:
            raise RuntimeError("Sonarr missing search requires MEDIAMOP_FETCHER_SONARR_BASE_URL and API key")
        client = FetcherArrV3Client(base, key)
        client.health_ok()
        limit = max(1, int(settings.fetcher_sonarr_missing_search_max_items_per_run))
        delay = max(1, min(int(settings.fetcher_sonarr_missing_search_retry_delay_minutes), 365 * 24 * 60))
        warnings: list[str] = []
        allowed_ids: list[int] = []
        allowed_recs: list[dict[str, Any]] = []
        pool = 0
        with session_factory() as session:
            with session.begin():
                prune_fetcher_arr_action_log(session, settings=settings, now=now)
                allowed_ids, allowed_recs, pool = drain_monitored_missing_with_cooldown(
                    client,
                    session,
                    entries=iter_sonarr_monitored_missing_episodes(client),
                    id_keys=("id", "episodeId"),
                    app="sonarr",
                    action="missing",
                    item_type="episode",
                    limit=limit,
                    cooldown_minutes=delay,
                    now=now,
                )
        if allowed_ids:
            w = best_effort_tag_sonarr_missing(client, allowed_recs)
            if w:
                warnings.append(w)
            trigger_sonarr_episode_search(client, allowed_ids)
        with session_factory() as session:
            with session.begin():
                _touch_schedule_state(session, field="sonarr_missing_last_run_at", when=now)
                if allowed_ids:
                    record_missing_search_dispatched(
                        session,
                        app="sonarr",
                        count=len(allowed_ids),
                        detail_lines=sonarr_episode_title_lines(allowed_recs),
                    )
                elif manual:
                    if pool > 0:
                        record_missing_search_zero_manual(session, app="sonarr", reason="retry_delay")
                    else:
                        record_missing_search_zero_manual(session, app="sonarr", reason="no_candidates")
        if warnings:
            logger.warning("%s", " | ".join(warnings))

    def _missing_radarr(ctx: FetcherJobWorkContext) -> None:
        if not settings.fetcher_radarr_missing_search_enabled:
            return
        manual = _parse_manual(ctx.payload_json)
        now = utc_now()
        if not manual and not fetcher_arr_search_schedule_in_window(
            schedule_enabled=settings.fetcher_radarr_missing_search_schedule_enabled,
            schedule_days=settings.fetcher_radarr_missing_search_schedule_days,
            schedule_start=settings.fetcher_radarr_missing_search_schedule_start,
            schedule_end=settings.fetcher_radarr_missing_search_schedule_end,
            timezone_name=settings.fetcher_arr_search_schedule_timezone,
            now=now,
        ):
            return
        base = settings.fetcher_radarr_base_url
        key = settings.fetcher_radarr_api_key
        if not base or not key:
            raise RuntimeError("Radarr missing search requires MEDIAMOP_FETCHER_RADARR_BASE_URL and API key")
        client = FetcherArrV3Client(base, key)
        client.health_ok()
        limit = max(1, int(settings.fetcher_radarr_missing_search_max_items_per_run))
        delay = max(1, min(int(settings.fetcher_radarr_missing_search_retry_delay_minutes), 365 * 24 * 60))
        warnings: list[str] = []
        allowed_ids: list[int] = []
        allowed_recs: list[dict[str, Any]] = []
        pool = 0
        with session_factory() as session:
            with session.begin():
                prune_fetcher_arr_action_log(session, settings=settings, now=now)
                allowed_ids, allowed_recs, pool = drain_monitored_missing_with_cooldown(
                    client,
                    session,
                    entries=iter_radarr_monitored_missing_movies(client),
                    id_keys=("id", "movieId"),
                    app="radarr",
                    action="missing",
                    item_type="movie",
                    limit=limit,
                    cooldown_minutes=delay,
                    now=now,
                )
        if allowed_ids:
            w = best_effort_tag_radarr_missing(client, allowed_ids)
            if w:
                warnings.append(w)
            trigger_radarr_movies_search(client, allowed_ids)
        with session_factory() as session:
            with session.begin():
                _touch_schedule_state(session, field="radarr_missing_last_run_at", when=now)
                if allowed_ids:
                    record_missing_search_dispatched(
                        session,
                        app="radarr",
                        count=len(allowed_ids),
                        detail_lines=radarr_movie_title_lines(allowed_recs),
                    )
                elif manual:
                    if pool > 0:
                        record_missing_search_zero_manual(session, app="radarr", reason="retry_delay")
                    else:
                        record_missing_search_zero_manual(session, app="radarr", reason="no_candidates")
        if warnings:
            logger.warning("%s", " | ".join(warnings))

    def _upgrade_sonarr(ctx: FetcherJobWorkContext) -> None:
        if not settings.fetcher_sonarr_upgrade_search_enabled:
            return
        manual = _parse_manual(ctx.payload_json)
        now = utc_now()
        if not manual and not fetcher_arr_search_schedule_in_window(
            schedule_enabled=settings.fetcher_sonarr_upgrade_search_schedule_enabled,
            schedule_days=settings.fetcher_sonarr_upgrade_search_schedule_days,
            schedule_start=settings.fetcher_sonarr_upgrade_search_schedule_start,
            schedule_end=settings.fetcher_sonarr_upgrade_search_schedule_end,
            timezone_name=settings.fetcher_arr_search_schedule_timezone,
            now=now,
        ):
            return
        base = settings.fetcher_sonarr_base_url
        key = settings.fetcher_sonarr_api_key
        if not base or not key:
            raise RuntimeError("Sonarr upgrade search requires MEDIAMOP_FETCHER_SONARR_BASE_URL and API key")
        client = FetcherArrV3Client(base, key)
        client.health_ok()
        limit = max(1, int(settings.fetcher_sonarr_upgrade_search_max_items_per_run))
        delay = max(1, min(int(settings.fetcher_sonarr_upgrade_search_retry_delay_minutes), 365 * 24 * 60))
        warnings: list[str] = []
        allowed_ids: list[int] = []
        allowed_recs: list[dict[str, Any]] = []
        cutoff_total = 0
        with session_factory() as session:
            with session.begin():
                prune_fetcher_arr_action_log(session, settings=settings, now=now)
                allowed_ids, allowed_recs, cutoff_total = paginate_wanted_cutoff(
                    client,
                    session,
                    app="sonarr",
                    action="upgrade",
                    item_type="episode",
                    id_keys=("id", "episodeId"),
                    limit=limit,
                    cooldown_minutes=delay,
                    now=now,
                )
        if allowed_ids:
            w = best_effort_tag_sonarr_upgrade(client, allowed_recs)
            if w:
                warnings.append(w)
            trigger_sonarr_episode_search(client, allowed_ids)
        with session_factory() as session:
            with session.begin():
                _touch_schedule_state(session, field="sonarr_upgrade_last_run_at", when=now)
                if allowed_ids:
                    record_upgrade_search_dispatched(
                        session,
                        app="sonarr",
                        count=len(allowed_ids),
                        detail_lines=sonarr_episode_title_lines(allowed_recs),
                    )
                elif manual:
                    if cutoff_total > 0:
                        record_upgrade_search_zero_manual(session, app="sonarr", reason="retry_delay")
                    else:
                        record_upgrade_search_zero_manual(session, app="sonarr", reason="no_candidates")
        if warnings:
            logger.warning("%s", " | ".join(warnings))

    def _upgrade_radarr(ctx: FetcherJobWorkContext) -> None:
        if not settings.fetcher_radarr_upgrade_search_enabled:
            return
        manual = _parse_manual(ctx.payload_json)
        now = utc_now()
        if not manual and not fetcher_arr_search_schedule_in_window(
            schedule_enabled=settings.fetcher_radarr_upgrade_search_schedule_enabled,
            schedule_days=settings.fetcher_radarr_upgrade_search_schedule_days,
            schedule_start=settings.fetcher_radarr_upgrade_search_schedule_start,
            schedule_end=settings.fetcher_radarr_upgrade_search_schedule_end,
            timezone_name=settings.fetcher_arr_search_schedule_timezone,
            now=now,
        ):
            return
        base = settings.fetcher_radarr_base_url
        key = settings.fetcher_radarr_api_key
        if not base or not key:
            raise RuntimeError("Radarr upgrade search requires MEDIAMOP_FETCHER_RADARR_BASE_URL and API key")
        client = FetcherArrV3Client(base, key)
        client.health_ok()
        limit = max(1, int(settings.fetcher_radarr_upgrade_search_max_items_per_run))
        delay = max(1, min(int(settings.fetcher_radarr_upgrade_search_retry_delay_minutes), 365 * 24 * 60))
        warnings: list[str] = []
        allowed_ids: list[int] = []
        allowed_recs: list[dict[str, Any]] = []
        cutoff_total = 0
        with session_factory() as session:
            with session.begin():
                prune_fetcher_arr_action_log(session, settings=settings, now=now)
                allowed_ids, allowed_recs, cutoff_total = paginate_wanted_cutoff(
                    client,
                    session,
                    app="radarr",
                    action="upgrade",
                    item_type="movie",
                    id_keys=("id", "movieId"),
                    limit=limit,
                    cooldown_minutes=delay,
                    now=now,
                )
        if allowed_ids:
            w = best_effort_tag_radarr_upgrade(client, allowed_ids)
            if w:
                warnings.append(w)
            trigger_radarr_movies_search(client, allowed_ids)
        with session_factory() as session:
            with session.begin():
                _touch_schedule_state(session, field="radarr_upgrade_last_run_at", when=now)
                if allowed_ids:
                    record_upgrade_search_dispatched(
                        session,
                        app="radarr",
                        count=len(allowed_ids),
                        detail_lines=radarr_movie_title_lines(allowed_recs),
                    )
                elif manual:
                    if cutoff_total > 0:
                        record_upgrade_search_zero_manual(session, app="radarr", reason="retry_delay")
                    else:
                        record_upgrade_search_zero_manual(session, app="radarr", reason="no_candidates")
        if warnings:
            logger.warning("%s", " | ".join(warnings))

    out: dict[str, Callable[[FetcherJobWorkContext], None]] = {
        JOB_KIND_MISSING_SEARCH_SONARR_MONITORED_EPISODES_V1: _missing_sonarr,
        JOB_KIND_MISSING_SEARCH_RADARR_MONITORED_MOVIES_V1: _missing_radarr,
        JOB_KIND_UPGRADE_SEARCH_SONARR_CUTOFF_UNMET_V1: _upgrade_sonarr,
        JOB_KIND_UPGRADE_SEARCH_RADARR_CUTOFF_UNMET_V1: _upgrade_radarr,
    }
    if set(out) != FETCHER_ARR_SEARCH_JOB_KINDS:
        raise RuntimeError(f"fetcher arr search handler registry drift: {set(out)!r}")
    return out


def merge_fetcher_failed_import_and_search_handlers(
    failed_import_handlers: Mapping[str, Callable[[FetcherJobWorkContext], None]],
    settings: MediaMopSettings,
    session_factory: sessionmaker[Session],
) -> dict[str, Callable[[FetcherJobWorkContext], None]]:
    """Production registry: failed-import drives + Arr search jobs."""

    merged: dict[str, Callable[[FetcherJobWorkContext], None]] = {
        **dict(failed_import_handlers),
        **build_fetcher_arr_search_job_handlers(settings, session_factory),
    }
    return merged
