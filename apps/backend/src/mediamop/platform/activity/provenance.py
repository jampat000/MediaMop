"""Why a piece of work is happening, carried from where it starts to the events it produces (#469).

Work is started by a schedule, an operator, a media manager's webhook, a new file in a watched
folder, an automatic retry, or the worker following up on earlier work. That fact is known only
where the job is queued, so it rides on the job payload as ``trigger`` and, for work that belongs
to a larger run (a folder scan), ``run_id``. Handlers copy both into the Activity details they
write, and ``classify`` lifts them into columns people can filter by.
"""

from __future__ import annotations

from typing import Any

from mediamop.platform.activity.classify import TRIGGERS

#: The watched-folder scan's own words for why it ran, in the shared vocabulary.
SCAN_TRIGGER_TO_TRIGGER = {"manual": "manual", "periodic": "scheduled", "filesystem_event": "folder_change"}


def job_provenance(payload: Any) -> dict[str, Any]:
    """``trigger`` and ``run_id`` from a job payload, only when present and valid."""

    out: dict[str, Any] = {}
    if not isinstance(payload, dict):
        return out
    trigger = payload.get("trigger")
    if isinstance(trigger, str) and trigger.strip().lower() in TRIGGERS:
        out["trigger"] = trigger.strip().lower()
    run_id = payload.get("run_id")
    if isinstance(run_id, (str, int)) and not isinstance(run_id, bool) and str(run_id).strip():
        out["run_id"] = run_id
    return out


def with_provenance(detail: dict[str, Any], payload: Any) -> dict[str, Any]:
    """``detail`` with the job's trigger and run added, never overwriting what the detail says."""

    return {**job_provenance(payload), **detail}
