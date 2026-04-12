"""Fetcher lane: Arr missing/upgrade search jobs, cooldown isolation, and worker semantics."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from mediamop.core.config import MediaMopSettings
from mediamop.modules.fetcher.fetcher_arr_search_enqueue import (
    enqueue_scheduled_radarr_missing_search_job,
    enqueue_scheduled_sonarr_missing_search_job,
)
from mediamop.modules.fetcher.fetcher_arr_search_handlers import (
    build_fetcher_arr_search_job_handlers,
    merge_fetcher_failed_import_and_search_handlers,
)
from mediamop.modules.fetcher.fetcher_arr_search_selection import (
    filter_item_ids_by_cooldown,
    iter_radarr_monitored_missing_movies,
    iter_sonarr_monitored_missing_episodes,
    paginate_wanted_cutoff,
)
from mediamop.modules.fetcher.fetcher_jobs_model import FetcherJob, FetcherJobStatus
from mediamop.modules.fetcher.fetcher_jobs_ops import fetcher_enqueue_or_requeue_schedule_job
from mediamop.modules.fetcher.fetcher_search_job_kinds import (
    DEDUPE_SCHEDULED_SONARR_MISSING,
    JOB_KIND_MISSING_SEARCH_RADARR_MONITORED_MOVIES_V1,
    JOB_KIND_MISSING_SEARCH_SONARR_MONITORED_EPISODES_V1,
    JOB_KIND_UPGRADE_SEARCH_RADARR_CUTOFF_UNMET_V1,
    JOB_KIND_UPGRADE_SEARCH_SONARR_CUTOFF_UNMET_V1,
)
from mediamop.modules.fetcher.fetcher_worker_loop import FetcherJobWorkContext, process_one_fetcher_job
from mediamop.modules.fetcher.failed_import_queue_job_handlers import build_failed_import_queue_job_handlers
from mediamop.modules.fetcher.fetcher_arr_action_log_model import FetcherArrActionLog
from mediamop.modules.refiner.jobs_ops import refiner_enqueue_or_get_job
from mediamop.platform.activity import constants as act_c
from mediamop.platform.activity.models import ActivityEvent

import mediamop.modules.fetcher.fetcher_jobs_model  # noqa: F401
import mediamop.modules.fetcher.fetcher_search_schedule_state_model  # noqa: F401
import mediamop.modules.refiner.jobs_model  # noqa: F401
import mediamop.platform.activity.models  # noqa: F401
import mediamop.platform.auth.models  # noqa: F401
from mediamop.core.db import Base


@pytest.fixture
def lane_engine(tmp_path):
    url = f"sqlite:///{tmp_path / 'arr_search_lane.sqlite'}"
    engine = create_engine(url, connect_args={"check_same_thread": False, "timeout": 30.0}, future=True)
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def lane_sf(lane_engine):
    return sessionmaker(bind=lane_engine, class_=Session, autoflush=False, autocommit=False, expire_on_commit=False, future=True)


def test_scheduled_search_enqueue_only_fetcher_jobs(lane_sf) -> None:
    with lane_sf() as s:
        enqueue_scheduled_sonarr_missing_search_job(s)
        enqueue_scheduled_radarr_missing_search_job(s)
        s.commit()
        rows = s.scalars(select(FetcherJob)).all()
    assert len(rows) == 2
    kinds = {r.job_kind for r in rows}
    assert kinds == {
        JOB_KIND_MISSING_SEARCH_SONARR_MONITORED_EPISODES_V1,
        JOB_KIND_MISSING_SEARCH_RADARR_MONITORED_MOVIES_V1,
    }
    assert all(r.dedupe_key.startswith("fetcher.search.scheduled:") for r in rows)


def test_refiner_enqueue_rejects_search_job_kinds(lane_sf) -> None:
    with lane_sf() as s:
        with pytest.raises(ValueError, match="refiner_enqueue_or_get_job refuses"):
            refiner_enqueue_or_get_job(
                s,
                dedupe_key="x",
                job_kind=JOB_KIND_MISSING_SEARCH_SONARR_MONITORED_EPISODES_V1,
            )


def test_merge_handlers_union_size(lane_sf, failed_import_queue_worker_runtime_bundle) -> None:
    settings = MediaMopSettings.load()
    fi = build_failed_import_queue_job_handlers(
        settings,
        lane_sf,
        failed_import_runtime=failed_import_queue_worker_runtime_bundle,
    )
    merged = merge_fetcher_failed_import_and_search_handlers(fi, settings, lane_sf)
    assert len(merged) == len(fi) + 4
    assert set(merged) == set(fi) | {
        JOB_KIND_MISSING_SEARCH_SONARR_MONITORED_EPISODES_V1,
        JOB_KIND_MISSING_SEARCH_RADARR_MONITORED_MOVIES_V1,
        JOB_KIND_UPGRADE_SEARCH_SONARR_CUTOFF_UNMET_V1,
        JOB_KIND_UPGRADE_SEARCH_RADARR_CUTOFF_UNMET_V1,
    }


def test_cooldown_missing_does_not_block_upgrade_same_item(lane_sf) -> None:
    now = datetime.now(timezone.utc)
    with lane_sf() as s:
        with s.begin():
            s.add(
                FetcherArrActionLog(
                    created_at=now,
                    app="sonarr",
                    action="missing",
                    item_type="episode",
                    item_id=42,
                ),
            )
        with s.begin():
            up = filter_item_ids_by_cooldown(
                s,
                app="sonarr",
                action="upgrade",
                item_type="episode",
                ids=[42],
                cooldown_minutes=60,
                now=now,
                max_apply=10,
            )
            assert up == [42]


def test_filter_item_ids_by_cooldown_writes_rows_only_for_allowed(lane_sf) -> None:
    now = datetime.now(timezone.utc)
    with lane_sf() as s:
        with s.begin():
            allowed = filter_item_ids_by_cooldown(
                s,
                app="radarr",
                action="missing",
                item_type="movie",
                ids=[1, 2, 3],
                cooldown_minutes=60,
                now=now,
                max_apply=2,
            )
            assert allowed == [1, 2]
        rows = s.scalars(select(FetcherArrActionLog)).all()
        assert {r.item_id for r in rows} == {1, 2}


def test_iter_sonarr_monitored_missing_includes_monitored_unaired_episodes() -> None:
    @dataclass
    class _Fake:
        posts: list[tuple[str, dict[str, Any]]] = field(default_factory=list)

        def get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
            if path == "/api/v3/series":
                return [{"id": 1, "monitored": True}, {"id": 2, "monitored": False}]
            if path == "/api/v3/episode":
                sid = (params or {}).get("seriesId")
                if sid == 1:
                    return [
                        {"id": 10, "monitored": True, "hasFile": False, "seriesId": 1},
                        {"id": 11, "monitored": False, "hasFile": False, "seriesId": 1},
                        {"id": 12, "monitored": True, "hasFile": True, "seriesId": 1},
                    ]
                return []
            return None

    out = list(iter_sonarr_monitored_missing_episodes(_Fake()))  # type: ignore[arg-type]
    assert [e["id"] for e in out] == [10]


def test_iter_radarr_monitored_missing_filters_monitored_and_has_file() -> None:
    @dataclass
    class _Fake:
        def get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
            if path == "/api/v3/movie":
                return [
                    {"id": 1, "monitored": True, "hasFile": False},
                    {"id": 2, "monitored": True, "hasFile": True},
                    {"id": 3, "monitored": False, "hasFile": False},
                ]
            return []

    out = list(iter_radarr_monitored_missing_movies(_Fake()))  # type: ignore[arg-type]
    assert [m["id"] for m in out] == [1]


def test_paginate_wanted_cutoff_uses_api_and_respects_action_scoped_cooldown(lane_sf) -> None:
    @dataclass
    class _Fake:
        page_calls: list[int] = field(default_factory=list)

        def get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
            assert path == "/api/v3/wanted/cutoff"
            self.page_calls.append(int(params.get("page", 0)))
            page = int(params.get("page", 1))
            if page == 1:
                return {
                    "totalRecords": 2,
                    "records": [
                        {"id": 100, "episodeId": 100, "seriesId": 7},
                        {"id": 101, "episodeId": 101, "seriesId": 7},
                    ],
                }
            return {"totalRecords": 2, "records": []}

    now = datetime.now(timezone.utc)
    fake = _Fake()
    with lane_sf() as s:
        with s.begin():
            ids, recs, total = paginate_wanted_cutoff(
                fake,  # type: ignore[arg-type]
                s,
                app="sonarr",
                action="upgrade",
                item_type="episode",
                id_keys=("id", "episodeId"),
                limit=2,
                cooldown_minutes=60,
                now=now,
            )
    assert total == 2
    assert ids == [100, 101]
    assert len(recs) == 2
    assert fake.page_calls and fake.page_calls[0] == 1


def test_enqueue_scheduled_allowed_when_worker_would_skip_outside_window(lane_sf, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "mediamop.modules.fetcher.fetcher_arr_search_handlers.fetcher_arr_search_schedule_in_window",
        lambda **_: False,
    )
    base = MediaMopSettings.load()
    settings = replace(
        base,
        fetcher_sonarr_base_url="http://sonarr.test",
        fetcher_sonarr_api_key="k",
        fetcher_sonarr_missing_search_enabled=True,
        fetcher_sonarr_missing_search_schedule_enabled=True,
    )
    with lane_sf() as s:
        fetcher_enqueue_or_requeue_schedule_job(
            s,
            dedupe_key=DEDUPE_SCHEDULED_SONARR_MISSING,
            job_kind=JOB_KIND_MISSING_SEARCH_SONARR_MONITORED_EPISODES_V1,
            payload_json='{"manual": false}',
        )
        s.commit()
        job_id = s.scalar(select(FetcherJob.id).where(FetcherJob.dedupe_key == DEDUPE_SCHEDULED_SONARR_MISSING))
        assert job_id is not None

    handlers = build_fetcher_arr_search_job_handlers(settings, lane_sf)
    ctx = FetcherJobWorkContext(
        id=int(job_id),
        job_kind=JOB_KIND_MISSING_SEARCH_SONARR_MONITORED_EPISODES_V1,
        payload_json='{"manual": false}',
        lease_owner="t",
    )
    handlers[ctx.job_kind](ctx)

    with lane_sf() as s:
        row = s.get(FetcherJob, int(job_id))
        assert row is not None
        assert row.status == FetcherJobStatus.PENDING.value
        n_act = s.scalar(
            select(func.count())
            .select_from(ActivityEvent)
            .where(ActivityEvent.event_type == act_c.FETCHER_ARR_SEARCH_MISSING_DISPATCHED),
        )
        assert int(n_act or 0) == 0


def test_scheduled_missing_zero_pool_no_activity_row(lane_sf, monkeypatch: pytest.MonkeyPatch) -> None:
    class _FakeClient:
        def __init__(self, *_a: Any, **_k: Any) -> None:
            pass

        def health_ok(self) -> None:
            return None

        def get_json(self, _path: str, _params: dict[str, Any] | None = None) -> Any:
            return []

        def post_json(self, *_a: Any, **_k: Any) -> Any:
            raise AssertionError("no command when pool empty")

        def put_json(self, *_a: Any, **_k: Any) -> Any:
            raise AssertionError("no tag when pool empty")

    monkeypatch.setattr(
        "mediamop.modules.fetcher.fetcher_arr_search_handlers.FetcherArrV3Client",
        _FakeClient,
    )
    base = MediaMopSettings.load()
    settings = replace(
        base,
        fetcher_sonarr_base_url="http://sonarr.test",
        fetcher_sonarr_api_key="k",
        fetcher_sonarr_missing_search_enabled=True,
        fetcher_sonarr_missing_search_schedule_enabled=False,
    )
    with lane_sf() as s:
        fetcher_enqueue_or_requeue_schedule_job(
            s,
            dedupe_key=DEDUPE_SCHEDULED_SONARR_MISSING,
            job_kind=JOB_KIND_MISSING_SEARCH_SONARR_MONITORED_EPISODES_V1,
            payload_json='{"manual": false}',
        )
        s.commit()
        jid = int(s.scalar(select(FetcherJob.id)) or 0)

    handlers = build_fetcher_arr_search_job_handlers(settings, lane_sf)
    with lane_sf() as s0:
        before_max = s0.scalar(select(func.max(ActivityEvent.id)))
    handlers[
        JOB_KIND_MISSING_SEARCH_SONARR_MONITORED_EPISODES_V1
    ](
        FetcherJobWorkContext(
            id=jid,
            job_kind=JOB_KIND_MISSING_SEARCH_SONARR_MONITORED_EPISODES_V1,
            payload_json='{"manual": false}',
            lease_owner="w",
        ),
    )
    with lane_sf() as s:
        after = s.scalars(select(ActivityEvent).where(ActivityEvent.id > (before_max or 0))).all()
    assert not any(e.event_type.startswith("fetcher.arr_search") for e in after)


def test_manual_missing_zero_emits_zero_manual_activity(lane_sf, monkeypatch: pytest.MonkeyPatch) -> None:
    class _FakeClient:
        def __init__(self, *_a: Any, **_k: Any) -> None:
            pass

        def health_ok(self) -> None:
            return None

        def get_json(self, _path: str, _params: dict[str, Any] | None = None) -> Any:
            return []

    monkeypatch.setattr(
        "mediamop.modules.fetcher.fetcher_arr_search_handlers.FetcherArrV3Client",
        _FakeClient,
    )
    base = MediaMopSettings.load()
    settings = replace(
        base,
        fetcher_sonarr_base_url="http://sonarr.test",
        fetcher_sonarr_api_key="k",
        fetcher_sonarr_missing_search_enabled=True,
        fetcher_sonarr_missing_search_schedule_enabled=False,
    )
    with lane_sf() as s:
        s.add(
            FetcherJob(
                dedupe_key="manual-test",
                job_kind=JOB_KIND_MISSING_SEARCH_SONARR_MONITORED_EPISODES_V1,
                status=FetcherJobStatus.PENDING.value,
                payload_json='{"manual": true}',
            ),
        )
        s.commit()
        jid = int(s.scalar(select(FetcherJob.id)) or 0)

    handlers = build_fetcher_arr_search_job_handlers(settings, lane_sf)
    handlers[JOB_KIND_MISSING_SEARCH_SONARR_MONITORED_EPISODES_V1](
        FetcherJobWorkContext(
            id=jid,
            job_kind=JOB_KIND_MISSING_SEARCH_SONARR_MONITORED_EPISODES_V1,
            payload_json='{"manual": true}',
            lease_owner="w",
        ),
    )
    with lane_sf() as s:
        row = s.scalars(
            select(ActivityEvent).where(ActivityEvent.event_type == act_c.FETCHER_ARR_SEARCH_MISSING_ZERO_MANUAL),
        ).first()
        assert row is not None


def test_sonarr_missing_handler_dispatches_episode_search_command(lane_sf, monkeypatch: pytest.MonkeyPatch) -> None:
    commands: list[dict[str, Any]] = []

    class _FakeClient:
        def __init__(self, *_a: Any, **_k: Any) -> None:
            pass

        def health_ok(self) -> None:
            return None

        def get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
            if path == "/api/v3/series":
                return [{"id": 1, "monitored": True}]
            if path == "/api/v3/episode":
                assert params and params.get("seriesId") == 1
                return [
                    {
                        "id": 55,
                        "monitored": True,
                        "hasFile": False,
                        "seriesId": 1,
                        "seriesTitle": "Show",
                        "seasonNumber": 1,
                        "episodeNumber": 2,
                        "title": "Two",
                    },
                ]
            if path == "/api/v3/tag":
                return [{"id": 9, "label": "fetcher-missing"}]
            return []

        def post_json(self, path: str, body: dict[str, Any]) -> Any:
            if path == "/api/v3/command":
                commands.append(body)
            return {}

        def put_json(self, *_a: Any, **_k: Any) -> Any:
            return {}

    monkeypatch.setattr(
        "mediamop.modules.fetcher.fetcher_arr_search_handlers.FetcherArrV3Client",
        _FakeClient,
    )
    base = MediaMopSettings.load()
    settings = replace(
        base,
        fetcher_sonarr_base_url="http://sonarr.test",
        fetcher_sonarr_api_key="k",
        fetcher_sonarr_missing_search_enabled=True,
        fetcher_sonarr_missing_search_schedule_enabled=False,
        fetcher_sonarr_missing_search_retry_delay_minutes=1,
    )
    with lane_sf() as s:
        s.add(
            FetcherJob(
                dedupe_key="cmd-test",
                job_kind=JOB_KIND_MISSING_SEARCH_SONARR_MONITORED_EPISODES_V1,
                status=FetcherJobStatus.PENDING.value,
                payload_json='{"manual": true}',
            ),
        )
        s.commit()
        jid = int(s.scalar(select(FetcherJob.id)) or 0)

    handlers = build_fetcher_arr_search_job_handlers(settings, lane_sf)
    handlers[JOB_KIND_MISSING_SEARCH_SONARR_MONITORED_EPISODES_V1](
        FetcherJobWorkContext(
            id=jid,
            job_kind=JOB_KIND_MISSING_SEARCH_SONARR_MONITORED_EPISODES_V1,
            payload_json='{"manual": true}',
            lease_owner="w",
        ),
    )
    assert commands == [{"name": "EpisodeSearch", "episodeIds": [55]}]


def test_process_one_fetcher_runs_search_handler(
    lane_sf,
    failed_import_queue_worker_runtime_bundle,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeClient:
        def __init__(self, *_a: Any, **_k: Any) -> None:
            pass

        def health_ok(self) -> None:
            return None

        def get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
            if path == "/api/v3/movie":
                return [{"id": 200, "monitored": True, "hasFile": False, "title": "M", "year": 1999}]
            if path == "/api/v3/tag":
                return [{"id": 3, "label": "fetcher-missing"}]
            return []

        def post_json(self, path: str, body: dict[str, Any]) -> Any:
            assert path == "/api/v3/command"
            assert body == {"name": "MoviesSearch", "movieIds": [200]}
            return {}

        def put_json(self, *_a: Any, **_k: Any) -> Any:
            return {}

    monkeypatch.setattr(
        "mediamop.modules.fetcher.fetcher_arr_search_handlers.FetcherArrV3Client",
        _FakeClient,
    )
    base = MediaMopSettings.load()
    settings = replace(
        base,
        fetcher_radarr_base_url="http://radarr.test",
        fetcher_radarr_api_key="rk",
        fetcher_radarr_missing_search_enabled=True,
        fetcher_radarr_missing_search_schedule_enabled=False,
        fetcher_radarr_missing_search_retry_delay_minutes=1,
    )
    with lane_sf() as s:
        s.add(
            FetcherJob(
                dedupe_key="rad-m",
                job_kind=JOB_KIND_MISSING_SEARCH_RADARR_MONITORED_MOVIES_V1,
                status=FetcherJobStatus.PENDING.value,
                payload_json='{"manual": true}',
            ),
        )
        s.commit()

    merged = merge_fetcher_failed_import_and_search_handlers(
        build_failed_import_queue_job_handlers(
            settings,
            lane_sf,
            failed_import_runtime=failed_import_queue_worker_runtime_bundle,
        ),
        settings,
        lane_sf,
    )
    out = process_one_fetcher_job(lane_sf, lease_owner="w1", job_handlers=merged)
    assert out == "processed"
    with lane_sf() as s:
        row = s.scalars(select(FetcherJob)).first()
        assert row is not None
        assert row.status == FetcherJobStatus.COMPLETED.value


def test_upgrade_handler_uses_wanted_cutoff_pagination(lane_sf, monkeypatch: pytest.MonkeyPatch) -> None:
    bodies: list[dict[str, Any]] = []

    class _FakeClient:
        def __init__(self, *_a: Any, **_k: Any) -> None:
            pass

        def health_ok(self) -> None:
            return None

        def get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
            assert path == "/api/v3/wanted/cutoff"
            return {
                "totalRecords": 1,
                "records": [{"id": 501, "movieId": 501, "title": "Film", "year": 2001}],
            }

        def post_json(self, path: str, body: dict[str, Any]) -> Any:
            if path == "/api/v3/command":
                bodies.append(body)
            return {}

        def put_json(self, *_a: Any, **_k: Any) -> Any:
            return {}

    monkeypatch.setattr(
        "mediamop.modules.fetcher.fetcher_arr_search_handlers.FetcherArrV3Client",
        _FakeClient,
    )
    base = MediaMopSettings.load()
    settings = replace(
        base,
        fetcher_radarr_base_url="http://radarr.test",
        fetcher_radarr_api_key="rk",
        fetcher_radarr_upgrade_search_enabled=True,
        fetcher_radarr_upgrade_search_schedule_enabled=False,
        fetcher_radarr_upgrade_search_retry_delay_minutes=1,
    )
    with lane_sf() as s:
        s.add(
            FetcherJob(
                dedupe_key="rad-u",
                job_kind=JOB_KIND_UPGRADE_SEARCH_RADARR_CUTOFF_UNMET_V1,
                status=FetcherJobStatus.PENDING.value,
                payload_json='{"manual": true}',
            ),
        )
        s.commit()
        jid = int(s.scalar(select(FetcherJob.id)) or 0)

    h = build_fetcher_arr_search_job_handlers(settings, lane_sf)
    h[JOB_KIND_UPGRADE_SEARCH_RADARR_CUTOFF_UNMET_V1](
        FetcherJobWorkContext(
            id=jid,
            job_kind=JOB_KIND_UPGRADE_SEARCH_RADARR_CUTOFF_UNMET_V1,
            payload_json='{"manual": true}',
            lease_owner="w",
        ),
    )
    assert bodies == [{"name": "MoviesSearch", "movieIds": [501]}]


def test_prune_fetcher_arr_action_log_uses_per_lane_retry_windows(lane_sf) -> None:
    """Short-retry lane drops old rows; long-retry lane keeps rows of the same age (no shared prune window)."""

    from mediamop.modules.fetcher.fetcher_arr_search_selection import prune_fetcher_arr_action_log

    now = datetime(2030, 6, 15, 12, 0, tzinfo=timezone.utc)
    old = now - timedelta(minutes=30)
    base = MediaMopSettings.load()
    settings = replace(
        base,
        fetcher_sonarr_missing_search_retry_delay_minutes=10,
        fetcher_sonarr_upgrade_search_retry_delay_minutes=1440,
        fetcher_radarr_missing_search_retry_delay_minutes=1440,
        fetcher_radarr_upgrade_search_retry_delay_minutes=1440,
    )
    with lane_sf() as s:
        with s.begin():
            s.add_all(
                [
                    FetcherArrActionLog(
                        created_at=old,
                        app="sonarr",
                        action="missing",
                        item_type="episode",
                        item_id=1,
                    ),
                    FetcherArrActionLog(
                        created_at=old,
                        app="sonarr",
                        action="upgrade",
                        item_type="episode",
                        item_id=2,
                    ),
                ],
            )
        with s.begin():
            prune_fetcher_arr_action_log(s, settings=settings, now=now)
        miss = s.scalars(
            select(FetcherArrActionLog).where(
                FetcherArrActionLog.app == "sonarr",
                FetcherArrActionLog.action == "missing",
            ),
        ).all()
        up = s.scalars(
            select(FetcherArrActionLog).where(
                FetcherArrActionLog.app == "sonarr",
                FetcherArrActionLog.action == "upgrade",
            ),
        ).all()
    assert miss == []
    assert len(up) == 1
