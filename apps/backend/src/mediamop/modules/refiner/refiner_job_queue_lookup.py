"""Find the queued job that belongs to a file the operator is looking at.

The Files screen knows a relative path; the queue knows a payload. Nothing joined the
two, which is why "move this to the front" had nowhere to start.
"""

from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from mediamop.modules.refiner.file_remux_pass.job_kinds import REFINER_FILE_REMUX_PASS_JOB_KIND
from mediamop.modules.refiner.jobs_model import RefinerJob, RefinerJobStatus


def pending_remux_job_for_relative_path(session: Session, *, relative_path: str) -> RefinerJob | None:
    """The oldest pending remux job for this path, or None.

    Pending only. A leased job is already running and cannot be started earlier, so
    returning one would let the caller report a move that did not happen.
    """

    wanted = (relative_path or "").strip()
    if not wanted:
        return None
    rows = session.scalars(
        select(RefinerJob)
        .where(RefinerJob.job_kind == REFINER_FILE_REMUX_PASS_JOB_KIND)
        .where(RefinerJob.status == RefinerJobStatus.PENDING.value)
        .order_by(RefinerJob.id)
    ).all()
    for job in rows:
        raw = (job.payload_json or "").strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and data.get("relative_media_path") == wanted:
            return job
    return None
