"""Media managers: the products MediaMop takes work from and reports back to.

Radarr and Sonarr are two of them, Deluno is another, and anything that can post JSON
is a fourth. They differ only in how they *phrase* things, so the difference lives in a
dialect rather than in routes, job kinds, or modules — inbound in :mod:`.import_events`,
outbound in :mod:`.manager_dialects`.

Both directions are keyed by ``kind`` and answer for **N connections**: a scope resolves
to every manager that looks after it (:mod:`.manager_binding`), not to one chosen by a
product name.
"""

from __future__ import annotations

from mediamop.platform.media_managers.handoff_paths import (
    HandoffPathResult,
    relative_media_path_for_handoff,
)
from mediamop.platform.media_managers.import_events import (
    MEDIA_MANAGER_DIALECTS,
    MediaManagerDialect,
    MediaManagerImportEvent,
    dialect_for_source,
    known_source_keys,
)
from mediamop.platform.media_managers.manager_binding import (
    collect_library_truth,
    collect_queue_signals,
    connections_for_scope,
    describe_connections,
)
from mediamop.platform.media_managers.manager_dialects import capabilities_for_kind, port_for_kind
from mediamop.platform.media_managers.manager_port import (
    ManagerCapabilities,
    ManagerConnection,
    ManagerDescription,
    ManagerLibraryTruth,
    ManagerQueueRow,
    ManagerQueueSignal,
    MediaManagerPort,
    label_for_connection,
)

__all__ = [
    "MEDIA_MANAGER_DIALECTS",
    "HandoffPathResult",
    "ManagerCapabilities",
    "ManagerConnection",
    "ManagerDescription",
    "ManagerLibraryTruth",
    "ManagerQueueRow",
    "ManagerQueueSignal",
    "MediaManagerDialect",
    "MediaManagerImportEvent",
    "MediaManagerPort",
    "capabilities_for_kind",
    "collect_library_truth",
    "collect_queue_signals",
    "connections_for_scope",
    "describe_connections",
    "dialect_for_source",
    "known_source_keys",
    "label_for_connection",
    "port_for_kind",
    "relative_media_path_for_handoff",
]
