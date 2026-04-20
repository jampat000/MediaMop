"""CRUD for singleton ``broker_settings``."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from mediamop.modules.broker.broker_settings_model import BrokerSettingsRow

_SINGLETON_ID = 1


def get_or_create_settings(session: Session) -> BrokerSettingsRow:
    row = session.scalars(select(BrokerSettingsRow).where(BrokerSettingsRow.id == _SINGLETON_ID)).one_or_none()
    if row is None:
        row = BrokerSettingsRow(
            id=_SINGLETON_ID,
            proxy_api_key=str(uuid.uuid4()),
        )
        session.add(row)
        session.flush()
    return row


def get_proxy_api_key(session: Session) -> str:
    return get_or_create_settings(session).proxy_api_key


def rotate_proxy_api_key(session: Session) -> str:
    row = get_or_create_settings(session)
    row.proxy_api_key = str(uuid.uuid4())
    session.flush()
    return row.proxy_api_key
