"""Refiner file activity handler keeps one live row per processed file."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from mediamop.core.config import MediaMopSettings
from mediamop.core.db import create_db_engine, create_session_factory
from mediamop.modules.refiner import refiner_file_remux_pass_handlers as handler_mod
from mediamop.modules.refiner.refiner_file_remux_pass_visibility import REMUX_PASS_OUTCOME_LIVE_OUTPUT_WRITTEN
from mediamop.modules.refiner.worker_loop import RefinerJobWorkContext
from mediamop.platform.activity import constants as activity_constants
from mediamop.platform.activity.live_stream import activity_latest_notifier
from mediamop.platform.activity.models import ActivityEvent


def test_refiner_remux_handler_updates_progress_row_to_completed_activity(
    monkeypatch,
) -> None:
    settings = MediaMopSettings.load()
    eng = create_db_engine(settings)
    fac = create_session_factory(eng)
    activity_latest_notifier.reset_for_tests()
    with fac() as db:
        assert isinstance(db, Session)
        db.execute(delete(ActivityEvent))
        db.commit()

    monkeypatch.setattr(
        handler_mod,
        "ensure_refiner_operator_settings_row",
        lambda _session: SimpleNamespace(min_file_age_seconds=0),
    )
    monkeypatch.setattr(handler_mod, "load_refiner_remux_rules_config", lambda _session, *, media_scope: object())
    monkeypatch.setattr(handler_mod, "resolve_refiner_path_runtime_for_remux", lambda *_args, **_kwargs: (object(), None))

    def _fake_run_refiner_file_remux_pass(**kwargs: Any) -> dict[str, Any]:
        progress_reporter = kwargs["progress_reporter"]
        progress_reporter(
            {
                "status": "processing",
                "relative_media_path": "Movie/file.mkv",
                "percent": 10.0,
                "message": "Refiner is writing the cleaned-up file.",
            }
        )
        progress_reporter(
            {
                "status": "processing",
                "relative_media_path": "Movie/file.mkv",
                "percent": 55.0,
                "message": "Refiner is writing the cleaned-up file.",
            }
        )
        return {
            "ok": True,
            "outcome": REMUX_PASS_OUTCOME_LIVE_OUTPUT_WRITTEN,
            "relative_media_path": "Movie/file.mkv",
            "source_size_bytes": 2000,
            "output_size_bytes": 1000,
        }

    monkeypatch.setattr(handler_mod, "run_refiner_file_remux_pass", _fake_run_refiner_file_remux_pass)

    handler = handler_mod.make_refiner_file_remux_pass_handler(settings, fac)
    handler(
        RefinerJobWorkContext(
            id=123,
            job_kind="refiner.file.remux_pass.v1",
            payload_json=json.dumps({"relative_media_path": "Movie/file.mkv", "media_scope": "movie"}),
            lease_owner="test",
        )
    )

    with fac() as db:
        rows = list(db.scalars(select(ActivityEvent).order_by(ActivityEvent.id)).all())

    assert len(rows) == 1
    row = rows[0]
    assert row.event_type == activity_constants.REFINER_FILE_REMUX_PASS_COMPLETED
    assert row.module == "refiner"
    assert row.title == "file.mkv was processed successfully"
    assert row.detail is not None
    detail = json.loads(row.detail)
    assert detail["outcome"] == REMUX_PASS_OUTCOME_LIVE_OUTPUT_WRITTEN
    assert detail["job_id"] == 123
    assert detail["source_size_bytes"] == 2000
    assert detail["output_size_bytes"] == 1000

    latest_id, revision = activity_latest_notifier.snapshot()
    assert latest_id == row.id
    assert revision == 3

    with fac() as db:
        assert isinstance(db, Session)
        db.execute(delete(ActivityEvent))
        db.commit()
