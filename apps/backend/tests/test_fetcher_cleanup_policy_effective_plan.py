"""DB-backed Fetcher cleanup policy: seed once from env, then row only."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session, sessionmaker

from mediamop.core.db import Base
from mediamop.modules.fetcher.cleanup_policy_model import FetcherFailedImportCleanupPolicyRow
from mediamop.modules.fetcher.cleanup_policy_service import (
    FailedImportDrivePolicySource,
    load_fetcher_failed_import_cleanup_bundle,
    upsert_fetcher_failed_import_cleanup_policy,
)
from mediamop.modules.arr_failed_import.env_settings import (
    AppFailedImportCleanupPolicySettings,
    default_failed_import_cleanup_settings_bundle,
)
from mediamop.modules.fetcher.radarr_failed_import_cleanup import (
    RadarrFailedImportCleanupAction,
    plan_radarr_failed_import_cleanup,
)
from mediamop.modules.fetcher.sonarr_failed_import_cleanup import (
    SonarrFailedImportCleanupAction,
    plan_sonarr_failed_import_cleanup,
)

import mediamop.modules.refiner.jobs_model  # noqa: F401


@pytest.fixture
def policy_engine(tmp_path):
    from sqlalchemy import create_engine

    url = f"sqlite:///{tmp_path / 'policy_plan.sqlite'}"
    engine = create_engine(
        url,
        connect_args={"check_same_thread": False, "timeout": 30.0},
        future=True,
    )
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def session_factory(policy_engine):
    return sessionmaker(
        bind=policy_engine,
        class_=Session,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
        future=True,
    )


def test_load_seeds_singleton_from_env_then_second_read_is_db_only(session_factory) -> None:
    env = default_failed_import_cleanup_settings_bundle()
    with session_factory() as s:
        eff1, row1 = load_fetcher_failed_import_cleanup_bundle(s, env)
        s.commit()
    assert row1.id == 1
    assert eff1.radarr.remove_failed_imports is False

    with session_factory() as s:
        eff2, row2 = load_fetcher_failed_import_cleanup_bundle(s, env)
    assert row2.id == 1
    assert eff2.radarr.remove_failed_imports is False
    # Mutate DB directly — env fallback must not mask this on next load.
    with session_factory() as s:
        r = s.get(FetcherFailedImportCleanupPolicyRow, 1)
        assert r is not None
        r.radarr_remove_failed_imports = True
        s.commit()
    different_env = default_failed_import_cleanup_settings_bundle()
    with session_factory() as s:
        eff3, _ = load_fetcher_failed_import_cleanup_bundle(s, different_env)
    assert eff3.radarr.remove_failed_imports is True


def test_upsert_after_seed_updates_db(session_factory) -> None:
    env = default_failed_import_cleanup_settings_bundle()
    with session_factory() as s:
        load_fetcher_failed_import_cleanup_bundle(s, env)
        s.commit()
    with session_factory() as s:
        upsert_fetcher_failed_import_cleanup_policy(
            s,
            env_bundle=env,
            radarr=AppFailedImportCleanupPolicySettings(remove_failed_imports=True),
            sonarr=AppFailedImportCleanupPolicySettings(),
        )
        s.commit()
    with session_factory() as s:
        eff, _ = load_fetcher_failed_import_cleanup_bundle(s, env)
    assert eff.radarr.remove_failed_imports is True


def test_drive_policy_source_implements_both_axes(session_factory) -> None:
    env = default_failed_import_cleanup_settings_bundle()
    with session_factory() as s:
        upsert_fetcher_failed_import_cleanup_policy(
            s,
            env_bundle=env,
            radarr=AppFailedImportCleanupPolicySettings(),
            sonarr=AppFailedImportCleanupPolicySettings(remove_corrupt_imports=True),
        )
        s.commit()
    with session_factory() as s:
        eff, _ = load_fetcher_failed_import_cleanup_bundle(s, env)
    src = FailedImportDrivePolicySource(eff)
    r_plan = plan_radarr_failed_import_cleanup(
        status_message_blob="Import failed",
        policy=src.radarr_failed_import_cleanup_policy(),
        radarr_queue_item_id=1,
    )
    assert r_plan.action is RadarrFailedImportCleanupAction.NONE
    s_plan = plan_sonarr_failed_import_cleanup(
        status_message_blob="corrupt file",
        policy=src.sonarr_failed_import_cleanup_policy(),
        sonarr_queue_item_id=1,
    )
    assert s_plan.action is SonarrFailedImportCleanupAction.PLANNED_REMOVE_FROM_DOWNLOAD_QUEUE
