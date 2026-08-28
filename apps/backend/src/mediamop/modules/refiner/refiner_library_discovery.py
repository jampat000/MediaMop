"""Create Refiner libraries from what a connected media manager already knows.

The operator typing a watched folder into MediaMop is re-entering information the
manager holds and keeps current — and until libraries existed they could only enter two
of them. Deluno publishes a manifest built for exactly this, and the arr products expose
a cruder version of the same thing through their root folders.

Two rules shape everything here, and both come from what Refiner does after a successful
pass — it deletes source folders:

**Re-sync reports, it never applies.** A watched folder that silently repoints is a
destructive surprise. Drift is surfaced with the manager's value and MediaMop's own value
side by side, and the operator decides.

**A path on the manager's host is not automatically a path MediaMop can see.** The check
is purely textual, the same approach ``handoff_paths`` already uses, so it behaves
identically on the API host and the worker and fails with a sentence rather than a stat
error on an unmounted share.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from mediamop.core.config import MediaMopSettings
from mediamop.modules.refiner.refiner_library_model import RefinerLibraryRow
from mediamop.modules.refiner.refiner_library_service import list_libraries
from mediamop.platform.media_managers.connection_model import MediaManagerConnectionRow
from mediamop.platform.media_managers.manager_binding import connections_by_id
from mediamop.platform.media_managers.manager_dialects import port_for_kind
from mediamop.platform.media_managers.manager_port import ManagerLibraryDescriptor

DriftKind = Literal["root_moved", "library_removed", "library_added", "path_not_local"]


class RefinerDiscoveryError(ValueError):
    """Discovery could not run, with an operator-readable reason."""


@dataclass(frozen=True, slots=True)
class DiscoverableLibrary:
    """One library a manager reports, and whether MediaMop already has it."""

    key: str
    name: str
    media_scope: str | None
    root_path: str | None
    already_imported: bool
    local_path_problem: str | None


@dataclass(frozen=True, slots=True)
class LibraryDrift:
    """A difference between what the manager says and what MediaMop has saved."""

    kind: DriftKind
    library_id: int | None
    library_name: str
    manager_value: str | None
    mediamop_value: str | None
    detail: str


def _comparable(path: str) -> str:
    """Case- and separator-insensitive, matching ``handoff_paths``."""

    return path.replace("\\", "/").strip().rstrip("/").lower()


def _looks_absolute(raw: str) -> bool:
    """Absolute on *any* host, judged textually.

    ``Path.is_absolute()`` answers for the host running this code, so a perfectly good
    POSIX root reported by a Linux manager reads as relative on Windows. The manager's
    path is not this host's path — that is the whole point — so the shape is what is
    checked here, and whether MediaMop can actually see it is the next question.
    """

    text = raw.replace("\\", "/")
    if text.startswith("/"):
        return True
    # Drive letter (C:/...) or UNC (//server/share).
    return bool(re.match(r"^[A-Za-z]:/", text)) or text.startswith("//")


def local_path_problem(root_path: str | None) -> str | None:
    """Why a manager-reported root cannot be used locally, or ``None`` if it can.

    Deliberately not a filesystem check first: a share that is simply not mounted yet
    should read as "not visible here", not as a crash. The existence check comes last
    and only sharpens the message.
    """

    raw = (root_path or "").strip()
    if not raw:
        return (
            "The manager did not say where this library lives, so MediaMop has no folder to watch. "
            "Set the watched folder yourself after importing."
        )
    if not _looks_absolute(raw):
        return f"The manager reported {raw!r}, which is not an absolute path MediaMop can resolve."
    if not Path(raw).expanduser().is_dir():
        return (
            f"The manager sees this library at {raw!r}. That path does not exist on the machine running "
            "MediaMop — both hosts have to see the same folder at the same path. Mount it there, or set "
            "MediaMop's own watched folder after importing."
        )
    return None


def _descriptors_for(
    session: Session,
    settings: MediaMopSettings,
    connection_row: MediaManagerConnectionRow,
) -> tuple[ManagerLibraryDescriptor, ...]:
    resolved = connections_by_id(session, settings, [connection_row.id])
    if not resolved:
        raise RefinerDiscoveryError(
            f"{connection_row.name} has no saved address and API key, so MediaMop cannot ask it anything."
        )
    port = port_for_kind(connection_row.kind)
    if port is None:
        raise RefinerDiscoveryError(f"MediaMop does not know how to talk to a {connection_row.kind} connection.")
    described = port.describe(resolved[0])
    if described.status != "reported":
        raise RefinerDiscoveryError(
            described.detail or f"{resolved[0].label} did not answer when asked what it manages."
        )
    return described.libraries


def discoverable_libraries(
    session: Session,
    settings: MediaMopSettings,
    connection_row: MediaManagerConnectionRow,
) -> list[DiscoverableLibrary]:
    """What this manager reports, marked up with what MediaMop already has."""

    imported = {
        (row.discovered_from_connection_id, row.discovered_library_key)
        for row in list_libraries(session)
        if row.discovered_library_key
    }
    out: list[DiscoverableLibrary] = []
    for descriptor in _descriptors_for(session, settings, connection_row):
        out.append(
            DiscoverableLibrary(
                key=descriptor.key,
                name=descriptor.name,
                media_scope=descriptor.media_scope,
                root_path=descriptor.root_path,
                already_imported=(connection_row.id, descriptor.key) in imported,
                local_path_problem=local_path_problem(descriptor.root_path),
            )
        )
    return out


def _unique_name(session: Session, wanted: str) -> str:
    existing = {row.name for row in list_libraries(session)}
    if wanted not in existing:
        return wanted
    for suffix in range(2, 100):
        candidate = f"{wanted} ({suffix})"
        if candidate not in existing:
            return candidate
    raise RefinerDiscoveryError(f"Too many libraries already named like {wanted!r}.")


def import_libraries(
    session: Session,
    settings: MediaMopSettings,
    connection_row: MediaManagerConnectionRow,
    *,
    keys: list[str],
) -> list[RefinerLibraryRow]:
    """Create a Refiner library per selected manager library.

    The manager's id is stored as a durable integration reference, which is what Deluno's
    own guidance asks external tools to keep. Everything else is an ordinary library:
    editable afterwards, and indistinguishable from a hand-made one everywhere else.
    """

    wanted = [k for k in keys if k]
    if not wanted:
        raise RefinerDiscoveryError("Choose at least one library to import.")

    by_key = {d.key: d for d in _descriptors_for(session, settings, connection_row)}
    missing = [k for k in wanted if k not in by_key]
    if missing:
        raise RefinerDiscoveryError(
            f"{connection_row.name} no longer reports a library with id {missing[0]}. Refresh the list and try again."
        )

    highest = session.scalars(
        select(RefinerLibraryRow.display_order).order_by(RefinerLibraryRow.display_order.desc())
    ).first()
    order = int(highest or 0)

    created: list[RefinerLibraryRow] = []
    for key in wanted:
        descriptor = by_key[key]
        order += 1
        # An unusable root is imported as an empty watched folder rather than a path
        # MediaMop cannot see: a library pointed at a folder that is not there would
        # fail every scan, and the operator is told why on the way in.
        usable_root = descriptor.root_path if local_path_problem(descriptor.root_path) is None else ""
        row = RefinerLibraryRow(
            name=_unique_name(session, descriptor.name or f"{connection_row.name} library {key}"),
            media_scope=descriptor.media_scope or "movie",
            display_order=order,
            watched_folder=usable_root or "",
            discovered_from_connection_id=connection_row.id,
            discovered_library_key=key,
        )
        session.add(row)
        session.flush()
        created.append(row)
    return created


def resync_drift(
    session: Session,
    settings: MediaMopSettings,
    connection_row: MediaManagerConnectionRow,
) -> list[LibraryDrift]:
    """Differences between the manager and MediaMop. Reported only, never applied."""

    descriptors = {d.key: d for d in _descriptors_for(session, settings, connection_row)}
    linked = [
        row
        for row in list_libraries(session)
        if row.discovered_from_connection_id == connection_row.id and row.discovered_library_key
    ]

    drift: list[LibraryDrift] = []
    for row in linked:
        descriptor = descriptors.get(row.discovered_library_key or "")
        if descriptor is None:
            drift.append(
                LibraryDrift(
                    kind="library_removed",
                    library_id=row.id,
                    library_name=row.name,
                    manager_value=None,
                    mediamop_value=row.watched_folder or None,
                    detail=(
                        f"{connection_row.name} no longer reports this library. MediaMop has left it exactly as "
                        "it is — remove it here if it is genuinely gone, or unlink it to keep it as a manual one."
                    ),
                )
            )
            continue
        manager_root = (descriptor.root_path or "").strip()
        saved = (row.watched_folder or "").strip()
        if manager_root and saved and _comparable(manager_root) != _comparable(saved):
            drift.append(
                LibraryDrift(
                    kind="root_moved",
                    library_id=row.id,
                    library_name=row.name,
                    manager_value=manager_root,
                    mediamop_value=saved,
                    detail=(
                        f"{connection_row.name} now says this library lives at {manager_root!r}, but MediaMop is "
                        f"watching {saved!r}. Nothing has been changed — Refiner deletes source folders after a "
                        "successful pass, so a watched folder only moves when you move it."
                    ),
                )
            )
        problem = local_path_problem(descriptor.root_path)
        if problem and not saved:
            drift.append(
                LibraryDrift(
                    kind="path_not_local",
                    library_id=row.id,
                    library_name=row.name,
                    manager_value=manager_root or None,
                    mediamop_value=None,
                    detail=problem,
                )
            )

    known = {row.discovered_library_key for row in linked}
    for key, descriptor in descriptors.items():
        if key in known:
            continue
        drift.append(
            LibraryDrift(
                kind="library_added",
                library_id=None,
                library_name=descriptor.name,
                manager_value=descriptor.root_path,
                mediamop_value=None,
                detail=(
                    f"{connection_row.name} reports a library MediaMop has not imported. Import it if you want "
                    "Refiner to process it."
                ),
            )
        )
    return drift


def unlink_library(session: Session, row: RefinerLibraryRow) -> RefinerLibraryRow:
    """Forget where a library came from, keeping the library itself untouched."""

    row.discovered_from_connection_id = None
    row.discovered_library_key = None
    session.add(row)
    session.flush()
    return row
