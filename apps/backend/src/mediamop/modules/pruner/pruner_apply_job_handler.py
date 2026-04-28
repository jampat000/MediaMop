"""Handler for ``pruner.candidate_removal.apply.v1`` — Jellyfin, Emby, and Plex (snapshot-bound)."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from mediamop.core.config import MediaMopSettings
from mediamop.modules.pruner.pruner_constants import (
    MEDIA_SCOPE_MOVIES,
    MEDIA_SCOPE_TV,
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
    pruner_apply_operator_label,
)
from mediamop.modules.pruner.pruner_credentials_envelope import decrypt_and_parse_envelope
from mediamop.modules.pruner.pruner_instances_service import get_server_instance
from mediamop.modules.pruner.pruner_emby_library_delete import emby_delete_library_item
from mediamop.modules.pruner.pruner_jellyfin_library_delete import jellyfin_delete_library_item
from mediamop.modules.pruner.pruner_plex_library_delete import plex_delete_library_metadata
from mediamop.modules.pruner.pruner_preview_run_model import PrunerPreviewRun
from mediamop.modules.pruner.worker_loop import PrunerJobWorkContext
from mediamop.platform.activity import constants as C
from mediamop.platform.activity.service import record_activity_event

_APPLY_SUPPORTED = frozenset(
    {
        RULE_FAMILY_MISSING_PRIMARY_MEDIA_REPORTED,
        RULE_FAMILY_NEVER_PLAYED_STALE_REPORTED,
        RULE_FAMILY_WATCHED_TV_REPORTED,
        RULE_FAMILY_WATCHED_MOVIES_REPORTED,
        RULE_FAMILY_WATCHED_MOVIE_LOW_RATING_REPORTED,
        RULE_FAMILY_UNWATCHED_MOVIE_STALE_REPORTED,
        RULE_FAMILY_GENRE_MATCH_REPORTED,
        RULE_FAMILY_STUDIO_MATCH_REPORTED,
        RULE_FAMILY_PEOPLE_MATCH_REPORTED,
        RULE_FAMILY_YEAR_RANGE_MATCH_REPORTED,
    },
)


def _parse_payload(payload_json: str | None) -> dict[str, Any]:
    if not payload_json or not payload_json.strip():
        msg = "apply job requires payload_json"
        raise ValueError(msg)
    data = json.loads(payload_json)
    if not isinstance(data, dict):
        msg = "apply payload must be a JSON object"
        raise ValueError(msg)
    return data


def _scope_label(media_scope: str) -> str:
    return "TV (episodes)" if media_scope == "tv" else "Movies (one row per movie item)"


def make_pruner_candidate_removal_apply_handler(
    settings: MediaMopSettings,
    session_factory: sessionmaker[Session],
) -> Callable[[PrunerJobWorkContext], None]:
    def _run(ctx: PrunerJobWorkContext) -> None:
        if not settings.pruner_apply_enabled:
            msg = "Pruner apply is disabled (MEDIAMOP_PRUNER_APPLY_ENABLED)."
            raise RuntimeError(msg)

        body = _parse_payload(ctx.payload_json)
        preview_run_uuid = body.get("preview_run_uuid")
        sid = body.get("server_instance_id")
        scope = body.get("media_scope")
        rule_family_id = body.get("rule_family_id")
        auto_applied = bool(body.get("auto_applied", False))
        max_deletes_raw = body.get("max_deletes_per_run")
        if not isinstance(preview_run_uuid, str) or len(preview_run_uuid) < 36:
            msg = "payload.preview_run_uuid must be a non-empty string (UUID)"
            raise ValueError(msg)
        if not isinstance(sid, int):
            msg = "payload.server_instance_id must be an integer"
            raise ValueError(msg)
        if not isinstance(scope, str) or scope not in ("tv", "movies"):
            msg = "payload.media_scope must be 'tv' or 'movies'"
            raise ValueError(msg)
        rid = str(rule_family_id or "")
        if rid not in _APPLY_SUPPORTED:
            msg = "payload.rule_family_id is not supported for apply in this slice"
            raise ValueError(msg)

        with session_factory() as session:
            inst = get_server_instance(session, sid)
            if inst is None:
                msg = f"unknown server_instance_id={sid}"
                raise ValueError(msg)
            prov = str(inst.provider)
            if prov not in ("jellyfin", "emby", "plex"):
                msg = "apply is supported for Jellyfin, Emby, and Plex instances only in this release"
                raise ValueError(msg)
            run = session.scalars(
                select(PrunerPreviewRun).where(
                    PrunerPreviewRun.preview_run_id == preview_run_uuid,
                    PrunerPreviewRun.server_instance_id == sid,
                ),
            ).first()
            if run is None:
                msg = "preview snapshot not found for this instance"
                raise ValueError(msg)
            if str(run.media_scope) != scope:
                msg = "preview snapshot media_scope does not match payload"
                raise ValueError(msg)
            snap_rule = str(run.rule_family_id)
            if snap_rule == RULE_FAMILY_WATCHED_TV_REPORTED and str(run.media_scope) != MEDIA_SCOPE_TV:
                msg = "watched_tv_reported apply requires a TV scope preview snapshot"
                raise ValueError(msg)
            if snap_rule == RULE_FAMILY_WATCHED_MOVIES_REPORTED and str(run.media_scope) != MEDIA_SCOPE_MOVIES:
                msg = "watched_movies_reported apply requires a Movies scope preview snapshot"
                raise ValueError(msg)
            if snap_rule == RULE_FAMILY_WATCHED_MOVIE_LOW_RATING_REPORTED and str(run.media_scope) != MEDIA_SCOPE_MOVIES:
                msg = "watched_movie_low_rating_reported apply requires a Movies scope preview snapshot"
                raise ValueError(msg)
            if snap_rule == RULE_FAMILY_UNWATCHED_MOVIE_STALE_REPORTED and str(run.media_scope) != MEDIA_SCOPE_MOVIES:
                msg = "unwatched_movie_stale_reported apply requires a Movies scope preview snapshot"
                raise ValueError(msg)
            if snap_rule != rid:
                msg = "payload.rule_family_id must match preview snapshot rule_family_id"
                raise ValueError(msg)
            if snap_rule not in _APPLY_SUPPORTED:
                msg = "preview snapshot rule_family_id is not eligible for apply"
                raise ValueError(msg)
            if str(run.outcome) != "success":
                msg = "preview snapshot outcome must be success to apply"
                raise ValueError(msg)
            cand_raw = run.candidates_json or "[]"
            try:
                parsed = json.loads(cand_raw)
            except json.JSONDecodeError as e:
                msg = f"preview candidates_json is not valid JSON: {e}"
                raise ValueError(msg) from e
            if not isinstance(parsed, list):
                msg = "preview candidates_json must be a JSON array"
                raise ValueError(msg)
            candidates: list[dict[str, Any]] = [x for x in parsed if isinstance(x, dict)]
            cap = int(run.candidate_count)
            if cap < 0:
                cap = 0
            if max_deletes_raw is not None:
                try:
                    cap = min(cap, max(1, min(int(max_deletes_raw), 5000)))
                except (TypeError, ValueError):
                    msg = "payload.max_deletes_per_run must be an integer when provided"
                    raise ValueError(msg) from None
            if len(candidates) > cap:
                candidates = candidates[:cap]
            display_name = inst.display_name
            base_url = inst.base_url
            env = decrypt_and_parse_envelope(settings, inst.credentials_ciphertext)
            if env is None:
                msg = (
                    "Pruner credentials could not be read. Re-enter this server's credentials or migrate them with "
                    "the original MEDIAMOP_SESSION_SECRET and MEDIAMOP_CREDENTIALS_SECRET configured."
                )
                raise RuntimeError(msg)
            secrets = env.get("secrets") or {}
            api_key = str(secrets.get("api_key", ""))
            plex_token = str(secrets.get("auth_token") or secrets.get("plex_token") or "")
            provider_for_delete = prov

        if not candidates:
            msg = "no candidates in preview snapshot"
            raise ValueError(msg)

        action_label = pruner_apply_operator_label(rid)

        removed = 0
        skipped = 0
        failed = 0
        for c in candidates:
            item_id = str(c.get("item_id", "")).strip()
            if not item_id:
                failed += 1
                continue
            if provider_for_delete == "emby":
                status, _err_body = emby_delete_library_item(
                    base_url=base_url,
                    api_key=api_key,
                    item_id=item_id,
                )
            elif provider_for_delete == "plex":
                if not plex_token.strip():
                    failed += 1
                    continue
                status, _err_body = plex_delete_library_metadata(
                    base_url=base_url,
                    auth_token=plex_token,
                    rating_key=item_id,
                )
            else:
                status, _err_body = jellyfin_delete_library_item(
                    base_url=base_url,
                    api_key=api_key,
                    item_id=item_id,
                )
            if status in (200, 204):
                removed += 1
            elif status == 404:
                skipped += 1
            else:
                failed += 1

        label = _scope_label(scope)
        title = f"{action_label}: {display_name} ({provider_for_delete}) — {label} — from preview snapshot"
        detail_obj: dict[str, object] = {
            "phase": "apply",
            "action": action_label,
            "preview_run_id": preview_run_uuid,
            "server_instance_id": sid,
            "provider": provider_for_delete,
            "media_scope": scope,
            "rule_family_id": rid,
            "removed": removed,
            "deleted_count": removed,
            "skipped": skipped,
            "failed": failed,
            "auto_applied": auto_applied,
            "max_deletes_per_run": max_deletes_raw,
            "note": "Skipped usually means the library entry was already gone. This path does not re-run preview.",
        }
        detail = json.dumps(detail_obj, separators=(",", ":"))[:10_000]
        evt = C.PRUNER_APPLY_LIBRARY_REMOVAL_COMPLETED
        if removed == 0 and skipped == 0 and failed > 0:
            evt = C.PRUNER_APPLY_LIBRARY_REMOVAL_FAILED
        with session_factory() as session:
            with session.begin():
                record_activity_event(
                    session,
                    event_type=evt,
                    module="pruner",
                    title=title,
                    detail=detail,
                )

    return _run
