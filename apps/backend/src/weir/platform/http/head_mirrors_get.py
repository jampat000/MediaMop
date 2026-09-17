"""Answer HEAD the way HTTP says to: same as GET, without the body.

FastAPI registers only the method a route declares, so `@router.get(...)` does not
answer HEAD and the request falls through to a 404. That is wrong on its own terms —
`HEAD /health` returning 404 while `GET /health` returns 200 tells a health checker
the endpoint does not exist — and it misleads anything that probes with HEAD before
committing to a real request.

This runs the request as a GET and discards the body, so every GET route answers HEAD
with the same status and headers. A path with no GET handler — a POST-only webhook,
say — then gets the spec-correct 405 instead of a 404, which matters because callers
probe webhooks with HEAD and a 404 tells them the endpoint is missing when it is not.
"""

from __future__ import annotations

from starlette.types import ASGIApp, Message, Receive, Scope, Send


class HeadMirrorsGetMiddleware:
    """Serve HEAD from the GET handler, returning headers without a body."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("method") != "HEAD":
            await self.app(scope, receive, send)
            return

        # Route as a GET so the matching handler runs...
        scope = dict(scope)
        scope["method"] = "GET"

        body_closed = False

        async def send_without_body(message: Message) -> None:
            # ...then drop the body, keeping the status line and headers. Content-Length
            # is deliberately left as GET reported it: RFC 9110 says a HEAD response
            # carries the header fields the GET would have, including the length the
            # body would have had.
            nonlocal body_closed
            if message["type"] == "http.response.body":
                # A streaming handler sends many body chunks. Close the response on the
                # first one and swallow the rest, or we would send after completion.
                if not body_closed:
                    body_closed = True
                    await send({"type": "http.response.body", "body": b"", "more_body": False})
                return
            await send(message)

        await self.app(scope, receive, send_without_body)
