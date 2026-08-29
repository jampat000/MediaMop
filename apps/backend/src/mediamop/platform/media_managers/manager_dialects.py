"""One outbound dialect per media manager kind.

Same principle as the inbound dialects in :mod:`.import_events`: the difference between
managers is how they *phrase* an answer, so phrasing is the only thing that is
per-manager. Each port here turns one product's JSON into the neutral shapes in
:mod:`.manager_port`, and everything downstream reads those.

Adding a manager means adding a port here. It does not mean a new route, job kind,
module, or column.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping
from typing import Any

from mediamop.core.config import MediaMopSettings
from mediamop.platform.media_managers.manager_http import (
    MediaManagerHttpClient,
    MediaManagerHttpError,
    MediaManagerRateLimitedError,
)
from mediamop.platform.media_managers.manager_port import (
    ALL_MEDIA_SCOPES,
    ManagerCapabilities,
    ManagerConnection,
    ManagerDescription,
    ManagerLibraryDescriptor,
    ManagerLibraryTruth,
    ManagerQueueRow,
    ManagerQueueSignal,
    MediaManagerPort,
    MediaScope,
)

logger = logging.getLogger(__name__)

_QUEUE_TIMEOUT_SECONDS = 30.0
_LIBRARY_TIMEOUT_SECONDS = 120.0
_DESCRIBE_TIMEOUT_SECONDS = 15.0

# Radarr and Sonarr page their list endpoints; both behave as a full listing at a cap
# far above any real library.
_ARR_LIBRARY_PAGE_SIZE = 200_000
_ARR_QUEUE_PAGE_SIZE = 1000

# Deluno's documented external integration surface (docs/external-integration-api.md in
# the Deluno repo). ``native`` publishes the same routes because that is what MediaMop's
# own payload contract asks a generic manager for.
_EXTERNAL_MANIFEST_PATH = "/api/integrations/external/manifest"
_EXTERNAL_QUEUE_PATH = "/api/integrations/external/queue"


def _text(value: Any) -> str | None:
    return value.strip() or None if isinstance(value, str) else None


def _first_text(row: Mapping[str, Any], *keys: str) -> str | None:
    for key in keys:
        found = _text(row.get(key))
        if found is not None:
            return found
    return None


def _whole_number(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def _first_number(row: Mapping[str, Any], *keys: str) -> int | None:
    for key in keys:
        found = _whole_number(row.get(key))
        if found is not None:
            return found
    return None


def _dicts(value: Any) -> list[dict[str, Any]]:
    return [x for x in value if isinstance(x, dict)] if isinstance(value, list) else []


def _scope_from_media_type(raw: Any) -> MediaScope | None:
    value = (_text(raw) or "").lower()
    if value in {"movie", "movies", "film", "films"}:
        return "movie"
    if value in {"tv", "series", "show", "shows", "episode", "episodes"}:
        return "tv"
    return None


def _unreachable(connection: ManagerConnection, exc: Exception, *, what: str) -> str:
    """One sentence an operator can act on, with the connection named."""

    if isinstance(exc, MediaManagerRateLimitedError):
        wait = exc.retry_after_seconds
        when = f" It asked MediaMop to wait about {int(wait)}s." if wait else ""
        return (
            f"{connection.label} is rate limiting MediaMop, so it could not say {what}.{when} "
            "MediaMop backed off rather than retrying straight away."
        )
    if isinstance(exc, MediaManagerHttpError):
        detail = str(exc)
        if "HTTP 401" in detail or "HTTP 403" in detail:
            return (
                f"{connection.label} refused MediaMop's API key, so it could not say {what}. "
                "Check the key on the Media managers settings page and save it again."
            )
        return f"{connection.label} did not give MediaMop the answer it expected when asked {what} ({detail})."
    return (
        f"MediaMop could not reach {connection.label} to ask {what} ({exc}). "
        "Check the address is right and that the app is running."
    )


def _client(connection: ManagerConnection, *, timeout_seconds: float) -> MediaManagerHttpClient:
    return MediaManagerHttpClient(connection.base_url, connection.api_key, timeout_seconds=timeout_seconds)


def _paths_under(raw_paths: Iterable[str]) -> tuple[str, ...]:
    return tuple(p.strip() for p in raw_paths if isinstance(p, str) and p.strip())


class ArrV3ManagerPort:
    """Radarr and Sonarr. One product per media scope, one shared v3 wire format."""

    def __init__(self, kind: str, scope: MediaScope, library_path: str, file_key: str | None) -> None:
        self.kind = kind
        self._scope = scope
        self._library_path = library_path
        # Radarr nests the file under ``movieFile``; Sonarr's episodefile rows carry the
        # path directly. That nesting is the whole difference between the two.
        self._file_key = file_key

    def capabilities(self) -> ManagerCapabilities:
        scope_word = "Movies" if self._scope == "movie" else "TV episodes"
        return ManagerCapabilities(
            scopes=frozenset({self._scope}),
            reports_queue=True,
            reports_library_truth=True,
            summary=(
                f"Looks after {scope_word}. MediaMop can ask it what is downloading or importing, "
                "and which files it still keeps in its library."
            ),
        )

    def describe(self, connection: ManagerConnection) -> ManagerDescription:
        caps = self.capabilities()
        try:
            payload = _client(connection, timeout_seconds=_DESCRIBE_TIMEOUT_SECONDS).get_json("/api/v3/rootfolder")
        except (MediaManagerHttpError, OSError) as exc:
            return ManagerDescription(
                connection=connection,
                status="unreachable",
                capabilities=caps,
                detail=_unreachable(connection, exc, what="which folders it manages"),
            )
        rows = _dicts(payload)
        roots = _paths_under(str(row.get("path", "")) for row in rows)
        libraries = tuple(
            ManagerLibraryDescriptor(
                key=str(_first_number(row, "id") or path),
                # An arr root folder has no name of its own; the path is what an
                # operator recognises it by.
                name=path,
                media_scope=self._scope,
                root_path=path,
            )
            for row, path in ((row, _text(row.get("path"))) for row in rows)
            if path
        )
        return ManagerDescription(
            connection=connection,
            status="reported",
            capabilities=caps,
            library_roots=roots,
            libraries=libraries,
        )

    def queue_rows(self, connection: ManagerConnection) -> ManagerQueueSignal:
        try:
            payload = _client(connection, timeout_seconds=_QUEUE_TIMEOUT_SECONDS).get_json(
                "/api/v3/queue",
                params={"pageSize": _ARR_QUEUE_PAGE_SIZE},
            )
        except (MediaManagerHttpError, OSError) as exc:
            return ManagerQueueSignal(
                connection=connection,
                status="unreachable",
                detail=_unreachable(connection, exc, what="what it is importing"),
            )
        records = payload if isinstance(payload, list) else (payload or {}).get("records")
        rows = tuple(ManagerQueueRow(scope=self._scope, payload=row) for row in _dicts(records))
        return ManagerQueueSignal(connection=connection, status="reported", rows=rows)

    def library_truth(self, connection: ManagerConnection, *, media_scope: MediaScope) -> ManagerLibraryTruth:
        if media_scope != self._scope:
            return ManagerLibraryTruth(
                connection=connection,
                status="no_signal",
                detail=f"{connection.label} does not look after this kind of library.",
            )
        try:
            payload = _client(connection, timeout_seconds=_LIBRARY_TIMEOUT_SECONDS).get_json(
                self._library_path,
                params={"pageSize": _ARR_LIBRARY_PAGE_SIZE},
            )
        except (MediaManagerHttpError, OSError) as exc:
            return ManagerLibraryTruth(
                connection=connection,
                status="unreachable",
                detail=_unreachable(connection, exc, what="which files it still keeps"),
            )
        paths: list[str] = []
        for row in _dicts(payload):
            holder = row.get(self._file_key) if self._file_key else row
            if isinstance(holder, Mapping):
                found = _text(holder.get("path"))
                if found is not None:
                    paths.append(found)
        return ManagerLibraryTruth(connection=connection, status="reported", library_file_paths=tuple(paths))


# Deluno job and dispatch states, mapped onto the neutral queue vocabulary the scope
# dialects already read. Anything not listed is treated as still in progress: a row is
# in this response because the manager has something to say about that file, and a state
# MediaMop does not recognise must not read as "finished".
_DELUNO_SETTLED_STATES: frozenset[str] = frozenset(
    {
        "completed",
        "complete",
        "done",
        "finished",
        "succeeded",
        "success",
        "ok",
        "failed",
        "failure",
        "error",
        "cancelled",
        "canceled",
        "aborted",
        "skipped",
        "ignored",
        "rejected",
    }
)
_DELUNO_IMPORT_PENDING_STATES: frozenset[str] = frozenset(
    {
        "importing",
        "importpending",
        "import_pending",
        "import-pending",
        "finalizing",
        "finalising",
        "moving",
        "handoff",
        "handing_off",
    }
)


class ExternalIntegrationManagerPort:
    """Deluno, and anything else speaking MediaMop's own payload shape.

    Both publish ``/api/integrations/external/...``; they differ only in which key names
    they use inside a row, and both sets are accepted here. A manager of this kind serves
    **both** media scopes, so it answers for a Movies library and a TV one without a
    second connection.
    """

    def __init__(self, kind: str) -> None:
        self.kind = kind

    def capabilities(self) -> ManagerCapabilities:
        return ManagerCapabilities(
            scopes=ALL_MEDIA_SCOPES,
            reports_queue=True,
            reports_library_truth=False,
            summary=(
                "Looks after Movies and TV episodes. MediaMop can ask it what is mid-import, but not which "
                "files it still keeps, so folder cleanup stays off unless another manager can answer that."
            ),
        )

    def describe(self, connection: ManagerConnection) -> ManagerDescription:
        caps = self.capabilities()
        try:
            payload = _client(connection, timeout_seconds=_DESCRIBE_TIMEOUT_SECONDS).get_json(_EXTERNAL_MANIFEST_PATH)
        except (MediaManagerHttpError, OSError) as exc:
            return ManagerDescription(
                connection=connection,
                status="unreachable",
                capabilities=caps,
                detail=_unreachable(connection, exc, what="what it manages"),
            )
        libraries = _manifest_libraries(payload)
        scopes = frozenset(
            scope
            for scope in (
                _scope_from_media_type(lib.get("mediaType") or lib.get("media_type") or lib.get("scope"))
                for lib in libraries
            )
            if scope is not None
        )
        roots = _paths_under(_first_text(lib, "path", "rootFolder", "root_folder", "root") or "" for lib in libraries)
        # A manifest that names its libraries narrows what this connection gets asked
        # about; one that does not leaves the static both-scopes assumption alone.
        if scopes:
            caps = ManagerCapabilities(
                scopes=scopes,
                reports_queue=caps.reports_queue,
                reports_library_truth=caps.reports_library_truth,
                summary=caps.summary,
            )
        return ManagerDescription(
            connection=connection,
            status="reported",
            capabilities=caps,
            library_roots=roots,
            libraries=tuple(_manifest_library_descriptor(lib) for lib in libraries if _manifest_library_key(lib)),
        )

    def queue_rows(self, connection: ManagerConnection) -> ManagerQueueSignal:
        try:
            payload = _client(connection, timeout_seconds=_QUEUE_TIMEOUT_SECONDS).get_json(_EXTERNAL_QUEUE_PATH)
        except (MediaManagerHttpError, OSError) as exc:
            return ManagerQueueSignal(
                connection=connection,
                status="unreachable",
                detail=_unreachable(connection, exc, what="what it is importing"),
            )
        rows: list[ManagerQueueRow] = []
        for entry in _external_queue_entries(payload):
            row = _external_queue_row(entry, connection=connection)
            if row is not None:
                rows.append(row)
        return ManagerQueueSignal(connection=connection, status="reported", rows=tuple(rows))

    def library_truth(self, connection: ManagerConnection, *, media_scope: MediaScope) -> ManagerLibraryTruth:
        return ManagerLibraryTruth(
            connection=connection,
            status="no_signal",
            detail=(
                f"{connection.label} tells MediaMop what it manages and what it is importing, but not which "
                "individual files it still keeps, so it cannot clear a folder for deletion."
            ),
        )


def _manifest_library_key(library: Mapping[str, Any]) -> str | None:
    """The manager's own id for a library, kept only as an integration reference.

    Confirmed against a populated manifest (Deluno#331): ``id`` is the library's own
    identifier, a hex string, stable across restarts. The numeric branch stays because
    the arr products' root-folder ids are integers and share this helper.
    """

    number = _first_number(library, "id")
    if number is not None:
        return str(number)
    return _first_text(library, "id")


def _manifest_library_descriptor(library: Mapping[str, Any]) -> ManagerLibraryDescriptor:
    """One manifest entry, read against the confirmed contract.

    The shape was unconfirmed when #351 shipped, because the documented sample was
    captured on an unconfigured instance and showed ``"libraries": []``. It is confirmed
    now (Deluno#331), so this reads the documented keys rather than guessing among
    plausible spellings — a parser that accepts shapes the manager never sends is a
    parser nobody can reason about, and it hides the day the contract really changes.

    ``processorOutputPath`` is populated **only** for a library whose ``importWorkflow``
    is ``refine-before-import``; a ``standard`` library sends an empty string. So the
    workflow is what MediaMop branches on, not whether the path happens to be there.
    """

    key = _manifest_library_key(library) or ""
    name = _first_text(library, "name") or key
    scope = _scope_from_media_type(library.get("mediaType"))
    root = _first_text(library, "rootPath")
    workflow = (_text(library.get("importWorkflow")) or "").strip().lower()
    processes_before_import = workflow == "refine-before-import"
    output = _first_text(library, "processorOutputPath") if processes_before_import else None
    return ManagerLibraryDescriptor(
        key=key,
        name=name,
        media_scope=scope,
        root_path=root,
        output_path=output,
        processes_before_import=processes_before_import,
    )


def _manifest_libraries(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, Mapping):
        for key in ("libraries", "roots", "rootFolders", "root_folders", "items"):
            found = _dicts(payload.get(key))
            if found:
                return found
        return []
    return _dicts(payload)


def _external_queue_entries(payload: Any) -> list[dict[str, Any]]:
    """Every row in a queue response, whichever container the manager wrapped it in.

    Deluno answers with "current jobs plus recent download dispatches", so more than one
    list can be present and all of them count.
    """

    if isinstance(payload, list):
        return _dicts(payload)
    if not isinstance(payload, Mapping):
        return []
    collected: list[dict[str, Any]] = []
    for key in ("jobs", "dispatches", "downloads", "queue", "items", "records", "results"):
        collected.extend(_dicts(payload.get(key)))
    return collected


def _external_queue_status(entry: Mapping[str, Any], *, connection: ManagerConnection) -> str:
    raw = _first_text(entry, "status", "state", "jobStatus", "job_status", "phase") or ""
    value = raw.lower().replace(" ", "_")
    if value in _DELUNO_IMPORT_PENDING_STATES:
        return "importpending"
    if value in _DELUNO_SETTLED_STATES:
        # Passed through unchanged: no scope dialect treats it as active, and keeping the
        # manager's own word makes an activity detail readable.
        return value
    if value:
        logger.debug(
            "Media manager %s reported queue state %r, which MediaMop treats as still in progress.",
            connection.label,
            raw,
        )
    return "downloading"


def _external_queue_row(entry: Mapping[str, Any], *, connection: ManagerConnection) -> ManagerQueueRow | None:
    scope = _scope_from_media_type(
        entry.get("mediaType")
        or entry.get("media_type")
        or entry.get("mediaScope")
        or entry.get("media_scope")
        or entry.get("scope")
    )
    if scope is None:
        return None
    path = _first_text(
        entry,
        "outputPath",
        "output_path",
        "targetPath",
        "target_path",
        "sourcePath",
        "source_path",
        "filePath",
        "file_path",
        "path",
    )
    title = _first_text(entry, "title", "releaseName", "release_name", "name")
    payload: dict[str, Any] = {
        "status": _external_queue_status(entry, connection=connection),
        "outputPath": path,
        "title": title,
        # ``media`` is the neutral entity key the scope dialects already read, so a
        # Deluno row lands on the same title/year anchor path as an arr row.
        "media": {"title": title, "year": _first_number(entry, "year", "releaseYear", "release_year")},
        "entityId": _first_number(entry, "entityId", "entity_id", "mediaId", "media_id", "id"),
    }
    return ManagerQueueRow(scope=scope, payload=payload)


_PORTS: dict[str, MediaManagerPort] = {
    "radarr": ArrV3ManagerPort("radarr", "movie", "/api/v3/movie", "movieFile"),
    "sonarr": ArrV3ManagerPort("sonarr", "tv", "/api/v3/episodefile", None),
    "deluno": ExternalIntegrationManagerPort("deluno"),
    "native": ExternalIntegrationManagerPort("native"),
}


def port_for_kind(kind: str) -> MediaManagerPort | None:
    return _PORTS.get((kind or "").strip().lower())


def capabilities_for_kind(kind: str) -> ManagerCapabilities | None:
    port = port_for_kind(kind)
    return port.capabilities() if port is not None else None


def kinds_serving_scope(media_scope: MediaScope) -> tuple[str, ...]:
    return tuple(sorted(k for k, p in _PORTS.items() if media_scope in p.capabilities().scopes))


def environment_connection_for_scope(settings: MediaMopSettings, media_scope: MediaScope) -> ManagerConnection | None:
    """The credentials that predate the connections table, read as a connection.

    These environment variables are named after the two products that existed when they
    were added, which is why resolving them is product knowledge and lives here rather
    than in the binding layer.
    """

    if media_scope == "tv":
        url, key = settings.arr_http_sonarr_credentials()
        kind = "sonarr"
    else:
        url, key = settings.arr_http_radarr_credentials()
        kind = "radarr"
    if not url or not key:
        return None
    return ManagerConnection(kind=kind, name="from environment", base_url=url, api_key=key, connection_id=None)
