"""Builders for media-manager port answers, so tests state the scenario and nothing else."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from mediamop.platform.media_managers.manager_port import (
    ManagerConnection,
    ManagerLibraryTruth,
    ManagerQueueRow,
    ManagerQueueSignal,
    MediaScope,
)


def connection(*, kind: str = "radarr", name: str = "Main", connection_id: int = 1) -> ManagerConnection:
    return ManagerConnection(
        kind=kind,
        name=name,
        base_url="http://manager.local",
        api_key="key",
        connection_id=connection_id,
    )


def reported(
    rows: Sequence[Mapping[str, Any]] = (),
    *,
    scope: MediaScope = "movie",
    kind: str = "radarr",
    name: str = "Main",
    connection_id: int = 1,
) -> ManagerQueueSignal:
    """A manager that answered. An empty ``rows`` means "I looked, nothing is importing"."""

    return ManagerQueueSignal(
        connection=connection(kind=kind, name=name, connection_id=connection_id),
        status="reported",
        rows=tuple(ManagerQueueRow(scope=scope, payload=row) for row in rows),
    )


def unreachable(
    *,
    kind: str = "radarr",
    name: str = "Main",
    connection_id: int = 1,
    detail: str = "MediaMop could not reach this manager.",
) -> ManagerQueueSignal:
    return ManagerQueueSignal(
        connection=connection(kind=kind, name=name, connection_id=connection_id),
        status="unreachable",
        detail=detail,
    )


def no_queue_signal(
    *,
    kind: str = "native",
    name: str = "Main",
    connection_id: int = 1,
    detail: str = "This manager cannot report a queue.",
) -> ManagerQueueSignal:
    return ManagerQueueSignal(
        connection=connection(kind=kind, name=name, connection_id=connection_id),
        status="no_signal",
        detail=detail,
    )


def truth_reported(
    paths: Sequence[str] = (),
    *,
    kind: str = "radarr",
    name: str = "Main",
    connection_id: int = 1,
) -> ManagerLibraryTruth:
    return ManagerLibraryTruth(
        connection=connection(kind=kind, name=name, connection_id=connection_id),
        status="reported",
        library_file_paths=tuple(paths),
    )


def truth_unreachable(
    *,
    kind: str = "radarr",
    name: str = "Main",
    connection_id: int = 1,
    detail: str = "MediaMop could not reach this manager.",
) -> ManagerLibraryTruth:
    return ManagerLibraryTruth(
        connection=connection(kind=kind, name=name, connection_id=connection_id),
        status="unreachable",
        detail=detail,
    )


def truth_no_signal(
    *,
    kind: str = "deluno",
    name: str = "Main",
    connection_id: int = 1,
    detail: str = "This manager cannot say which files it keeps.",
) -> ManagerLibraryTruth:
    return ManagerLibraryTruth(
        connection=connection(kind=kind, name=name, connection_id=connection_id),
        status="no_signal",
        detail=detail,
    )
