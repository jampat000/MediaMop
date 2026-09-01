"""Report a finished hand-off back to the media manager that asked for it.

A hand-off is a loan, not a delivery: the manager still owns the import and is waiting
to be told the file is ready. Refiner therefore has to call back, and the job payload
carries everything needed to do it — which manager, which hand-off id, and the path it
gave us to answer on.

Nothing here decides whether the manager imports. It reports an outcome; the manager
applies its own rules.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

import httpx
from sqlalchemy.orm import Session

from mediamop.core.config import MediaMopSettings
from mediamop.platform.media_managers.connection_service import (
    connection_for_kind,
    resolve_callback_target,
)

logger = logging.getLogger(__name__)

_TIMEOUT_SECONDS = 20.0

# Outcomes the remux pass can finish with that mean "the file is ready to import".
_SUCCESS_OUTCOMES = frozenset({"live_output_written", "live_skipped_not_required"})


@dataclass(frozen=True, slots=True)
class HandoffOrigin:
    """The manager-supplied half of a hand-off, carried on the job payload."""

    source_key: str
    handoff_id: str | None
    callback_path: str | None
    release_name: str | None

    @classmethod
    def from_payload(cls, payload: Any) -> HandoffOrigin | None:
        if not isinstance(payload, dict):
            return None
        origin = payload.get("origin")
        if not isinstance(origin, dict):
            return None
        source_key = str(origin.get("source_key") or "").strip()
        if not source_key:
            return None
        return cls(
            source_key=source_key,
            handoff_id=(str(origin["handoff_id"]).strip() if origin.get("handoff_id") else None),
            callback_path=(str(origin["callback_path"]).strip() if origin.get("callback_path") else None),
            release_name=(str(origin["release_name"]).strip() if origin.get("release_name") else None),
        )


def build_completion_body(*, origin: HandoffOrigin, result: dict[str, Any]) -> dict[str, Any]:
    """Shape the report. Deliberately small: an outcome, a path, and a reason."""

    outcome = str(result.get("outcome") or "").strip()
    succeeded = bool(result.get("ok")) and outcome in _SUCCESS_OUTCOMES
    body: dict[str, Any] = {
        "handoffId": origin.handoff_id,
        "status": "completed" if succeeded else "failed",
        "processorName": "MediaMop Refiner",
    }
    if origin.release_name:
        body["releaseName"] = origin.release_name
    if succeeded:
        output_file = result.get("output_file")
        if isinstance(output_file, str) and output_file.strip():
            body["outputPath"] = output_file.strip()
        body["message"] = _success_message(outcome, result)
    else:
        body["message"] = _failure_message(result)
    return body


def _success_message(outcome: str, result: dict[str, Any]) -> str:
    if result.get("pass_through_unchanged") is True:
        return "The operator passed this file through unchanged; it is ready in the output folder."
    if outcome == "live_skipped_not_required":
        return "No remux was needed; the file was already in the wanted shape."
    removed_audio = result.get("removed_audio")
    removed_subs = result.get("removed_subtitles")
    parts = []
    if isinstance(removed_audio, list) and removed_audio:
        parts.append(f"{len(removed_audio)} audio track(s)")
    if isinstance(removed_subs, list) and removed_subs:
        parts.append(f"{len(removed_subs)} subtitle track(s)")
    if not parts:
        return "Remux finished."
    return "Removed " + " and ".join(parts) + "."


def _failure_message(result: dict[str, Any]) -> str:
    for key in ("reason", "output_completeness_note", "source_folder_skip_reason"):
        value = result.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return "The processing pass did not produce a usable output."


def report_handoff_completion(
    session: Session,
    settings: MediaMopSettings,
    *,
    payload_json: str | None,
    result: dict[str, Any],
) -> str:
    """Post the outcome back to the originating manager.

    Returns a short status for logging and activity. Never raises: a manager being
    unreachable must not fail a remux that already succeeded on disk.
    """

    try:
        payload = json.loads(payload_json) if payload_json else None
    except json.JSONDecodeError:
        return "skipped: job payload is not readable"

    origin = HandoffOrigin.from_payload(payload)
    if origin is None:
        return "skipped: not a hand-off"
    if not origin.callback_path:
        return "skipped: the hand-off named no callback path"

    connection = connection_for_kind(session, origin.source_key)
    if connection is None:
        return f"skipped: no enabled {origin.source_key} connection is configured to report back to"

    target = resolve_callback_target(settings, connection)
    if target is None:
        return f"skipped: the {connection.name} connection has no address saved"

    url = f"{target.base_url}/{origin.callback_path.lstrip('/')}"
    headers = {"Content-Type": "application/json"}
    if target.api_key:
        headers["X-Api-Key"] = target.api_key

    body = build_completion_body(origin=origin, result=result)
    try:
        response = httpx.post(url, json=body, headers=headers, timeout=_TIMEOUT_SECONDS)
    except httpx.HTTPError as exc:
        logger.warning("Hand-off completion callback to %s failed: %s", url, exc)
        return f"failed: could not reach {connection.name} ({exc.__class__.__name__})"

    if response.is_success:
        return f"reported {body['status']} to {connection.name}"
    logger.warning("Hand-off completion callback to %s returned HTTP %s", url, response.status_code)
    return f"failed: {connection.name} answered HTTP {response.status_code}"
