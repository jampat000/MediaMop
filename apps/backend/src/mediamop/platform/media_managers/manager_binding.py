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

from collections.abc import Sequence
from dataclasses import replace

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


def _only_rows_for_scope(signal: ManagerQueueSignal, media_scope: MediaScope) -> ManagerQueueSignal:
    """Drop rows describing the other kind of library.

    A manager that serves both scopes answers for its whole instance, so a Movies
    fan-out gets that manager's in-flight TV imports too. Those rows carry a real title
    and year, so the anchor rules will happily match them against a film with a similar
    name and hold it — a TV import blocking a movie is never a safety signal, it is a
    false positive with a plausible-looking reason attached.

    Filtering here rather than in the dialect keeps the dialect an honest mirror of what
    the manager said, and puts the scope rule in the one place that knows which scope
    was asked about.
    """

    if not signal.is_reported:
        return signal
    kept = tuple(row for row in signal.rows if row.scope == media_scope)
    return signal if len(kept) == len(signal.rows) else replace(signal, rows=kept)


def connections_by_id(
    session: Session,
    settings: MediaMopSettings,
    connection_ids: Sequence[int],
) -> list[ManagerConnection]:
    """Exactly the connections named, in id order. Half-configured ones are dropped.

    A Refiner library states which managers cover it (ADR-0014 §4), so this is the path
    that replaces inferring one from a media scope.
    """

    wanted = set(connection_ids)
    if not wanted:
        return []
    rows = [row for row in _enabled_rows(session) if row.id in wanted]
    return [c for c in (_connection_from_row(settings, row) for row in rows) if c is not None]


def collect_queue_signals(
    session: Session,
    settings: MediaMopSettings,
    *,
    media_scope: MediaScope,
    connection_ids: Sequence[int] | None = None,
) -> tuple[ManagerQueueSignal, ...]:
    """Ask the managers covering this work what they are importing about ``media_scope``.

    ``connection_ids`` is what a library names. Without it the scope binding still
    applies, which is what keeps pre-library callers and payloads working.
    """

    if connection_ids is not None:
        resolved = connections_by_id(session, settings, connection_ids)
    else:
        resolved = connections_for_scope(session, settings, media_scope=media_scope)

    signals: list[ManagerQueueSignal] = []
    for connection in resolved:
        port = port_for_kind(connection.kind)
        if port is None:
            continue
        signals.append(_only_rows_for_scope(port.queue_rows(connection), media_scope))
    return tuple(signals)


def collect_library_truth(
    session: Session,
    settings: MediaMopSettings,
    *,
    media_scope: MediaScope,
    connection_ids: Sequence[int] | None = None,
) -> tuple[ManagerLibraryTruth, ...]:
    """Ask the managers covering this work which library files they still keep."""

    if connection_ids is not None:
        resolved = connections_by_id(session, settings, connection_ids)
    else:
        resolved = connections_for_scope(session, settings, media_scope=media_scope)

    answers: list[ManagerLibraryTruth] = []
    for connection in resolved:
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
