"""Drive the Python job queue against a database file, for the .NET cross-backend tests.

Usage: python python_queue_driver.py <backend-src> <db-path> <ops-json-file>
Prints one JSON line: {"weir_file": ..., "results": [...]}.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime


def main() -> None:
    backend_src, db_path, ops_path = sys.argv[1], sys.argv[2], sys.argv[3]
    sys.path.insert(0, backend_src)

    import weir
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session, sessionmaker

    from weir.core.db import _register_sqlite_datetime_adapters
    from weir.platform.jobs.startup_recovery import recover_incomplete_jobs_after_startup
    from weir.platform.suite_settings.model import SuiteSettingsRow
    from weir.refiner.jobs_model import RefinerJob
    from weir.refiner.jobs_ops import (
        claim_next_eligible_refiner_job,
        complete_claimed_refiner_job,
        fail_claimed_refiner_job,
        refiner_enqueue_or_get_job,
    )
    from weir.refiner.refiner_work_admission import evaluate_work_admission
    from weir.refiner.worker_loop import process_one_refiner_job

    _register_sqlite_datetime_adapters()
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False, "timeout": 30.0}, future=True)
    factory = sessionmaker(bind=engine, class_=Session, autoflush=False, autocommit=False, expire_on_commit=False, future=True)

    def when(text: str | None) -> datetime | None:
        return datetime.fromisoformat(text) if text else None

    def raw_row(job_id: int) -> dict[str, object] | None:
        connection = sqlite3.connect(db_path)
        connection.row_factory = sqlite3.Row
        try:
            row = connection.execute("SELECT * FROM refiner_jobs WHERE id = ?", (job_id,)).fetchone()
            return dict(row) if row is not None else None
        finally:
            connection.close()

    results: list[object] = []
    with open(ops_path, encoding="utf-8") as handle:
        ops = json.load(handle)
    for op in ops:
        name = op["op"]
        if name == "enqueue":
            with factory() as session:
                job = refiner_enqueue_or_get_job(
                    session,
                    dedupe_key=op["key"],
                    job_kind=op["kind"],
                    payload_json=op.get("payload"),
                    max_attempts=op.get("max_attempts", 3),
                )
                session.commit()
                results.append({"id": job.id})
        elif name == "claim":
            now = when(op["now"])
            from datetime import timedelta

            with factory() as session:
                job = claim_next_eligible_refiner_job(
                    session,
                    lease_owner=op["owner"],
                    lease_expires_at=now + timedelta(seconds=op["lease_seconds"]),
                    now=now,
                )
                session.commit()
                results.append(None if job is None else {"id": job.id, "attempt_count": job.attempt_count})
        elif name == "complete":
            with factory() as session:
                ok = complete_claimed_refiner_job(session, job_id=op["id"], lease_owner=op["owner"], now=when(op["now"]))
                session.commit()
                results.append({"ok": ok})
        elif name == "fail":
            with factory() as session:
                ok = fail_claimed_refiner_job(
                    session, job_id=op["id"], lease_owner=op["owner"], error_message=op["error"], now=when(op["now"])
                )
                session.commit()
                results.append({"ok": ok})
        elif name == "process":
            message = op.get("raise")

            def handler(_ctx, message=message):
                if message:
                    raise RuntimeError(message)

            outcome = process_one_refiner_job(
                factory,
                lease_owner=op["owner"],
                job_handlers={op["kind"]: handler},
                now=when(op["now"]),
                lease_seconds=op.get("lease_seconds", 300),
            )
            results.append({"outcome": outcome})
        elif name == "pause":
            with factory() as session:
                row = session.get(SuiteSettingsRow, 1)
                row.processing_paused = True
                row.scan_while_paused = bool(op.get("scan_while_paused", True))
                row.processing_paused_until = when(op.get("until"))
                session.commit()
                results.append({"ok": True})
        elif name == "admission":
            with factory() as session:
                admission = evaluate_work_admission(session, now=when(op["now"]))
                results.append(
                    {
                        "paused": admission.pause.paused,
                        "blocked": sorted(admission.blocked_library_ids),
                        "available": admission.available_units,
                    }
                )
        elif name == "recover":
            with factory() as session, session.begin():
                result = recover_incomplete_jobs_after_startup(session, now=when(op["now"]))
                results.append(result.as_log_dict())
        elif name == "get":
            results.append(raw_row(op["id"]))
        elif name == "orm_get":
            with factory() as session:
                job = session.scalars(select(RefinerJob).where(RefinerJob.id == op["id"])).one()
                results.append(
                    {
                        "status": job.status,
                        "lease_expires_at": None if job.lease_expires_at is None else job.lease_expires_at.isoformat(),
                        "not_before": None if job.not_before is None else job.not_before.isoformat(),
                    }
                )
        else:
            raise SystemExit(f"unknown op {name}")

    print(json.dumps({"weir_file": weir.__file__, "results": results}, default=str))


if __name__ == "__main__":
    main()
