"""A fake media manager: a real HTTP server on 127.0.0.1 that records every request.

Weir talks to Sonarr, Radarr and Deluno over HTTP, so the contract suite gives it something real
to talk to. Each fake starts with the minimum each product answers (verified against the paths
Weir calls in ``platform/media_managers``) and a test scripts the rest:

    fake = FakeManager.deluno()
    fake.route("GET", "/api/integrations/external/queue", {"jobs": [...]})
    fake.route("POST", "/api/integrations/processors/events", status=503)
    ...
    fake.wait_for_request("POST", "/api/integrations/processors/events")

A route's response can be a value (sent as JSON), or a callable ``(request) -> Reply | value``
for behaviour that depends on the request or changes over time.
"""

from __future__ import annotations

import json
import re
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlsplit

API_KEY = "contract-fake-manager-api-key"


@dataclass(frozen=True)
class RecordedRequest:
    method: str
    path: str
    query: dict[str, list[str]]
    headers: dict[str, str]
    body: bytes
    at: float

    @property
    def json(self) -> Any:
        return json.loads(self.body.decode("utf-8")) if self.body else None

    def header(self, name: str) -> str | None:
        wanted = name.lower()
        for key, value in self.headers.items():
            if key.lower() == wanted:
                return value
        return None


@dataclass
class Reply:
    status: int = 200
    body: Any = None
    headers: dict[str, str] = field(default_factory=dict)


Responder = Callable[[RecordedRequest], "Reply | Any"]


@dataclass
class _Route:
    method: str
    pattern: re.Pattern[str]
    responder: Responder


def _compile(path: str) -> re.Pattern[str]:
    """``/api/v3/queue/{id}`` style placeholders match one path segment."""

    escaped = re.escape(path)
    return re.compile("^" + re.sub(r"\\\{[^/]+?\\\}", r"[^/]+", escaped) + "$")


class FakeManager:
    """A scripted, recording HTTP server. Start it with ``with`` or :meth:`start`."""

    def __init__(self, kind: str, *, api_key: str = API_KEY) -> None:
        self.kind = kind
        self.api_key = api_key
        self.requests: list[RecordedRequest] = []
        self._routes: list[_Route] = []
        self._lock = threading.Lock()
        self._changed = threading.Condition(self._lock)
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    # --- presets --------------------------------------------------------------------------------

    @classmethod
    def arr(cls, kind: str, *, root_folders: list[str] | None = None) -> FakeManager:
        """Sonarr or Radarr v3: status, root folders, a queue that can be scripted, command, manual import."""

        if kind not in ("sonarr", "radarr"):
            raise ValueError("kind must be sonarr or radarr")
        fake = cls(kind)
        fake.queue: list[dict[str, Any]] = []  # type: ignore[misc]
        fake.library: list[dict[str, Any]] = []  # type: ignore[misc]
        fake.route("GET", "/api/v3/system/status", {"appName": kind.capitalize(), "version": "4.0.0.0"})
        fake.route(
            "GET",
            "/api/v3/rootfolder",
            lambda _r: [{"id": i + 1, "path": p} for i, p in enumerate(root_folders or [])],
        )

        def queue(request: RecordedRequest) -> Any:
            return {"page": 1, "pageSize": 1000, "totalRecords": len(fake.queue), "records": list(fake.queue)}

        def remove(request: RecordedRequest) -> Reply:
            item_id = request.path.rsplit("/", 1)[-1]
            before = len(fake.queue)
            fake.queue[:] = [row for row in fake.queue if str(row.get("id")) != item_id]
            return Reply(200 if len(fake.queue) < before else 404, None)

        fake.route("GET", "/api/v3/queue", queue)
        fake.route("DELETE", "/api/v3/queue/{id}", remove)
        fake.route("POST", "/api/v3/command", lambda r: Reply(201, {"id": 1, "name": (r.json or {}).get("name")}))
        fake.route("GET", "/api/v3/manualimport", [])
        fake.route("GET", "/api/v3/movie" if kind == "radarr" else "/api/v3/episodefile", lambda _r: fake.library)
        return fake

    @classmethod
    def deluno(
        cls,
        *,
        libraries: list[dict[str, Any]] | None = None,
        capabilities: list[str] | None = None,
    ) -> FakeManager:
        """Deluno's external-integration surface and its processor events endpoint."""

        fake = cls("deluno")
        fake.libraries: list[dict[str, Any]] = list(libraries or [])  # type: ignore[misc]
        fake.capabilities: list[str] = list(capabilities or [])  # type: ignore[misc]
        fake.jobs: list[dict[str, Any]] = []  # type: ignore[misc]
        fake.route("GET", "/api/integrations/external/health", {"status": "ok"})
        fake.route(
            "GET",
            "/api/integrations/external/manifest",
            lambda _r: {"name": "Deluno", "libraries": fake.libraries, "capabilities": fake.capabilities},
        )
        fake.route("GET", "/api/integrations/external/queue", lambda _r: {"jobs": fake.jobs, "dispatches": []})
        fake.route("POST", "/api/integrations/processors/events", Reply(202, {"accepted": True}))
        return fake

    # --- scripting ------------------------------------------------------------------------------

    def route(self, method: str, path: str, response: Any = None, *, status: int | None = None) -> None:
        """Answer ``method path``. Later routes win over earlier ones for the same request."""

        if callable(response):
            responder: Responder = response
        elif isinstance(response, Reply):
            fixed = response
            responder = lambda _r: fixed  # noqa: E731
        else:
            fixed_reply = Reply(status or 200, response)
            responder = lambda _r: fixed_reply  # noqa: E731
        if status is not None and callable(response):
            inner = responder
            responder = lambda r: Reply(status, inner(r))  # noqa: E731
        with self._lock:
            self._routes.insert(0, _Route(method.upper(), _compile(path), responder))

    def requests_to(self, method: str, path_prefix: str) -> list[RecordedRequest]:
        with self._lock:
            return [r for r in self.requests if r.method == method.upper() and r.path.startswith(path_prefix)]

    def wait_for_request(
        self,
        method: str,
        path_prefix: str,
        *,
        count: int = 1,
        timeout_s: float = 60.0,
        where: Callable[[RecordedRequest], bool] | None = None,
    ) -> list[RecordedRequest]:
        deadline = time.monotonic() + timeout_s
        with self._changed:
            while True:
                found = [
                    r
                    for r in self.requests
                    if r.method == method.upper() and r.path.startswith(path_prefix) and (where is None or where(r))
                ]
                if len(found) >= count:
                    return found
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    seen = ", ".join(f"{r.method} {r.path}" for r in self.requests[-20:]) or "nothing"
                    raise AssertionError(
                        f"{self.kind} fake never received {count}x {method} {path_prefix} within {timeout_s}s; "
                        f"last requests: {seen}"
                    )
                self._changed.wait(timeout=min(remaining, 0.5))

    # --- server ---------------------------------------------------------------------------------

    @property
    def base_url(self) -> str:
        if self._server is None:
            raise RuntimeError("The fake manager is not running.")
        return f"http://127.0.0.1:{self._server.server_address[1]}"

    def start(self) -> FakeManager:
        fake = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *_args: object) -> None:
                return

            def _handle(self) -> None:
                length = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(length) if length else b""
                split = urlsplit(self.path)
                request = RecordedRequest(
                    method=self.command,
                    path=split.path,
                    query=parse_qs(split.query),
                    headers=dict(self.headers.items()),
                    body=body,
                    at=time.time(),
                )
                with fake._changed:
                    fake.requests.append(request)
                    routes = list(fake._routes)
                    fake._changed.notify_all()
                reply = Reply(404, {"message": f"fake {fake.kind} has no route for {self.command} {split.path}"})
                for route in routes:
                    if route.method == self.command and route.pattern.match(split.path):
                        try:
                            produced = route.responder(request)
                        except Exception as exc:  # noqa: BLE001 - a broken script answers 500, visibly
                            produced = Reply(500, {"message": f"fake responder raised: {exc!r}"})
                        reply = produced if isinstance(produced, Reply) else Reply(200, produced)
                        break
                payload = b"" if reply.body is None else json.dumps(reply.body).encode("utf-8")
                self.send_response(reply.status)
                if payload:
                    self.send_header("Content-Type", "application/json")
                for key, value in reply.headers.items():
                    self.send_header(key, value)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                if payload and self.command != "HEAD":
                    self.wfile.write(payload)

            do_GET = do_POST = do_PUT = do_DELETE = do_PATCH = do_HEAD = _handle  # noqa: N815

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._server.daemon_threads = True
        self._thread = threading.Thread(target=self._server.serve_forever, name=f"fake-{self.kind}", daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
        self._server = None

    def __enter__(self) -> FakeManager:
        return self.start()

    def __exit__(self, *_exc: object) -> None:
        self.stop()
