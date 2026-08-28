"""Which managers look after a media scope, and asking all of them.

This replaces the single ``(url, key)`` tuple that Refiner used to resolve from a
hardcoded scope-to-product map. That map could only ever answer with one manager, so a
4K-plus-1080p pair of instances was invisible, and so was one manager running alongside
another during a migration.

A scope now resolves to **N connections** and the caller asks all of them. What to do
with a manager that could not answer is deliberately left to the caller, because the
right answer differs: a watched-folder scan degrades to the file-settling gates and
says so, while anything standing in front of a delete refuses to proceed.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from mediamop.core.config import MediaMopSettings
from mediamop.platform.arr_library.arr_connection_crypto import decrypt_arr_api_key
from mediamop.platform.media_managers.connection_model import MediaManagerConnectionRow
from mediamop.platform.media_managers.manager_dialects import environment_connection_for_scope, port_for_kind
from mediamop.platform.media_managers.manager_port import (
    ManagerConnection,
    ManagerDescription,
    ManagerLibraryTruth,
    ManagerQueueSignal,
    MediaScope,
)


def _connection_from_row(settings: MediaMopSettings, row: MediaManagerConnectionRow) -> ManagerConnection | None:
    url = (row.base_url or "").strip()
    ciphertext = (row.api_key_ciphertext or "").strip()
    if not url or not ciphertext:
        return None
    key = decrypt_arr_api_key(settings, ciphertext)
    if not key:
        return None
    return ManagerConnection(kind=row.kind, name=row.name, base_url=url, api_key=key, connection_id=row.id)


def _enabled_rows(session: Session) -> list[MediaManagerConnectionRow]:
    return list(
        session.scalars(
            select(MediaManagerConnectionRow)
            .where(MediaManagerConnectionRow.enabled.is_(True))
            .order_by(MediaManagerConnectionRow.id)
        )
    )


def _row_serves_scope(row: MediaManagerConnectionRow, media_scope: MediaScope) -> bool:
    port = port_for_kind(row.kind)
    return port is not None and media_scope in port.capabilities().scopes


def connections_for_scope(
    session: Session,
    settings: MediaMopSettings,
    *,
    media_scope: MediaScope,
) -> list[ManagerConnection]:
    """Every enabled, credentialed manager that looks after ``media_scope``.

    A manager serving both scopes (Deluno, or anything speaking the native shape)
    appears for both without a second connection.
    """

    rows = _enabled_rows(session)
    serving = [row for row in rows if _row_serves_scope(row, media_scope)]
    resolved = [c for c in (_connection_from_row(settings, row) for row in serving) if c is not None]
    if resolved:
        return resolved
    # An enabled row that is half-configured is still a deliberate answer to "which
    # manager looks after this", so the environment variables only apply when nothing
    # in the table claims the scope at all.
    if serving:
        return []
    # The environment variables that predate the connections table. Kept as a fallback so
    # an instance that never opened the settings page keeps working.
    env = environment_connection_for_scope(settings, media_scope)
    return [env] if env is not None else []


def all_enabled_connections(session: Session, settings: MediaMopSettings) -> list[ManagerConnection]:
    return [c for c in (_connection_from_row(settings, row) for row in _enabled_rows(session)) if c is not None]


def collect_queue_signals(
    session: Session,
    settings: MediaMopSettings,
    *,
    media_scope: MediaScope,
) -> tuple[ManagerQueueSignal, ...]:
    """Ask every manager covering ``media_scope`` what it is importing."""

    signals: list[ManagerQueueSignal] = []
    for connection in connections_for_scope(session, settings, media_scope=media_scope):
        port = port_for_kind(connection.kind)
        if port is None:
            continue
        signals.append(port.queue_rows(connection))
    return tuple(signals)


def collect_library_truth(
    session: Session,
    settings: MediaMopSettings,
    *,
    media_scope: MediaScope,
) -> tuple[ManagerLibraryTruth, ...]:
    """Ask every manager covering ``media_scope`` which library files it still keeps."""

    answers: list[ManagerLibraryTruth] = []
    for connection in connections_for_scope(session, settings, media_scope=media_scope):
        port = port_for_kind(connection.kind)
        if port is None:
            continue
        answers.append(port.library_truth(connection, media_scope=media_scope))
    return tuple(answers)


def describe_connections(session: Session, settings: MediaMopSettings) -> tuple[ManagerDescription, ...]:
    """What each configured manager says it manages."""

    described: list[ManagerDescription] = []
    for connection in all_enabled_connections(session, settings):
        port = port_for_kind(connection.kind)
        if port is None:
            continue
        described.append(port.describe(connection))
    return tuple(described)
