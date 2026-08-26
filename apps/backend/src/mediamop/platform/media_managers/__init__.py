"""Media managers: the products that tell MediaMop about files.

Radarr and Sonarr are two of them, Deluno is another, and anything that can post JSON
is a fourth. They differ only in how they phrase an event, so the difference lives in a
dialect (:mod:`.import_events`) rather than in routes, job kinds, or modules.
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

__all__ = [
    "MEDIA_MANAGER_DIALECTS",
    "HandoffPathResult",
    "MediaManagerDialect",
    "MediaManagerImportEvent",
    "dialect_for_source",
    "known_source_keys",
    "relative_media_path_for_handoff",
]
