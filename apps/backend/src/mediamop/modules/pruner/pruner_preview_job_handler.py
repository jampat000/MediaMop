"""Handler for ``pruner.candidate_removal.preview.v1`` (per-scope rule family previews)."""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Callable
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from mediamop.core.config import MediaMopSettings
from mediamop.modules.pruner.pruner_constants import (
    MEDIA_SCOPE_MOVIES,
    RULE_FAMILY_GENRE_MATCH_REPORTED,
    RULE_FAMILY_MISSING_PRIMARY_MEDIA_REPORTED,
    RULE_FAMILY_NEVER_PLAYED_STALE_REPORTED,
    RULE_FAMILY_PEOPLE_MATCH_REPORTED,
    RULE_FAMILY_STUDIO_MATCH_REPORTED,
    RULE_FAMILY_UNWATCHED_MOVIE_STALE_REPORTED,
    RULE_FAMILY_WATCHED_MOVIE_LOW_RATING_REPORTED,
    RULE_FAMILY_WATCHED_MOVIES_REPORTED,
    RULE_FAMILY_WATCHED_TV_REPORTED,
    RULE_FAMILY_YEAR_RANGE_MATCH_REPORTED,
    clamp_never_played_min_age_days,
    clamp_preview_year_bound,
    clamp_watched_movie_low_rating_max_jellyfin_emby_community_rating,
    clamp_watched_movie_low_rating_max_plex_audience_rating,
    pruner_preview_rule_families_jf_emby,
)
from mediamop.modules.pruner.pruner_credentials_envelope import decrypt_and_parse_envelope
from mediamop.modules.pruner.pruner_genre_filters import preview_genre_filters_from_db_column
from mediamop.modules.pruner.pruner_people_filters import (
    preview_people_filters_from_db_column,
    preview_people_roles_from_db_column,
)
from mediamop.modules.pruner.pruner_studio_collection_filters import (
    preview_collection_filters_from_db_column,
    preview_studio_filters_from_db_column,
)
from mediamop.modules.pruner.pruner_instances_service import get_scope_settings, get_server_instance
from mediamop.modules.pruner.pruner_job_kinds import PRUNER_CANDIDATE_REMOVAL_APPLY_JOB_KIND
from mediamop.modules.pruner.pruner_jobs_ops import pruner_enqueue_or_get_job
from mediamop.modules.pruner.pruner_plex_live_eligibility import plex_missing_primary_effective_max_items
from mediamop.modules.pruner.pruner_media_library import preview_payload_json, serialize_candidates
from mediamop.modules.pruner.pruner_preview_service import insert_preview_run
from mediamop.modules.pruner.worker_loop import PrunerJobWorkContext
from mediamop.platform.activity import constants as C
from mediamop.platform.activity.service import record_activity_event
from mediamop.platform.observability.diagnostics import DiagnosticAction, DiagnosticModule, DiagnosticResult, DiagnosticTrigger
from mediamop.platform.observability.operator_messages import activity_detail_envelope, provider_label, scan_title

logger = logging.getLogger(__name__)


def _parse_payload(payload_json: str | None) -> dict[str, Any]:
    if not payload_json or not payload_json.strip():
        msg = "preview job requires payload_json"
        raise ValueError(msg)
    data = json.loads(payload_json)
    if not isinstance(data, dict):
        msg = "preview payload must be a JSON object"
        raise ValueError(msg)
    return data


def make_pruner_candidate_removal_preview_handler(
    settings: MediaMopSettings,
    session_factory: sessionmaker[Session],
) -> Callable[[PrunerJobWorkContext], None]:
    def _run(ctx: PrunerJobWorkContext) -> None:
        body = _parse_payload(ctx.payload_json)
        sid = body.get("server_instance_id")
        scope = body.get("media_scope")
        trigger_raw = body.get("trigger")
        is_scheduled = trigger_raw == "scheduled"
        rule_raw = body.get("rule_family_id", RULE_FAMILY_MISSING_PRIMARY_MEDIA_REPORTED)
        rule_family_id = str(rule_raw)
        if not isinstance(sid, int):
            msg = "payload.server_instance_id must be an integer"
            raise ValueError(msg)
        if not isinstance(scope, str) or scope not in ("tv", "movies"):
            msg = "payload.media_scope must be 'tv' or 'movies'"
            raise ValueError(msg)
        if rule_family_id not in pruner_preview_rule_families_jf_emby():
            msg = "payload.rule_family_id is not supported for preview in this slice"
            raise ValueError(msg)
        if rule_family_id == RULE_FAMILY_WATCHED_MOVIES_REPORTED and scope != MEDIA_SCOPE_MOVIES:
            msg = "watched_movies_reported preview requires media_scope=movies"
            raise ValueError(msg)
        if rule_family_id in (
            RULE_FAMILY_WATCHED_MOVIE_LOW_RATING_REPORTED,
            RULE_FAMILY_UNWATCHED_MOVIE_STALE_REPORTED,
        ) and scope != MEDIA_SCOPE_MOVIES:
            msg = f"{rule_family_id} preview requires media_scope=movies"
            raise ValueError(msg)

        with session_factory() as session:
            inst = get_server_instance(session, sid)
            if inst is None:
                msg = f"unknown server_instance_id={sid}"
                raise ValueError(msg)
            sc = get_scope_settings(session, server_instance_id=sid, media_scope=scope)
            if sc is None:
                msg = "scope settings row missing"
                raise RuntimeError(msg)
            if rule_family_id == RULE_FAMILY_MISSING_PRIMARY_MEDIA_REPORTED:
                if not bool(sc.missing_primary_media_reported_enabled):
                    msg = "missing_primary_media_reported_enabled is false for this scope"
                    raise ValueError(msg)
            elif rule_family_id == RULE_FAMILY_NEVER_PLAYED_STALE_REPORTED:
                if not bool(sc.never_played_stale_reported_enabled):
                    msg = "never_played_stale_reported_enabled is false for this scope"
                    raise ValueError(msg)
            elif rule_family_id == RULE_FAMILY_WATCHED_TV_REPORTED:
                if not bool(sc.watched_tv_reported_enabled):
                    msg = "watched_tv_reported_enabled is false for this scope"
                    raise ValueError(msg)
            elif rule_family_id == RULE_FAMILY_WATCHED_MOVIES_REPORTED:
                if not bool(sc.watched_movies_reported_enabled):
                    msg = "watched_movies_reported_enabled is false for this scope"
                    raise ValueError(msg)
            elif rule_family_id == RULE_FAMILY_WATCHED_MOVIE_LOW_RATING_REPORTED:
                if not bool(sc.watched_movie_low_rating_reported_enabled):
                    msg = "watched_movie_low_rating_reported_enabled is false for this scope"
                    raise ValueError(msg)
            elif rule_family_id == RULE_FAMILY_UNWATCHED_MOVIE_STALE_REPORTED:
                if not bool(sc.unwatched_movie_stale_reported_enabled):
                    msg = "unwatched_movie_stale_reported_enabled is false for this scope"
                    raise ValueError(msg)
            max_items = max(1, min(int(sc.preview_max_items), 5000))
            age_days = clamp_never_played_min_age_days(int(sc.never_played_min_age_days))
            unwatched_stale_days = clamp_never_played_min_age_days(int(sc.unwatched_movie_stale_min_age_days))
            low_rating_jf = clamp_watched_movie_low_rating_max_jellyfin_emby_community_rating(
                float(sc.watched_movie_low_rating_max_jellyfin_emby_community_rating),
            )
            low_rating_plex = clamp_watched_movie_low_rating_max_plex_audience_rating(
                float(sc.watched_movie_low_rating_max_plex_audience_rating),
            )
            env = decrypt_and_parse_envelope(settings, inst.credentials_ciphertext)
            if env is None:
                msg = (
                    "Pruner credentials could not be read. Re-enter this server's credentials or migrate them with "
                    "the original MEDIAMOP_SESSION_SECRET and MEDIAMOP_CREDENTIALS_SECRET configured."
                )
                raise RuntimeError(msg)
            provider = str(env["provider"])
            secrets: dict[str, str] = env["secrets"]
            base_url = inst.base_url
            display_name = inst.display_name
            if provider == "plex" and rule_family_id == RULE_FAMILY_MISSING_PRIMARY_MEDIA_REPORTED:
                max_items = plex_missing_primary_effective_max_items(settings, int(sc.preview_max_items))
            preview_genres = preview_genre_filters_from_db_column(str(sc.preview_include_genres_json))
            preview_people = preview_people_filters_from_db_column(str(sc.preview_include_people_json))
            preview_people_roles = preview_people_roles_from_db_column(str(sc.preview_include_people_roles_json))
            preview_studios = preview_studio_filters_from_db_column(str(sc.preview_include_studios_json))
            preview_collections = preview_collection_filters_from_db_column(str(sc.preview_include_collections_json))
            preview_year_min = clamp_preview_year_bound(sc.preview_year_min)
            preview_year_max = clamp_preview_year_bound(sc.preview_year_max)
            auto_apply_enabled = bool(sc.auto_apply_enabled)
            max_deletes_per_run = max(1, min(int(sc.max_deletes_per_run), 5000))
            if preview_year_min is not None and preview_year_max is not None and preview_year_min > preview_year_max:
                msg = "preview_year_min is greater than preview_year_max for this scope"
                raise ValueError(msg)

        try:
            outcome, unsup, cands, trunc = preview_payload_json(
                provider=provider,
                base_url=base_url,
                media_scope=scope,
                secrets=secrets,
                max_items=max_items,
                rule_family_id=rule_family_id,
                never_played_min_age_days=age_days if rule_family_id == RULE_FAMILY_NEVER_PLAYED_STALE_REPORTED else None,
                preview_include_genres=preview_genres,
                preview_include_people=preview_people,
                preview_include_people_roles=preview_people_roles,
                watched_movie_low_rating_max_jellyfin_emby_community_rating=low_rating_jf
                if rule_family_id == RULE_FAMILY_WATCHED_MOVIE_LOW_RATING_REPORTED
                else None,
                watched_movie_low_rating_max_plex_audience_rating=low_rating_plex
                if rule_family_id == RULE_FAMILY_WATCHED_MOVIE_LOW_RATING_REPORTED
                else None,
                unwatched_movie_stale_min_age_days=unwatched_stale_days
                if rule_family_id == RULE_FAMILY_UNWATCHED_MOVIE_STALE_REPORTED
                else None,
                preview_year_min=preview_year_min,
                preview_year_max=preview_year_max,
                preview_include_studios=preview_studios,
            )
            cand_json = serialize_candidates(cands)
            err: str | None = None
        except Exception as exc:  # noqa: BLE001
            outcome = "failed"
            unsup = None
            cands = []
            trunc = False
            cand_json = "[]"
            err = str(exc)[:10_000]
            logger.exception(
                "Pruner preview failed server_instance_id=%s media_scope=%s rule_family_id=%s",
                sid,
                scope,
                rule_family_id,
            )

        run_uuid = str(uuid.uuid4())
        label_scope = "TV (episodes)" if scope == "tv" else "Movies (one row per movie item)"
        if rule_family_id == RULE_FAMILY_MISSING_PRIMARY_MEDIA_REPORTED:
            rule_tag = "missing primary"
        elif rule_family_id == RULE_FAMILY_NEVER_PLAYED_STALE_REPORTED:
            rule_tag = "never-played stale"
        elif rule_family_id == RULE_FAMILY_WATCHED_TV_REPORTED:
            rule_tag = "watched TV"
        elif rule_family_id == RULE_FAMILY_WATCHED_MOVIES_REPORTED:
            rule_tag = "watched movies"
        elif rule_family_id == RULE_FAMILY_WATCHED_MOVIE_LOW_RATING_REPORTED:
            rule_tag = "watched low-rating movies"
        elif rule_family_id == RULE_FAMILY_UNWATCHED_MOVIE_STALE_REPORTED:
            rule_tag = "unwatched stale movies"
        elif rule_family_id == RULE_FAMILY_GENRE_MATCH_REPORTED:
            rule_tag = "genre match"
        elif rule_family_id == RULE_FAMILY_STUDIO_MATCH_REPORTED:
            rule_tag = "studio match"
        elif rule_family_id == RULE_FAMILY_PEOPLE_MATCH_REPORTED:
            rule_tag = "people match"
        elif rule_family_id == RULE_FAMILY_YEAR_RANGE_MATCH_REPORTED:
            rule_tag = "year range match"
        else:
            rule_tag = str(rule_family_id)
        source_label = f"{display_name} ({provider_label(provider) or provider})"
        result_for_message = (
            DiagnosticResult.SUCCESS
            if outcome == "success"
            else DiagnosticResult.SKIPPED
            if outcome == "unsupported"
            else DiagnosticResult.FAILED
        )
        title = scan_title(
            module_label="Pruner preview",
            result=result_for_message,
            count=len(cands),
            scope=scope,
            source=source_label,
            scheduled=is_scheduled,
        )

        with session_factory() as session:
            with session.begin():
                insert_preview_run(
                    session,
                    preview_run_uuid=run_uuid,
                    server_instance_id=sid,
                    media_scope=scope,
                    rule_family_id=rule_family_id,
                    pruner_job_id=int(ctx.id),
                    candidate_count=len(cands),
                    candidates_json=cand_json,
                    truncated=trunc,
                    outcome=outcome,
                    unsupported_detail=unsup,
                    error_message=err,
                )
                auto_apply_queued = bool(
                    is_scheduled
                    and auto_apply_enabled
                    and settings.pruner_apply_enabled
                    and outcome == "success"
                    and len(cands) > 0,
                )
                detail_obj: dict[str, object] = {
                    **activity_detail_envelope(
                        module=DiagnosticModule.PRUNER,
                        action=DiagnosticAction.PREVIEW,
                        trigger=DiagnosticTrigger.SCHEDULED if is_scheduled else DiagnosticTrigger.MANUAL,
                        result=result_for_message,
                        provider=provider,
                        media_scope=scope,
                        counts={"checked": len(cands), "found": len(cands), "queued": int(auto_apply_queued)},
                        user_message=(
                            f"Pruner checked {label_scope} for {rule_tag} and found {len(cands)} item"
                            f"{'' if len(cands) == 1 else 's'}."
                        ),
                    ),
                    "phase": "preview",
                    "preview_run_id": run_uuid,
                    "outcome": outcome,
                    "candidate_count": len(cands),
                    "truncated": trunc,
                    "rule_family_id": rule_family_id,
                    "trigger": "scheduled" if is_scheduled else "manual",
                }
                if preview_genres:
                    detail_obj["preview_include_genres"] = list(preview_genres)
                if preview_people:
                    detail_obj["preview_include_people"] = list(preview_people)
                if preview_year_min is not None or preview_year_max is not None:
                    detail_obj["preview_year_min"] = preview_year_min
                    detail_obj["preview_year_max"] = preview_year_max
                if preview_studios:
                    detail_obj["preview_include_studios"] = list(preview_studios)
                if preview_collections and provider == "plex":
                    detail_obj["preview_include_collections"] = list(preview_collections)
                elif preview_collections and provider in ("jellyfin", "emby"):
                    detail_obj["preview_collections_ignored_note"] = (
                        "Collection include tokens are stored for this scope but not applied on Jellyfin/Emby previews "
                        "in this slice — the Items API path does not expose per-item library collection membership "
                        "without extra calls."
                    )
                if outcome == "success" and rule_family_id == RULE_FAMILY_GENRE_MATCH_REPORTED and preview_genres and len(cands) == 0:
                    detail_obj["preview_genre_rule_zero_candidates_note"] = (
                        "Zero rows matched your selected genres under the preview cap — the library may still contain "
                        "other genres, or matches may sit beyond the cap (try raising per-tab preview max)."
                    )
                if outcome == "success" and rule_family_id == RULE_FAMILY_PEOPLE_MATCH_REPORTED and preview_people and len(cands) == 0:
                    detail_obj["preview_people_rule_zero_candidates_note"] = (
                        "Zero rows matched your entered names under the preview cap — widen names, adjust roles "
                        "(Jellyfin/Emby), or raise the per-tab preview max if you expected matches."
                    )
                if provider == "plex" and rule_family_id == RULE_FAMILY_MISSING_PRIMARY_MEDIA_REPORTED:
                    detail_obj["plex_missing_primary_item_cap"] = max_items
                    detail_obj["plex_missing_primary_cap_note"] = (
                        "Plex missing-primary preview collects at most this many rows per run "
                        "(min per-scope preview cap, MEDIAMOP_PRUNER_PLEX_LIVE_ABS_MAX_ITEMS, and 5000 ceiling). "
                        "truncated=true means more matches existed upstream than this cap."
                    )
                if outcome == "unsupported" and unsup:
                    detail_obj["unsupported_detail"] = unsup[:2000]
                if err:
                    detail_obj["error"] = err[:2000]
                if auto_apply_queued:
                    detail_obj["auto_apply_queued"] = True
                    detail_obj["max_deletes_per_run"] = max_deletes_per_run
                elif is_scheduled and auto_apply_enabled and not settings.pruner_apply_enabled:
                    detail_obj["auto_apply_skipped"] = "Pruner apply is disabled for this MediaMop process."
                detail = json.dumps(detail_obj, separators=(",", ":"))[:10_000]
                if outcome == "success":
                    evt = C.PRUNER_PREVIEW_SUCCEEDED
                elif outcome == "unsupported":
                    evt = C.PRUNER_PREVIEW_UNSUPPORTED
                else:
                    evt = C.PRUNER_PREVIEW_FAILED
                record_activity_event(
                    session,
                    event_type=evt,
                    module="pruner",
                    title=title,
                    detail=detail,
                )
                if auto_apply_queued:
                    payload = {
                        "preview_run_uuid": run_uuid,
                        "server_instance_id": sid,
                        "media_scope": scope,
                        "rule_family_id": rule_family_id,
                        "auto_applied": True,
                        "max_deletes_per_run": max_deletes_per_run,
                    }
                    pruner_enqueue_or_get_job(
                        session,
                        dedupe_key=f"pruner:apply:auto:v1:{run_uuid}:{uuid.uuid4()}",
                        job_kind=PRUNER_CANDIDATE_REMOVAL_APPLY_JOB_KIND,
                        payload_json=json.dumps(payload, separators=(",", ":")),
                    )

    return _run
