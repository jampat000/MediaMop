from __future__ import annotations

import os

from sqlalchemy import delete, update

from mediamop.core.config import MediaMopSettings
from mediamop.core.db import create_db_engine, create_session_factory
from mediamop.modules.pruner.pruner_preview_run_model import PrunerPreviewRun
from mediamop.modules.pruner.pruner_scope_settings_model import PrunerScopeSettings
from mediamop.modules.pruner.pruner_server_instance_model import PrunerServerInstance
from mediamop.modules.refiner.refiner_library_model import RefinerLibraryRow
from mediamop.platform.auth.models import User, UserSession
from mediamop.platform.suite_settings.model import SuiteSettingsRow


def clear_auth_tables_for_home(home: str) -> None:
    """Reset all per-test state so each test starts from a clean baseline.

    Auth tables (User, UserSession, SuiteSettingsRow) are cleared so the next
    test begins at the setup / login page.

    Module configuration is also reset so that wizard skip, Refiner, and
    Pruner forms don't inherit stale paths or credentials from a previous
    test.  The migration-seeded Refiner libraries have their folders *cleared*
    rather than being deleted, because they are the only path store now (#363)
    and a scope with no library at all has nowhere to resolve to.  Per-instance
    rows (PrunerServerInstance and their children) are deleted outright.
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

        # --- Seeded libraries: clear the folders a test may have set ---
        # The libraries are seeded by Alembic and are the only path store now (#363), so
        # deleting them would leave nothing for a scope to resolve to. Their folders are
        # cleared instead, which is the state a fresh install has.
        db.execute(update(RefinerLibraryRow).values(watched_folder="", work_folder="", output_folder=""))

        # --- Auth tables ---
        db.execute(delete(UserSession))
        db.execute(delete(User))
        db.execute(delete(SuiteSettingsRow))
        db.commit()
    engine.dispose()
