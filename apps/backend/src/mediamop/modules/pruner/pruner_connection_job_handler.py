"""Handler for ``pruner.server_connection.test.v1``."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from mediamop.core.config import MediaMopSettings
from mediamop.modules.pruner.pruner_credentials_envelope import decrypt_and_parse_envelope
from mediamop.modules.pruner.pruner_instances_service import get_server_instance
from mediamop.modules.pruner.pruner_media_library import test_emby_jellyfin_connection, test_plex_connection
from mediamop.modules.pruner.worker_loop import PrunerJobWorkContext
from mediamop.platform.activity import constants as C
from mediamop.platform.activity.service import record_activity_event
from mediamop.platform.observability.diagnostics import DiagnosticAction, DiagnosticModule, DiagnosticResult, DiagnosticTrigger
from mediamop.platform.observability.operator_messages import activity_detail_envelope, connection_test_title


def _parse_payload(payload_json: str | None) -> dict[str, Any]:
    if not payload_json or not payload_json.strip():
        msg = "connection test job requires payload_json with server_instance_id"
        raise ValueError(msg)
    data = json.loads(payload_json)
    if not isinstance(data, dict):
        msg = "connection test payload must be a JSON object"
        raise ValueError(msg)
    return data


def make_pruner_server_connection_test_handler(
    settings: MediaMopSettings,
    session_factory: sessionmaker[Session],
) -> Callable[[PrunerJobWorkContext], None]:
    def _run(ctx: PrunerJobWorkContext) -> None:
        body = _parse_payload(ctx.payload_json)
        sid = body.get("server_instance_id")
        if not isinstance(sid, int):
            msg = "payload.server_instance_id must be an integer"
            raise ValueError(msg)

        with session_factory() as session:
            inst = get_server_instance(session, sid)
            if inst is None:
                msg = f"unknown server_instance_id={sid}"
                raise ValueError(msg)
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

        if provider in ("emby", "jellyfin"):
            ok, detail = test_emby_jellyfin_connection(
                base_url=base_url,
                api_key=secrets.get("api_key", ""),
            )
        elif provider == "plex":
            ok, detail = test_plex_connection(
                base_url=base_url,
                auth_token=secrets.get("auth_token"),
            )
        else:
            ok, detail = False, f"unsupported provider {provider!r}"

        when = datetime.now(timezone.utc)
        title = connection_test_title(module_label="Pruner", name=display_name, provider=provider, ok=ok)
        detail_s = (detail or "")[:10_000]
        result_for_message = DiagnosticResult.SUCCESS if ok else DiagnosticResult.FAILED
        activity_detail = {
            **activity_detail_envelope(
                module=DiagnosticModule.PRUNER,
                action=DiagnosticAction.CONNECTION_TEST,
                trigger=DiagnosticTrigger.MANUAL,
                result=result_for_message,
                provider=provider,
                user_message=detail_s or ("Connection test passed." if ok else "Connection test failed."),
                next_action=None if ok else "Check the server URL and credentials, then run the connection test again.",
            ),
            "detail": detail_s,
        }
        with session_factory() as session:
            with session.begin():
                inst2 = get_server_instance(session, sid)
                if inst2 is None:
                    return
                inst2.last_connection_test_at = when
                inst2.last_connection_test_ok = ok
                inst2.last_connection_test_detail = detail_s
                evt = (
                    C.PRUNER_CONNECTION_TEST_SUCCEEDED
                    if ok
                    else C.PRUNER_CONNECTION_TEST_FAILED
                )
                record_activity_event(
                    session,
                    event_type=evt,
                    module="pruner",
                    title=title,
                    detail=json.dumps(activity_detail, separators=(",", ":"))[:10_000],
                )

    return _run
