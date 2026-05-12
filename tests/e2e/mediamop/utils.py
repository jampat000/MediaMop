from __future__ import annotations

import os

from sqlalchemy import delete

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
    """Reset all per-test state: auth tables AND module configuration tables.

    Auth tables (User, UserSession, SuiteSettingsRow) are cleared so the next
    test starts at the setup / login page.  Module config tables are cleared so
    that wizard skip, Refiner, Subber, and Pruner forms don't inherit stale
    paths or credentials from a previous test (e.g. test_seeded_module_save_audit
    leaves refiner TV paths and Sonarr/Emby settings that confuse later tests).
    """
    os.environ["MEDIAMOP_HOME"] = home
    settings = MediaMopSettings.load()
    engine = create_db_engine(settings)
    factory = create_session_factory(engine)
    with factory() as db:
        # Delete child rows first to avoid FK constraint violations on strict DBs.
        db.execute(delete(PrunerScopeSettings))
        db.execute(delete(PrunerPreviewRun))
        db.execute(delete(PrunerServerInstance))
        db.execute(delete(SubberProviderRow))
        db.execute(delete(SubberSettingsRow))
        db.execute(delete(RefinerPathSettingsRow))
        db.execute(delete(UserSession))
        db.execute(delete(User))
        db.execute(delete(SuiteSettingsRow))
        db.commit()
    engine.dispose()
