from __future__ import annotations

import os

from sqlalchemy import delete

from mediamop.core.config import MediaMopSettings
from mediamop.core.db import create_db_engine, create_session_factory
from mediamop.platform.auth.models import User, UserSession


def clear_auth_tables_for_home(home: str) -> None:
    os.environ["MEDIAMOP_HOME"] = home
    settings = MediaMopSettings.load()
    engine = create_db_engine(settings)
    factory = create_session_factory(engine)
    with factory() as db:
        db.execute(delete(UserSession))
        db.execute(delete(User))
        db.commit()
    engine.dispose()
