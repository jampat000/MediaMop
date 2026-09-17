"""A thin HTTP client for the Weir API: cookies, CSRF and sign-in, nothing Weir-specific inside.

Every method returns the raw ``httpx.Response`` so a test asserts on status codes, headers and
bodies exactly as a browser or a media manager would see them.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import httpx

ADMIN_USERNAME = "alice"
ADMIN_PASSWORD = "test-password-strong"
API = "/api/v1"


class WeirClient:
    """One browser-like session against one server: its own cookie jar."""

    def __init__(self, base_url: str, *, timeout_s: float = 30.0, headers: Mapping[str, str] | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.http = httpx.Client(
            base_url=self.base_url,
            timeout=timeout_s,
            follow_redirects=False,
            headers=dict(headers or {}),
        )

    # --- plumbing ---------------------------------------------------------------------------

    def close(self) -> None:
        self.http.close()

    def __enter__(self) -> WeirClient:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    @property
    def cookies(self) -> httpx.Cookies:
        return self.http.cookies

    def request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        return self.http.request(method, path, **kwargs)

    def get(self, path: str, **kwargs: Any) -> httpx.Response:
        return self.http.get(path, **kwargs)

    def head(self, path: str, **kwargs: Any) -> httpx.Response:
        return self.http.head(path, **kwargs)

    def options(self, path: str, **kwargs: Any) -> httpx.Response:
        return self.http.options(path, **kwargs)

    def post(self, path: str, **kwargs: Any) -> httpx.Response:
        return self.http.post(path, **kwargs)

    def put(self, path: str, **kwargs: Any) -> httpx.Response:
        return self.http.put(path, **kwargs)

    def patch(self, path: str, **kwargs: Any) -> httpx.Response:
        return self.http.patch(path, **kwargs)

    def delete(self, path: str, **kwargs: Any) -> httpx.Response:
        return self.http.delete(path, **kwargs)

    # --- CSRF -------------------------------------------------------------------------------

    def csrf(self) -> str:
        r = self.get(f"{API}/auth/csrf")
        assert r.status_code == 200, r.text
        return str(r.json()["csrf_token"])

    def _with_csrf_body(self, json: Mapping[str, Any] | None) -> dict[str, Any]:
        body = dict(json or {})
        body.setdefault("csrf_token", self.csrf())
        return body

    def post_csrf(self, path: str, json: Mapping[str, Any] | None = None, **kwargs: Any) -> httpx.Response:
        """POST with a fresh ``csrf_token`` in the JSON body (the web app's shape)."""

        return self.post(path, json=self._with_csrf_body(json), **kwargs)

    def put_csrf(self, path: str, json: Mapping[str, Any] | None = None, **kwargs: Any) -> httpx.Response:
        return self.put(path, json=self._with_csrf_body(json), **kwargs)

    def patch_csrf(self, path: str, json: Mapping[str, Any] | None = None, **kwargs: Any) -> httpx.Response:
        return self.patch(path, json=self._with_csrf_body(json), **kwargs)

    def delete_csrf(self, path: str, **kwargs: Any) -> httpx.Response:
        """DELETE with the token in ``X-CSRF-Token`` (a DELETE has no body)."""

        headers = {"X-CSRF-Token": self.csrf(), **dict(kwargs.pop("headers", None) or {})}
        return self.delete(path, headers=headers, **kwargs)

    # --- accounts -----------------------------------------------------------------------------

    def bootstrap(self, username: str = ADMIN_USERNAME, password: str = ADMIN_PASSWORD) -> httpx.Response:
        return self.post(
            f"{API}/auth/bootstrap",
            json={"username": username, "password": password, "csrf_token": self.csrf()},
        )

    def login(
        self,
        username: str = ADMIN_USERNAME,
        password: str = ADMIN_PASSWORD,
        *,
        trusted_device: bool | None = None,
        expect: int | None = 200,
    ) -> httpx.Response:
        body: dict[str, Any] = {"username": username, "password": password, "csrf_token": self.csrf()}
        if trusted_device is not None:
            body["trusted_device"] = trusted_device
        r = self.post(f"{API}/auth/login", json=body)
        if expect is not None:
            assert r.status_code == expect, r.text
        return r

    def logout(self) -> httpx.Response:
        return self.post(f"{API}/auth/logout", headers={"X-CSRF-Token": self.csrf()})

    def ensure_admin(self, username: str = ADMIN_USERNAME, password: str = ADMIN_PASSWORD) -> None:
        """Create the first admin when the install has none, then sign in as it."""

        status = self.get(f"{API}/auth/bootstrap/status")
        assert status.status_code == 200, status.text
        if status.json().get("bootstrap_allowed"):
            r = self.bootstrap(username, password)
            assert r.status_code == 200, r.text
        self.login(username, password)
