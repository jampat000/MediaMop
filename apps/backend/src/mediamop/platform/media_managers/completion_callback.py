"""Report a finished hand-off back to the media manager that asked for it.

A hand-off is a loan, not a delivery: the manager still owns the import and is waiting
to be told the file is ready. Refiner therefore has to call back, and the job payload
carries everything needed to do it — which manager, which hand-off id, which of the
manager's libraries it belongs to, and the path it gave us to answer on.

Nothing here decides whether the manager imports. It reports an outcome; the manager
applies its own rules.

Two rules shape what gets reported (verified against Deluno's
``POST /api/integrations/processors/events``, 2026-09-16):

- **Only a final failure is reported.** Deluno imports a file it finds in the output
  folder for a hand-off that is still open, and stops looking once the hand-off is marked
  failed. A failure that will be retried, or that is about to be passed through, is not
  final — reporting it would close the hand-off and strand the file that follows.
- **``outputPath`` is a path on the manager's host.** Deluno refuses a completion whose
  path is not inside the library's processor output folder *as Deluno sees it*, which is
  not necessarily how MediaMop sees it (containers, mapped drives). The path is rebuilt
  under the manager's own folder when the manager names one.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path, PurePath, PurePosixPath, PureWindowsPath
from typing import Any

import httpx
from sqlalchemy.orm import Session

from mediamop.core.config import MediaMopSettings
from mediamop.platform.media_managers.connection_service import (
    connection_for_kind,
    resolve_callback_target,
)
from mediamop.platform.media_managers.manager_dialects import port_for_kind
from mediamop.platform.media_managers.manager_port import ManagerConnection

logger = logging.getLogger(__name__)

_TIMEOUT_SECONDS = 20.0

# Outcomes the remux pass can finish with that mean "the file is ready to import".
_SUCCESS_OUTCOMES = frozenset({"live_output_written", "live_skipped_not_required"})

_PASS_THROUGH_AFTER_FAILURE_MESSAGE = (
    "MediaMop could not process this file, so it handed the original back unchanged; it is ready to import."
)


@dataclass(frozen=True, slots=True)
class HandoffOrigin:
    """The manager-supplied half of a hand-off, carried on the job payload."""

    source_key: str
    handoff_id: str | None
    callback_path: str | None
    release_name: str | None
    library_id: str | None = None

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
            handoff_id=_optional_text(origin.get("handoff_id")),
            callback_path=_optional_text(origin.get("callback_path")),
            release_name=_optional_text(origin.get("release_name")),
            library_id=_optional_text(origin.get("library_id")),
        )


def _optional_text(value: Any) -> str | None:
    text = str(value).strip() if value else ""
    return text or None


def is_succeeded(result: dict[str, Any]) -> bool:
    outcome = str(result.get("outcome") or "").strip()
    return bool(result.get("ok")) and outcome in _SUCCESS_OUTCOMES


def build_completion_body(
    *,
    origin: HandoffOrigin,
    result: dict[str, Any],
    output_path: str | None = None,
) -> dict[str, Any]:
    """Shape the report. Deliberately small: an outcome, a path, and a reason.

    ``output_path`` overrides the local ``output_file`` with the same file expressed in the
    manager's own coordinates, when that translation was possible.
    """

    outcome = str(result.get("outcome") or "").strip()
    succeeded = is_succeeded(result)
    body: dict[str, Any] = {
        "handoffId": origin.handoff_id,
        "status": "completed" if succeeded else "failed",
        "processorName": "MediaMop Refiner",
    }
    if origin.library_id:
        body["libraryId"] = origin.library_id
    if origin.release_name:
        body["releaseName"] = origin.release_name
    if succeeded:
        output_file = output_path or result.get("output_file")
        if isinstance(output_file, str) and output_file.strip():
            body["outputPath"] = output_file.strip()
        body["message"] = _success_message(outcome, result)
    else:
        body["message"] = _failure_message(result)
        if result.get("rejected_cleanup_status") == "deleted":
            # The library's own "delete rejected files" setting removed it. No disposition is
            # claimed: "rejected" asks a manager to blocklist and search again, which that
            # setting never promised.
            body["sourceRemoved"] = True
        else:
            # The original stays exactly where the manager left it. Said explicitly so a
            # manager that can act on a rejected file never mistakes a held one for it.
            body["disposition"] = "held"
            body["sourceRemoved"] = False
        failure_class = result.get("failure_class")
        if isinstance(failure_class, str) and failure_class.strip():
            body["failureClass"] = failure_class.strip()
    return body


def _success_message(outcome: str, result: dict[str, Any]) -> str:
    if result.get("passed_through_after_failure") is True:
        return _PASS_THROUGH_AFTER_FAILURE_MESSAGE
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


def _pure_manager_path(path: str) -> PurePath:
    """A path in the manager's own style — the manager's host is not necessarily this one."""

    text = path.strip()
    looks_windows = "\\" in text or (len(text) >= 2 and text[1] == ":" and text[0].isalpha())
    return PureWindowsPath(text) if looks_windows else PurePosixPath(text)


def translate_output_path(*, output_file: str, local_output_folder: str, manager_output_folder: str) -> str | None:
    """``output_file`` rebuilt under the manager's output folder, or None when it is not under ours."""

    try:
        relative = Path(output_file).resolve().relative_to(Path(local_output_folder).resolve())
    except (OSError, ValueError):
        return None
    if not relative.parts:
        return None
    return str(_pure_manager_path(manager_output_folder).joinpath(*relative.parts))


def _manager_output_path(connection: ManagerConnection, *, origin: HandoffOrigin, result: dict[str, Any]) -> str | None:
    """The output file as the manager will see it, or None to fall back to the local path.

    Falling back is safe: the manager refuses a path outside its folder, and Deluno still
    imports the file from the folder on its own reconciliation pass.
    """

    output_file = result.get("output_file")
    local_folder = result.get("refiner_output_folder_resolved")
    if not origin.library_id or not isinstance(output_file, str) or not isinstance(local_folder, str):
        return None
    port = port_for_kind(connection.kind)
    if port is None:
        return None
    try:
        description = port.describe(connection)
    except Exception:  # noqa: BLE001 - a manifest problem must not stop the report
        logger.warning("Could not read %s's libraries to place the output path.", connection.label, exc_info=True)
        return None
    for library in description.libraries:
        if library.key == origin.library_id and library.processes_before_import and library.output_path:
            return translate_output_path(
                output_file=output_file,
                local_output_folder=local_folder,
                manager_output_folder=library.output_path,
            )
    return None


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

    succeeded = is_succeeded(result)
    if not succeeded and result.get("retry_scheduled") is True:
        return "skipped: the failure will be retried, so it is not final yet"
    if not succeeded and result.get("pass_through_queued") is True:
        return "skipped: the original is being handed back, which will be reported when it is delivered"

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

    output_path = None
    if succeeded:
        output_path = _manager_output_path(
            ManagerConnection(
                kind=connection.kind,
                name=connection.name,
                base_url=target.base_url,
                api_key=target.api_key or "",
                connection_id=connection.id,
            ),
            origin=origin,
            result=result,
        )

    body = build_completion_body(origin=origin, result=result, output_path=output_path)
    try:
        response = httpx.post(url, json=body, headers=headers, timeout=_TIMEOUT_SECONDS)
    except httpx.HTTPError as exc:
        logger.warning("Hand-off completion callback to %s failed: %s", url, exc)
        return f"failed: could not reach {connection.name} ({exc.__class__.__name__})"

    if response.is_success:
        return f"reported {body['status']} to {connection.name}"
    logger.warning("Hand-off completion callback to %s returned HTTP %s", url, response.status_code)
    return f"failed: {connection.name} answered HTTP {response.status_code}"
