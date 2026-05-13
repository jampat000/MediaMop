from __future__ import annotations

import os

from sqlalchemy import delete, update

from mediamop.core.config import MediaMopSettings
from mediamop.core.db import create_db_engine, create_session_factory
from mediamop.modules.pruner.pruner_preview_run_model import PrunerPreviewRun
from mediamop.modules.pruner.pruner_scope_settings_model import PrunerScopeSettings
from mediamop.modules.pruner.pruner_server_instance_model import PrunerServerInstance
from mediamop.modules.refiner.refiner_path_settings_model import RefinerPathSettingsRow
from mediamop.modules.subber.subber_providers_model import SubberProviderRow
from mediamop.modules.subber.subber_settings_model import SubberSettingsRow
from mediamop.platform.auth.models import User, UserSession
from mediamop.platform.suite_settings.model import SuiteSettingsRow


def clear_auth_tables_for_home(home: str) -> None:
    """Reset all per-test state so each test starts from a clean baseline.

    Auth tables (User, UserSession, SuiteSettingsRow) are cleared so the next
    test begins at the setup / login page.

    Module configuration is also reset so that wizard skip, Refiner, Subber,
    and Pruner forms don't inherit stale paths or credentials from a previous
    test.  Singleton rows (RefinerPathSettingsRow, SubberSettingsRow) are
    *reset* rather than deleted because the backend raises RuntimeError when
    the migration-seeded row with id=1 is missing.  Per-instance rows
    (PrunerServerInstance, SubberProviderRow, and their children) are deleted
    outright because they are not singletons.
    """
    os.environ["MEDIAMOP_HOME"] = home
    settings = MediaMopSettings.load()
    engine = create_db_engine(settings)
    factory = create_session_factory(engine)
    with factory() as db:
        # --- Non-singleton rows: safe to delete ---
        db.execute(delete(PrunerScopeSettings))
        db.execute(delete(PrunerPreviewRun))
        db.execute(delete(PrunerServerInstance))
        db.execute(delete(SubberProviderRow))

        # --- Singleton rows: reset variable fields back to blank/null ---
        # RefinerPathSettingsRow (id=1) is seeded by Alembic; deleting it
        # causes RuntimeError in ensure_refiner_path_settings_row.
        # Clear only the path fields that tests may have set.
        db.execute(
            update(RefinerPathSettingsRow)
            .where(RefinerPathSettingsRow.id == 1)
            .values(
                refiner_watched_folder=None,
                refiner_work_folder=None,
                refiner_output_folder="",
                refiner_tv_watched_folder=None,
                refiner_tv_work_folder=None,
                refiner_tv_output_folder=None,
            )
        )

        # SubberSettingsRow (id=1) is also a migration-seeded singleton.
        # Reset URL / credential fields; schedule and preference columns can
        # keep their defaults since tests don't depend on them being blank.
        db.execute(
            update(SubberSettingsRow)
            .where(SubberSettingsRow.id == 1)
            .values(
                sonarr_base_url="",
                sonarr_credentials_ciphertext="",
                radarr_base_url="",
                radarr_credentials_ciphertext="",
                opensubtitles_username="",
                opensubtitles_credentials_ciphertext="",
            )
        )

        # --- Auth tables ---
        db.execute(delete(UserSession))
        db.execute(delete(User))
        db.execute(delete(SuiteSettingsRow))
        db.commit()
    engine.dispose()
