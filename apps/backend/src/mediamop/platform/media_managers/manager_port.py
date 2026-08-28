"""The three questions MediaMop asks a media manager, and the answers it accepts.

ADR-0013 made a connection a row with a ``kind``. This is the outbound half of that
decision: instead of "call Radarr", a caller asks *the managers that look after this
scope* three things.

``describe()``
    What do you manage — which scopes, which library roots, and which of the questions
    below can you actually answer?

``queue_rows()``
    Is anything mid-import right now? Rows come back in a shape
    :func:`~mediamop.modules.refiner.queue_adapter.map_queue_row_to_refiner_view` can
    read, each tagged with the scope it describes.

``library_truth()``
    Do you still keep a library file inside this folder? This is the gate in front of a
    delete, so it is the one that must never guess.

The answers are three-valued on purpose. ``reported`` carries data — possibly none,
which means "I looked and there is nothing". ``no_signal`` means this manager cannot
answer that question at all. ``unreachable`` means it should have been able to and
was not. **Only ``reported`` with no rows means "safe to proceed".** An empty tuple on
its own would have collapsed all three into "nothing is importing", which is exactly
the bug this port exists to remove.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

MediaScope = Literal["movie", "tv"]
ALL_MEDIA_SCOPES: frozenset[MediaScope] = frozenset({"movie", "tv"})

SignalStatus = Literal["reported", "no_signal", "unreachable"]

# Short, operator-facing name for a kind. Distinct from the inbound dialect's
# ``display_name`` because that one spells out the payload shape ("Generic (MediaMop
# native payload)"), which reads badly inside a sentence about a running import.
_KIND_LABELS: dict[str, str] = {
    "radarr": "Radarr",
    "sonarr": "Sonarr",
    "deluno": "Deluno",
    "native": "Media manager",
}


def label_for_connection(kind: str, name: str) -> str:
    """``"Deluno (Main)"`` — what a blocked-upstream reason names.

    A connection named after its own product is not repeated: a Deluno connection
    called "Deluno" is just "Deluno".
    """

    product = _KIND_LABELS.get((kind or "").strip().lower(), "Media manager")
    label = (name or "").strip()
    if not label:
        return product
    if label.casefold() == product.casefold():
        return label
    return f"{product} ({label})"


@dataclass(frozen=True, slots=True)
class ManagerConnection:
    """One configured manager, resolved far enough to talk to.

    ``connection_id`` is ``None`` for the environment-variable credentials that predate
    the connections table; everything else about them behaves the same.
    """

    kind: str
    name: str
    base_url: str
    api_key: str
    connection_id: int | None = None

    @property
    def label(self) -> str:
        return label_for_connection(self.kind, self.name)


@dataclass(frozen=True, slots=True)
class ManagerQueueRow:
    """One in-progress item, tagged with the scope whose dialect can read it."""

    scope: MediaScope
    payload: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class ManagerQueueSignal:
    """What one manager said when asked whether it is mid-import.

    ``status == "reported"`` and ``rows == ()`` is the only combination that means
    "nothing is importing". The other two mean "do not treat this as clear".
    """

    connection: ManagerConnection
    status: SignalStatus
    rows: tuple[ManagerQueueRow, ...] = ()
    detail: str | None = None

    @property
    def is_reported(self) -> bool:
        return self.status == "reported"


@dataclass(frozen=True, slots=True)
class ManagerLibraryTruth:
    """Library file paths one manager still keeps inside the folder that was asked about.

    ``status == "reported"`` with an empty ``library_file_paths`` is the only answer
    that clears a delete.
    """

    connection: ManagerConnection
    status: SignalStatus
    library_file_paths: tuple[str, ...] = ()
    detail: str | None = None

    @property
    def is_reported(self) -> bool:
        return self.status == "reported"


@dataclass(frozen=True, slots=True)
class ManagerCapabilities:
    """What a kind of manager can be asked, before anyone talks to it.

    Static per kind, so connection binding never spends a request working out whether a
    manager is worth asking.
    """

    scopes: frozenset[MediaScope]
    reports_queue: bool
    reports_library_truth: bool
    summary: str


@dataclass(frozen=True, slots=True)
class ManagerLibraryDescriptor:
    """One library a manager says it looks after.

    ``key`` is the manager's own identifier, kept as a durable integration reference —
    Deluno's documentation asks external tools to store its ids for exactly this and
    nothing else. ``root_path`` is a path **on the manager's host**, which is not
    necessarily a path MediaMop can see.
    """

    key: str
    name: str
    media_scope: MediaScope | None
    root_path: str | None = None


@dataclass(frozen=True, slots=True)
class ManagerDescription:
    """A live answer to "what do you manage", degrading to the static capabilities."""

    connection: ManagerConnection
    status: SignalStatus
    capabilities: ManagerCapabilities
    library_roots: tuple[str, ...] = field(default=())
    libraries: tuple[ManagerLibraryDescriptor, ...] = field(default=())
    detail: str | None = None


class MediaManagerPort(Protocol):
    """One kind of manager, answering the three questions."""

    kind: str

    def capabilities(self) -> ManagerCapabilities:
        """What this kind can be asked. No network."""

    def describe(self, connection: ManagerConnection) -> ManagerDescription:
        """What this manager says it manages."""

    def queue_rows(self, connection: ManagerConnection) -> ManagerQueueSignal:
        """What this manager says is mid-import."""

    def library_truth(
        self,
        connection: ManagerConnection,
        *,
        media_scope: MediaScope,
    ) -> ManagerLibraryTruth:
        """Every library file path this manager still keeps for ``media_scope``.

        Callers filter to the folder they care about; a manager cannot be asked "is
        this one folder still yours" without leaking MediaMop's paths into the query.
        """
