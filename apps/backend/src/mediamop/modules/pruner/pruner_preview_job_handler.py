"""Handler for ``pruner.candidate_removal.preview.v1`` (per-scope rule family previews)."""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from mediamop.core.config import MediaMopSettings
from mediamop.modules.pruner.pruner_constants import (
    RULE_FAMILY_MISSING_PRIMARY_MEDIA_REPORTED,
    RULE_FAMILY_NEVER_PLAYED_STALE_REPORTED,
    RULE_FAMILY_WATCHED_TV_REPORTED,
    clamp_never_played_min_age_days,
    pruner_preview_rule_families_jf_emby,
)
from mediamop.modules.pruner.pruner_credentials_envelope import decrypt_and_parse_envelope
from mediamop.modules.pruner.pruner_instances_service import get_scope_settings, get_server_instance
from mediamop.modules.pruner.pruner_plex_live_eligibility import plex_missing_primary_effective_max_items
from mediamop.modules.pruner.pruner_media_library import preview_payload_json, serialize_candidates
from mediamop.modules.pruner.pruner_preview_service import insert_preview_run
from mediamop.modules.pruner.worker_loop import PrunerJobWorkContext
from mediamop.platform.activity import constants as C
from mediamop.platform.activity.service import record_activity_event


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
        if is_scheduled and rule_family_id != RULE_FAMILY_MISSING_PRIMARY_MEDIA_REPORTED:
            msg = "scheduled preview may only target missing_primary_media_reported"
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
            max_items = max(1, min(int(sc.preview_max_items), 5000))
            age_days = clamp_never_played_min_age_days(int(sc.never_played_min_age_days))
            env = decrypt_and_parse_envelope(settings, inst.credentials_ciphertext)
            if env is None:
                msg = "cannot decrypt credentials (session secret missing or ciphertext invalid)"
                raise RuntimeError(msg)
            provider = str(env["provider"])
            secrets: dict[str, str] = env["secrets"]
            base_url = inst.base_url
            display_name = inst.display_name
            if provider == "plex" and rule_family_id == RULE_FAMILY_MISSING_PRIMARY_MEDIA_REPORTED:
                max_items = plex_missing_primary_effective_max_items(settings, int(sc.preview_max_items))

        try:
            outcome, unsup, cands, trunc = preview_payload_json(
                provider=provider,
                base_url=base_url,
                media_scope=scope,
                secrets=secrets,
                max_items=max_items,
                rule_family_id=rule_family_id,
                never_played_min_age_days=age_days if rule_family_id == RULE_FAMILY_NEVER_PLAYED_STALE_REPORTED else None,
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

        run_uuid = str(uuid.uuid4())
        label_scope = "TV (episodes)" if scope == "tv" else "Movies (one row per movie item)"
        if rule_family_id == RULE_FAMILY_MISSING_PRIMARY_MEDIA_REPORTED:
            rule_tag = "missing primary"
        elif rule_family_id == RULE_FAMILY_NEVER_PLAYED_STALE_REPORTED:
            rule_tag = "never-played stale"
        elif rule_family_id == RULE_FAMILY_WATCHED_TV_REPORTED:
            rule_tag = "watched TV"
        else:
            rule_tag = str(rule_family_id)
        title = (
            f"Scheduled Pruner preview ({rule_tag}): {display_name} ({provider}) — {label_scope}"
            if is_scheduled
            else f"Pruner preview ({rule_tag}): {display_name} ({provider}) — {label_scope}"
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
                detail_obj: dict[str, object] = {
                    "phase": "preview",
                    "preview_run_id": run_uuid,
                    "outcome": outcome,
                    "candidate_count": len(cands),
                    "truncated": trunc,
                    "rule_family_id": rule_family_id,
                    "trigger": "scheduled" if is_scheduled else "manual",
                }
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

    return _run
