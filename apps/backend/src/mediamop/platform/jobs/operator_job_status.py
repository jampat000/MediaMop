"""Plain-language status summaries for persisted background jobs.

Job rows retain the technical error for diagnostics, but the dashboard and inspection
screens need a useful answer to two questions: what happened, and what can I do next?
Keeping that translation here prevents every UI surface from inventing a different
interpretation of the same worker error.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class JobOperatorStatus:
    operator_message: str
    next_action: str
    technical_detail: str | None = None


def _clean(raw: object, *, limit: int = 1200) -> str:
    return " ".join(str(raw or "").split())[:limit]


def _payload(raw: str | None) -> dict[str, Any]:
    try:
        value = json.loads(raw or "{}")
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _file_name(payload: dict[str, Any]) -> str | None:
    path = payload.get("relative_media_path")
    return Path(path).name if isinstance(path, str) and path.strip() else None


def _technical_detail(last_error: str | None) -> str | None:
    value = _clean(last_error, limit=10_000)
    return value or None


def build_job_operator_status(
    *,
    module: str,
    job_kind: str,
    status: str,
    last_error: str | None,
    payload_json: str | None = None,
) -> JobOperatorStatus:
    """Translate one persisted job row into an operator message and next action."""

    label = module.title()
    payload = _payload(payload_json)
    file_name = _file_name(payload)
    subject = f" for {file_name}" if file_name else ""
    error = _clean(last_error, limit=10_000)
    lower = error.lower()
    technical = _technical_detail(last_error)

    if status == "pending":
        return JobOperatorStatus(
            operator_message=f"{label} has queued this work{subject}.",
            next_action="No action is needed. MediaMop will start it when the required worker capacity is available.",
            technical_detail=technical,
        )
    if status == "leased":
        return JobOperatorStatus(
            operator_message=f"{label} is working on this job{subject}.",
            next_action="No action is needed unless it stays here beyond the normal processing time; then open the job record.",
            technical_detail=technical,
        )
    if status == "completed":
        return JobOperatorStatus(
            operator_message=f"{label} finished this job{subject}.",
            next_action="No action is needed. Open the processing record if you want the detailed outcome.",
            technical_detail=technical,
        )
    if status == "cancelled":
        return JobOperatorStatus(
            operator_message=f"This {label} job was cancelled before a worker started it{subject}.",
            next_action=(
                "No action is needed. If the file still exists and should be processed, start it again from Files."
            ),
            technical_detail=technical,
        )
    if status == "handler_ok_finalize_failed":
        return JobOperatorStatus(
            operator_message=(
                f"The {label} work completed{subject}, but MediaMop could not finish saving the job result."
            ),
            next_action="Use Recover result below. MediaMop will not run the media work again.",
            technical_detail=technical,
        )

    if "database is locked" in lower or "database table is locked" in lower:
        if module.lower() == "refiner":
            return JobOperatorStatus(
                operator_message=(
                    f"MediaMop could not save the Refiner result while another local operation was using the database{subject}."
                ),
                next_action=(
                    "Try the file again. If it repeats, set Refiner ‘Files at once’ to 1, let the current work finish, and retry."
                ),
                technical_detail=technical,
            )
        return JobOperatorStatus(
            operator_message=f"MediaMop could not save the {label} result because another local operation was using the database.",
            next_action="Try the job again after the current local work finishes.",
            technical_detail=technical,
        )
    if (
        "not a supported refiner media" in lower
        or "unsupported refiner" in lower
        or "refiner does not process" in lower
    ):
        return JobOperatorStatus(
            operator_message=f"This file is not a supported Refiner media file for this pass{subject}.",
            next_action="Choose a supported video file or update the library’s media types, then start it again.",
            technical_detail=technical,
        )
    if "could not find this file" in lower or "file not found" in lower or "no such file" in lower:
        return JobOperatorStatus(
            operator_message=f"MediaMop could not find this file under the saved watched folder{subject}.",
            next_action="Check the library path or restore the file, then use Start again.",
            technical_detail=technical,
        )
    if "ffprobe failed" in lower or "could not read this media" in lower:
        return JobOperatorStatus(
            operator_message=f"Refiner could not read this media file{subject}.",
            next_action="Check that the file is complete and playable, then use Try again.",
            technical_detail=technical,
        )
    if "legacy refiner dry_run" in lower:
        return JobOperatorStatus(
            operator_message=f"This Refiner job was created with an older processing mode{subject}.",
            next_action="Remove the old entry from the Files list, then let the next scan create a current job.",
            technical_detail=technical,
        )
    if "modified too recently" in lower or "still being written" in lower:
        return JobOperatorStatus(
            operator_message=f"MediaMop is waiting for this file to finish changing{subject}.",
            next_action="Wait for the copy or import to finish, then use Check again from Refiner Files.",
            technical_detail=technical,
        )
    if "no retainable audio" in lower:
        return JobOperatorStatus(
            operator_message=f"Refiner could not build a safe audio plan for this file{subject}.",
            next_action="Check the file’s audio tracks and saved Refiner audio rules, then use Try again.",
            technical_detail=technical,
        )

    if status in {"failed", "error"}:
        return JobOperatorStatus(
            operator_message=f"{label} could not finish this job{subject}.",
            next_action=(
                "Open the related Files or Jobs screen for the explanation, fix the cause, and start it again."
            ),
            technical_detail=technical,
        )
    return JobOperatorStatus(
        operator_message=f"{label} needs a review for this job{subject}.",
        next_action="Open the related Jobs screen to inspect the current status.",
        technical_detail=technical,
    )


__all__ = ["JobOperatorStatus", "build_job_operator_status"]
