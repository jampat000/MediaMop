"""In-process Trimmer worker handler for ``trimmer.supplied_trim_plan.json_file_write.v1``."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session, sessionmaker

from mediamop.core.config import MediaMopSettings
from mediamop.modules.trimmer.trimmer_supplied_trim_plan_json_file_write_activity import (
    record_trimmer_supplied_trim_plan_json_file_write_completed,
)
from mediamop.modules.trimmer.trimmer_supplied_trim_plan_json_file_write_paths import (
    trimmer_plan_exports_dir,
)
from mediamop.modules.trimmer.trimmer_trim_plan_constraints_evaluate import (
    evaluate_trim_plan_constraints,
)
from mediamop.modules.trimmer.worker_loop import TrimmerJobWorkContext


def make_trimmer_supplied_trim_plan_json_file_write_handler(
    settings: MediaMopSettings,
    session_factory: sessionmaker[Session],
) -> Callable[[TrimmerJobWorkContext], None]:
    """Validate trim plan JSON, then write canonical JSON under ``MEDIAMOP_HOME/trimmer/plan_exports/``.

    Does not read media files, run FFmpeg, transcode, or cut containers — file is the supplied segment list only.
    """

    def _run(ctx: TrimmerJobWorkContext) -> None:
        raw = (ctx.payload_json or "").strip()
        if not raw:
            detail_obj: dict[str, Any] = {"job_id": ctx.id, "ok": False, "reason": "missing payload_json"}
            detail = json.dumps(detail_obj, separators=(",", ":"))[:10_000]
            with session_factory() as session:
                with session.begin():
                    record_trimmer_supplied_trim_plan_json_file_write_completed(session, detail=detail)
            return

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            detail_obj = {"job_id": ctx.id, "ok": False, "reason": f"invalid json: {exc}"}
            detail = json.dumps(detail_obj, separators=(",", ":"))[:10_000]
            with session_factory() as session:
                with session.begin():
                    record_trimmer_supplied_trim_plan_json_file_write_completed(session, detail=detail)
            return

        if not isinstance(data, dict):
            detail_obj = {"job_id": ctx.id, "ok": False, "reason": "payload must be a JSON object"}
            detail = json.dumps(detail_obj, separators=(",", ":"))[:10_000]
            with session_factory() as session:
                with session.begin():
                    record_trimmer_supplied_trim_plan_json_file_write_completed(session, detail=detail)
            return

        ok, reason, ev_detail = evaluate_trim_plan_constraints(data)
        if not ok:
            detail_obj: dict[str, Any] = {"job_id": ctx.id, "ok": False}
            if reason:
                detail_obj["reason"] = reason
            detail_obj.update(ev_detail)
            detail = json.dumps(detail_obj, separators=(",", ":"))[:10_000]
            with session_factory() as session:
                with session.begin():
                    record_trimmer_supplied_trim_plan_json_file_write_completed(session, detail=detail)
            return

        outbox = trimmer_plan_exports_dir(settings.mediamop_home)
        outbox.mkdir(parents=True, exist_ok=True)
        file_name = f"trimmer-plan-job-{ctx.id}-{uuid4().hex}.json"
        out_path = outbox / file_name

        segments = data.get("segments")
        src = data.get("source_duration_sec")
        envelope = {
            "schema_kind": "trimmer.supplied_trim_plan.json_file_write.v1",
            "job_id": ctx.id,
            "segments": segments,
            "source_duration_sec": src,
        }
        try:
            text = json.dumps(envelope, indent=2, sort_keys=True, ensure_ascii=False)
            out_path.write_text(text, encoding="utf-8", newline="\n")
        except OSError as exc:
            detail_obj = {"job_id": ctx.id, "ok": False, "reason": f"write failed: {exc}"}
            detail = json.dumps(detail_obj, separators=(",", ":"))[:10_000]
            with session_factory() as session:
                with session.begin():
                    record_trimmer_supplied_trim_plan_json_file_write_completed(session, detail=detail)
            return

        rel = f"trimmer/plan_exports/{file_name}"
        detail_obj = {
            "job_id": ctx.id,
            "ok": True,
            "output_relative_path": rel,
            "output_absolute_path": str(out_path.resolve()),
        }
        detail_obj.update(ev_detail)
        detail = json.dumps(detail_obj, separators=(",", ":"))[:10_000]
        with session_factory() as session:
            with session.begin():
                record_trimmer_supplied_trim_plan_json_file_write_completed(session, detail=detail)

    return _run
