from __future__ import annotations

import os

from sqlalchemy import delete, update

from weir.core.config import WeirSettings
from weir.core.db import create_db_engine, create_session_factory
from weir.refiner.refiner_library_model import RefinerLibraryRow
from weir.platform.auth.models import User, UserSession
from weir.platform.suite_settings.model import SuiteSettingsRow


def clear_auth_tables_for_home(home: str) -> None:
    """Reset all per-test state so each test starts from a clean baseline.

    Auth tables (User, UserSession, SuiteSettingsRow) are cleared so the next
    test begins at the setup / login page.

    Module configuration is also reset so that wizard skip and Refiner forms
    don't inherit stale paths from a previous test.  The migration-seeded
    Refiner libraries have their folders *cleared* rather than being deleted,
    because they are the only path store now (#363) and a scope with no library
    at all has nowhere to resolve to.
    """
    os.environ["WEIR_HOME"] = home
    settings = WeirSettings.load()
    engine = create_db_engine(settings)
    factory = create_session_factory(engine)
    with factory() as db:
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
