"""Handler for ``pruner.candidate_removal.plex_live.v1`` — Plex-only, no preview snapshot."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from mediamop.core.config import MediaMopSettings
from mediamop.modules.pruner.pruner_constants import RULE_FAMILY_MISSING_PRIMARY_MEDIA_REPORTED
from mediamop.modules.pruner.pruner_credentials_envelope import decrypt_and_parse_envelope
from mediamop.modules.pruner.pruner_instances_service import get_scope_settings, get_server_instance
from mediamop.modules.pruner.pruner_plex_library_delete import plex_delete_library_metadata
from mediamop.modules.pruner.pruner_plex_live_candidates import list_plex_missing_thumb_candidates
from mediamop.modules.pruner.pruner_plex_live_eligibility import effective_plex_live_cap
from mediamop.modules.pruner.worker_loop import PrunerJobWorkContext
from mediamop.platform.activity import constants as C
from mediamop.platform.activity.service import record_activity_event

_APPLY_TITLE_PREFIX = "Remove broken library entries"


def _parse_payload(payload_json: str | None) -> dict[str, Any]:
    if not payload_json or not payload_json.strip():
        msg = "plex live job requires payload_json"
        raise ValueError(msg)
    data = json.loads(payload_json)
    if not isinstance(data, dict):
        msg = "plex live payload must be a JSON object"
        raise ValueError(msg)
    return data


def _scope_label(media_scope: str) -> str:
    return "TV (episodes)" if media_scope == "tv" else "Movies (one row per movie item)"


def make_pruner_plex_live_removal_handler(
    settings: MediaMopSettings,
    session_factory: sessionmaker[Session],
) -> Callable[[PrunerJobWorkContext], None]:
    def _run(ctx: PrunerJobWorkContext) -> None:
        if not settings.pruner_apply_enabled:
            msg = "Pruner apply gate is off (MEDIAMOP_PRUNER_APPLY_ENABLED)."
            raise RuntimeError(msg)
        if not settings.pruner_plex_live_removal_enabled:
            msg = "Plex live removal is off (MEDIAMOP_PRUNER_PLEX_LIVE_REMOVAL_ENABLED)."
            raise RuntimeError(msg)

        body = _parse_payload(ctx.payload_json)
        sid = body.get("server_instance_id")
        scope = body.get("media_scope")
        rule_family_id = body.get("rule_family_id")
        if not isinstance(sid, int):
            msg = "payload.server_instance_id must be an integer"
            raise ValueError(msg)
        if not isinstance(scope, str) or scope not in ("tv", "movies"):
            msg = "payload.media_scope must be 'tv' or 'movies'"
            raise ValueError(msg)
        if str(rule_family_id or "") != RULE_FAMILY_MISSING_PRIMARY_MEDIA_REPORTED:
            msg = "payload.rule_family_id must match missing_primary_media_reported for this slice"
            raise ValueError(msg)

        with session_factory() as session:
            inst = get_server_instance(session, sid)
            if inst is None:
                msg = f"unknown server_instance_id={sid}"
                raise ValueError(msg)
            if str(inst.provider) != "plex":
                msg = "plex live handler refused non-plex instance"
                raise ValueError(msg)
            sc = get_scope_settings(session, server_instance_id=sid, media_scope=scope)
            if sc is None:
                msg = "scope row missing"
                raise ValueError(msg)
            if not bool(sc.missing_primary_media_reported_enabled):
                msg = "missing_primary_media_reported_enabled is false for this scope"
                raise ValueError(msg)
            cap = effective_plex_live_cap(settings, int(sc.preview_max_items))
            display_name = inst.display_name
            base_url = inst.base_url
            env = decrypt_and_parse_envelope(settings, inst.credentials_ciphertext)
            if env is None:
                msg = "cannot decrypt credentials (session secret missing or ciphertext invalid)"
                raise RuntimeError(msg)
            secrets = env.get("secrets") or {}
            token = str(secrets.get("auth_token") or secrets.get("plex_token") or "")

        if cap < 1:
            msg = "effective live cap is zero"
            raise ValueError(msg)
        if not token.strip():
            msg = "plex auth token missing in credentials envelope"
            raise ValueError(msg)

        candidates = list_plex_missing_thumb_candidates(
            base_url=base_url,
            auth_token=token,
            media_scope=scope,
            max_items=cap,
        )

        removed = 0
        skipped = 0
        failed = 0
        for c in candidates:
            item_id = str(c.get("item_id", "")).strip()
            if not item_id:
                failed += 1
                continue
            status, _body = plex_delete_library_metadata(
                base_url=base_url,
                auth_token=token,
                rating_key=item_id,
            )
            if status in (200, 204):
                removed += 1
            elif status == 404:
                skipped += 1
            else:
                failed += 1

        label = _scope_label(scope)
        title = f"Plex live: {_APPLY_TITLE_PREFIX}: {display_name} (plex) — {label}"
        detail_obj: dict[str, object] = {
            "action": _APPLY_TITLE_PREFIX,
            "live_mode": "plex",
            "preview_involved": False,
            "server_instance_id": sid,
            "provider": "plex",
            "media_scope": scope,
            "rule_family_id": RULE_FAMILY_MISSING_PRIMARY_MEDIA_REPORTED,
            "removed": removed,
            "skipped": skipped,
            "failed": failed,
            "live_scan_cap": cap,
            "semantics_note": (
                "Plex live path scans leaf items with empty/missing thumb on the item JSON; "
                "this is not the same as Jellyfin/Emby preview primary-image probes."
            ),
        }
        detail = json.dumps(detail_obj, separators=(",", ":"))[:10_000]
        evt = C.PRUNER_PLEX_LIVE_LIBRARY_REMOVAL_COMPLETED
        if removed == 0 and skipped == 0 and failed > 0:
            evt = C.PRUNER_PLEX_LIVE_LIBRARY_REMOVAL_FAILED
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
