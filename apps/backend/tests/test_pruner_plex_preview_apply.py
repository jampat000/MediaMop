"""Plex missing_primary_media_reported: preview persistence + snapshot-bound apply."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

import mediamop.modules.pruner.pruner_jobs_model  # noqa: F401
import mediamop.modules.pruner.pruner_preview_run_model  # noqa: F401
import mediamop.modules.pruner.pruner_scope_settings_model  # noqa: F401
import mediamop.modules.pruner.pruner_server_instance_model  # noqa: F401
import mediamop.platform.activity.models  # noqa: F401
import mediamop.platform.auth.models  # noqa: F401
from mediamop.core.config import MediaMopSettings
from mediamop.core.db import create_db_engine, create_session_factory
from mediamop.modules.pruner.pruner_apply_eligibility import compute_apply_eligibility
from mediamop.modules.pruner.pruner_constants import (
    MEDIA_SCOPE_MOVIES,
    MEDIA_SCOPE_TV,
    RULE_FAMILY_MISSING_PRIMARY_MEDIA_REPORTED,
)
from mediamop.modules.pruner.pruner_instances_service import create_server_instance, get_scope_settings
from mediamop.modules.pruner.pruner_job_handlers import build_pruner_job_handlers
from mediamop.modules.pruner.pruner_job_kinds import (
    PRUNER_CANDIDATE_REMOVAL_APPLY_JOB_KIND,
    PRUNER_CANDIDATE_REMOVAL_PREVIEW_JOB_KIND,
)
from mediamop.modules.pruner.pruner_jobs_model import PrunerJob, PrunerJobStatus
from mediamop.modules.pruner.pruner_preview_service import insert_preview_run
from mediamop.modules.pruner.worker_loop import PrunerJobWorkContext
from mediamop.platform.activity import constants as C
from mediamop.platform.activity.models import ActivityEvent
from tests.integration_app_runtime_quiesce import (
    integration_test_quiesce_in_process_workers,
    integration_test_quiesce_periodic_enqueue,
    integration_test_set_home,
)


@pytest.fixture(autouse=True)
def _iso(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    integration_test_set_home(tmp_path, monkeypatch, "mmhome_pruner_plex_preview_apply")
    integration_test_quiesce_in_process_workers(monkeypatch)
    integration_test_quiesce_periodic_enqueue(monkeypatch)
    backend = Path(__file__).resolve().parents[1]
    command.upgrade(Config(str(backend / "alembic.ini")), "head")


@pytest.fixture
def session_factory(_iso) -> sessionmaker[Session]:
    settings = MediaMopSettings.load()
    return create_session_factory(create_db_engine(settings))


def _plex_instance(session_factory: sessionmaker[Session], *, label: str = "Plex") -> int:
    settings = MediaMopSettings.load()
    with session_factory() as s:
        with s.begin():
            inst = create_server_instance(
                s,
                settings,
                provider="plex",
                display_name=label,
                base_url="http://plex.test:32400",
                credentials_secrets={"auth_token": "tok"},
            )
            return int(inst.id)


def test_plex_apply_does_not_call_candidate_collector(
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MEDIAMOP_PRUNER_APPLY_ENABLED", "1")
    settings = MediaMopSettings.load()
    sid = _plex_instance(session_factory)
    run_uuid = str(uuid.uuid4())
    calls: list[str] = []

    def _boom(**_kw: object) -> tuple[list[dict[str, object]], bool]:
        calls.append("list")
        raise AssertionError("apply must not rediscover Plex candidates")

    monkeypatch.setattr(
        "mediamop.modules.pruner.pruner_plex_missing_thumb_candidates.list_plex_missing_thumb_candidates",
        _boom,
    )
    monkeypatch.setattr(
        "mediamop.modules.pruner.pruner_media_library.list_plex_missing_thumb_candidates",
        _boom,
    )

    def _delete(**kw: object) -> tuple[int, str | None]:
        rk = str(kw.get("rating_key", ""))
        if rk == "1":
            return 200, None
        if rk == "2":
            return 404, None
        return 500, "x"

    monkeypatch.setattr(
        "mediamop.modules.pruner.pruner_apply_job_handler.plex_delete_library_metadata",
        _delete,
    )

    with session_factory() as s:
        with s.begin():
            insert_preview_run(
                s,
                preview_run_uuid=run_uuid,
                server_instance_id=sid,
                media_scope=MEDIA_SCOPE_TV,
                rule_family_id=RULE_FAMILY_MISSING_PRIMARY_MEDIA_REPORTED,
                pruner_job_id=None,
                candidate_count=2,
                candidates_json=json.dumps(
                    [
                        {"item_id": "1", "granularity": "episode"},
                        {"item_id": "2", "granularity": "episode"},
                    ],
                ),
                truncated=False,
                outcome="success",
                unsupported_detail=None,
                error_message=None,
            )
            job_row = PrunerJob(
                dedupe_key="plex-apply-test",
                job_kind=PRUNER_CANDIDATE_REMOVAL_APPLY_JOB_KIND,
                status=PrunerJobStatus.COMPLETED.value,
            )
            s.add(job_row)
            s.flush()
            job_id = int(job_row.id)

    handlers = build_pruner_job_handlers(settings, session_factory)
    handlers[PRUNER_CANDIDATE_REMOVAL_APPLY_JOB_KIND](
        PrunerJobWorkContext(
            id=job_id,
            job_kind=PRUNER_CANDIDATE_REMOVAL_APPLY_JOB_KIND,
            payload_json=json.dumps(
                {
                    "preview_run_uuid": run_uuid,
                    "server_instance_id": sid,
                    "media_scope": MEDIA_SCOPE_TV,
                    "rule_family_id": RULE_FAMILY_MISSING_PRIMARY_MEDIA_REPORTED,
                },
            ),
            lease_owner="pytest",
        ),
    )

    assert calls == []
    with session_factory() as s:
        evt = s.scalars(select(ActivityEvent).order_by(ActivityEvent.id.desc()).limit(1)).first()
        assert evt is not None
        assert evt.event_type == C.PRUNER_APPLY_LIBRARY_REMOVAL_COMPLETED
        detail = json.loads(evt.detail or "{}")
        assert detail.get("removed") == 1
        assert detail.get("skipped") == 1
        assert detail.get("failed") == 0


def test_plex_apply_preview_run_must_match_instance(
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MEDIAMOP_PRUNER_APPLY_ENABLED", "1")
    settings = MediaMopSettings.load()
    sid_a = _plex_instance(session_factory, label="A")
    sid_b = _plex_instance(session_factory, label="B")
    run_uuid = str(uuid.uuid4())
    with session_factory() as s:
        with s.begin():
            insert_preview_run(
                s,
                preview_run_uuid=run_uuid,
                server_instance_id=sid_b,
                media_scope=MEDIA_SCOPE_TV,
                rule_family_id=RULE_FAMILY_MISSING_PRIMARY_MEDIA_REPORTED,
                pruner_job_id=None,
                candidate_count=1,
                candidates_json=json.dumps([{"item_id": "9", "granularity": "episode"}]),
                truncated=False,
                outcome="success",
                unsupported_detail=None,
                error_message=None,
            )

    handlers = build_pruner_job_handlers(settings, session_factory)
    fn = handlers[PRUNER_CANDIDATE_REMOVAL_APPLY_JOB_KIND]
    with pytest.raises(ValueError, match="preview snapshot not found"):
        fn(
            PrunerJobWorkContext(
                id=1,
                job_kind=PRUNER_CANDIDATE_REMOVAL_APPLY_JOB_KIND,
                payload_json=json.dumps(
                    {
                        "preview_run_uuid": run_uuid,
                        "server_instance_id": sid_a,
                        "media_scope": MEDIA_SCOPE_TV,
                        "rule_family_id": RULE_FAMILY_MISSING_PRIMARY_MEDIA_REPORTED,
                    },
                ),
                lease_owner="pytest",
            ),
        )


def test_plex_apply_rejects_scope_mismatch_with_snapshot(
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MEDIAMOP_PRUNER_APPLY_ENABLED", "1")
    settings = MediaMopSettings.load()
    sid = _plex_instance(session_factory)
    run_uuid = str(uuid.uuid4())
    with session_factory() as s:
        with s.begin():
            insert_preview_run(
                s,
                preview_run_uuid=run_uuid,
                server_instance_id=sid,
                media_scope=MEDIA_SCOPE_MOVIES,
                rule_family_id=RULE_FAMILY_MISSING_PRIMARY_MEDIA_REPORTED,
                pruner_job_id=None,
                candidate_count=1,
                candidates_json=json.dumps([{"item_id": "m1", "granularity": "movie_item"}]),
                truncated=False,
                outcome="success",
                unsupported_detail=None,
                error_message=None,
            )

    handlers = build_pruner_job_handlers(settings, session_factory)
    fn = handlers[PRUNER_CANDIDATE_REMOVAL_APPLY_JOB_KIND]
    with pytest.raises(ValueError, match="media_scope"):
        fn(
            PrunerJobWorkContext(
                id=1,
                job_kind=PRUNER_CANDIDATE_REMOVAL_APPLY_JOB_KIND,
                payload_json=json.dumps(
                    {
                        "preview_run_uuid": run_uuid,
                        "server_instance_id": sid,
                        "media_scope": MEDIA_SCOPE_TV,
                        "rule_family_id": RULE_FAMILY_MISSING_PRIMARY_MEDIA_REPORTED,
                    },
                ),
                lease_owner="pytest",
            ),
        )


def test_compute_apply_eligibility_allows_plex_missing_primary_snapshot(
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MEDIAMOP_PRUNER_APPLY_ENABLED", "1")
    settings = MediaMopSettings.load()
    sid = _plex_instance(session_factory)
    run_uuid = str(uuid.uuid4())
    with session_factory() as s:
        with s.begin():
            insert_preview_run(
                s,
                preview_run_uuid=run_uuid,
                server_instance_id=sid,
                media_scope=MEDIA_SCOPE_TV,
                rule_family_id=RULE_FAMILY_MISSING_PRIMARY_MEDIA_REPORTED,
                pruner_job_id=None,
                candidate_count=1,
                candidates_json=json.dumps([{"item_id": "z", "granularity": "episode"}]),
                truncated=False,
                outcome="success",
                unsupported_detail=None,
                error_message=None,
            )
        out = compute_apply_eligibility(
            s,
            settings,
            instance_id=sid,
            media_scope=MEDIA_SCOPE_TV,
            preview_run_uuid=run_uuid,
        )
    assert out.eligible is True
    assert out.provider == "plex"


def test_candidates_json_cap_does_not_widen_apply_set(
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Snapshot stores extra JSON objects but apply respects candidate_count cap only."""

    monkeypatch.setenv("MEDIAMOP_PRUNER_APPLY_ENABLED", "1")
    settings = MediaMopSettings.load()
    sid = _plex_instance(session_factory)
    run_uuid = str(uuid.uuid4())
    wide = [{"item_id": str(i), "granularity": "episode"} for i in range(5)]
    with session_factory() as s:
        with s.begin():
            insert_preview_run(
                s,
                preview_run_uuid=run_uuid,
                server_instance_id=sid,
                media_scope=MEDIA_SCOPE_TV,
                rule_family_id=RULE_FAMILY_MISSING_PRIMARY_MEDIA_REPORTED,
                pruner_job_id=None,
                candidate_count=2,
                candidates_json=json.dumps(wide),
                truncated=False,
                outcome="success",
                unsupported_detail=None,
                error_message=None,
            )

    deleted: list[str] = []

    def _delete(**kw: object) -> tuple[int, str | None]:
        deleted.append(str(kw.get("rating_key", "")))
        return 200, None

    monkeypatch.setattr(
        "mediamop.modules.pruner.pruner_apply_job_handler.plex_delete_library_metadata",
        _delete,
    )

    handlers = build_pruner_job_handlers(settings, session_factory)
    handlers[PRUNER_CANDIDATE_REMOVAL_APPLY_JOB_KIND](
        PrunerJobWorkContext(
            id=1,
            job_kind=PRUNER_CANDIDATE_REMOVAL_APPLY_JOB_KIND,
            payload_json=json.dumps(
                {
                    "preview_run_uuid": run_uuid,
                    "server_instance_id": sid,
                    "media_scope": MEDIA_SCOPE_TV,
                    "rule_family_id": RULE_FAMILY_MISSING_PRIMARY_MEDIA_REPORTED,
                },
            ),
            lease_owner="pytest",
        ),
    )
    assert deleted == ["0", "1"]


def test_auto_apply_payload_enforces_max_deletes_per_run(
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MEDIAMOP_PRUNER_APPLY_ENABLED", "1")
    settings = MediaMopSettings.load()
    sid = _plex_instance(session_factory)
    run_uuid = str(uuid.uuid4())
    candidates = [{"item_id": str(i), "granularity": "episode"} for i in range(5)]
    with session_factory() as s:
        with s.begin():
            insert_preview_run(
                s,
                preview_run_uuid=run_uuid,
                server_instance_id=sid,
                media_scope=MEDIA_SCOPE_TV,
                rule_family_id=RULE_FAMILY_MISSING_PRIMARY_MEDIA_REPORTED,
                pruner_job_id=None,
                candidate_count=5,
                candidates_json=json.dumps(candidates),
                truncated=False,
                outcome="success",
                unsupported_detail=None,
                error_message=None,
            )

    deleted: list[str] = []

    def _delete(**kw: object) -> tuple[int, str | None]:
        deleted.append(str(kw.get("rating_key", "")))
        return 200, None

    monkeypatch.setattr(
        "mediamop.modules.pruner.pruner_apply_job_handler.plex_delete_library_metadata",
        _delete,
    )

    handlers = build_pruner_job_handlers(settings, session_factory)
    handlers[PRUNER_CANDIDATE_REMOVAL_APPLY_JOB_KIND](
        PrunerJobWorkContext(
            id=1,
            job_kind=PRUNER_CANDIDATE_REMOVAL_APPLY_JOB_KIND,
            payload_json=json.dumps(
                {
                    "preview_run_uuid": run_uuid,
                    "server_instance_id": sid,
                    "media_scope": MEDIA_SCOPE_TV,
                    "rule_family_id": RULE_FAMILY_MISSING_PRIMARY_MEDIA_REPORTED,
                    "auto_applied": True,
                    "max_deletes_per_run": 2,
                },
            ),
            lease_owner="pytest",
        ),
    )

    assert deleted == ["0", "1"]
    with session_factory() as s:
        evt = s.scalars(select(ActivityEvent).order_by(ActivityEvent.id.desc()).limit(1)).first()
        assert evt is not None
        detail = json.loads(evt.detail or "{}")
        assert detail["auto_applied"] is True
        assert detail["deleted_count"] == 2
        assert detail["max_deletes_per_run"] == 2


def test_plex_missing_primary_effective_max_items_matches_retired_live_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MEDIAMOP_PRUNER_PLEX_LIVE_ABS_MAX_ITEMS", "7")
    settings = MediaMopSettings.load()
    from mediamop.modules.pruner.pruner_plex_live_eligibility import plex_missing_primary_effective_max_items

    assert plex_missing_primary_effective_max_items(settings, 500) == 7
    assert plex_missing_primary_effective_max_items(settings, 3) == 3


def test_plex_preview_job_passes_effective_cap_to_collector(
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Preview must pass the same capped max_items the retired live job used (min scope, ABS max, 5k)."""

    monkeypatch.setenv("MEDIAMOP_PRUNER_PLEX_LIVE_ABS_MAX_ITEMS", "3")
    settings = MediaMopSettings.load()  # after env: picks up ABS max for handler + eligibility math
    captured: dict[str, int] = {}

    def _spy(*, max_items: int, **_kw: object) -> tuple[list[dict[str, object]], bool]:
        captured["max_items"] = int(max_items)
        return [], False

    monkeypatch.setattr(
        "mediamop.modules.pruner.pruner_media_library.list_plex_missing_thumb_candidates",
        _spy,
    )

    sid = _plex_instance(session_factory)
    with session_factory() as s:
        sc = get_scope_settings(s, server_instance_id=sid, media_scope=MEDIA_SCOPE_TV)
        assert sc is not None
        sc.preview_max_items = 500
        s.commit()

    with session_factory() as s:
        with s.begin():
            job_row = PrunerJob(
                dedupe_key="plex-cap-preview",
                job_kind=PRUNER_CANDIDATE_REMOVAL_PREVIEW_JOB_KIND,
                status=PrunerJobStatus.COMPLETED.value,
            )
            s.add(job_row)
            s.flush()
            job_id = int(job_row.id)

    handlers = build_pruner_job_handlers(settings, session_factory)
    handlers[PRUNER_CANDIDATE_REMOVAL_PREVIEW_JOB_KIND](
        PrunerJobWorkContext(
            id=job_id,
            job_kind=PRUNER_CANDIDATE_REMOVAL_PREVIEW_JOB_KIND,
            payload_json=json.dumps({"server_instance_id": sid, "media_scope": MEDIA_SCOPE_TV}),
            lease_owner="pytest",
        ),
    )
    assert captured.get("max_items") == 3
