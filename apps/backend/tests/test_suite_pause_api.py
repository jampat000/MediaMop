"""The pause endpoint — ``/api/v1/suite/pause``.

Pause is on the suite rather than on Refiner so Pruner can honour the same switch later
instead of a second one appearing beside it (#337).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.integration_helpers import auth_get, auth_post, auth_put, csrf


@pytest.fixture
def signed_in(client_with_admin: TestClient) -> TestClient:
    token = csrf(client_with_admin)
    response = auth_post(
        client_with_admin,
        "/api/v1/auth/login",
        json={"username": "alice", "password": "test-password-strong", "csrf_token": token},
    )
    assert response.status_code == 200, response.text
    return client_with_admin


def test_processing_starts_unpaused_and_says_what_a_pause_would_do(signed_in: TestClient) -> None:
    body = auth_get(signed_in, "/api/v1/suite/pause").json()

    assert body["paused"] is False
    # The in-flight policy is stated up front, because the assumption otherwise is that
    # a pause stops work dead.
    assert "already running finishes" in body["in_flight_policy"]


def test_a_pause_with_an_expiry_reports_when_it_lifts(signed_in: TestClient) -> None:
    response = auth_put(
        signed_in,
        "/api/v1/suite/pause",
        json={"csrf_token": csrf(signed_in), "paused": True, "pause_for_minutes": 120},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["paused"] is True
    assert body["paused_until"] is not None
    assert "automatically at" in body["reason"]


def test_a_pause_with_no_expiry_says_so_rather_than_implying_one(signed_in: TestClient) -> None:
    body = auth_put(
        signed_in,
        "/api/v1/suite/pause",
        json={"csrf_token": csrf(signed_in), "paused": True},
    ).json()

    assert body["paused"] is True
    assert body["paused_until"] is None
    assert "when you resume it" in body["reason"]


def test_resuming_clears_the_expiry(signed_in: TestClient) -> None:
    auth_put(
        signed_in,
        "/api/v1/suite/pause",
        json={"csrf_token": csrf(signed_in), "paused": True, "pause_for_minutes": 30},
    )

    body = auth_put(
        signed_in,
        "/api/v1/suite/pause",
        json={"csrf_token": csrf(signed_in), "paused": False},
    ).json()

    assert body["paused"] is False
    assert body["paused_until"] is None


def test_scan_while_paused_can_be_turned_off(signed_in: TestClient) -> None:
    body = auth_put(
        signed_in,
        "/api/v1/suite/pause",
        json={
            "csrf_token": csrf(signed_in),
            "paused": True,
            "scan_while_paused": False,
        },
    ).json()

    assert body["scan_while_paused"] is False


def test_a_pause_change_without_a_csrf_token_is_refused(signed_in: TestClient) -> None:
    response = auth_put(signed_in, "/api/v1/suite/pause", json={"paused": True, "scan_while_paused": True})

    assert response.status_code == 422


def test_an_out_of_range_duration_is_refused(signed_in: TestClient) -> None:
    response = auth_put(
        signed_in,
        "/api/v1/suite/pause",
        json={
            "csrf_token": csrf(signed_in),
            "paused": True,
            "pause_for_minutes": 0,
        },
    )

    assert response.status_code == 422
