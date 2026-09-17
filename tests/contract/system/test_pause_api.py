"""Port of the retired Python backend's tests/test_pause_api.py (the pause endpoint, ``/api/v1/pause``)."""

from __future__ import annotations

from tests.contract.support.client import API
from tests.contract.system import _helpers as h

PAUSE = f"{API}/pause"


def test_processing_starts_unpaused_and_says_what_a_pause_would_do(server_factory, client_factory) -> None:
    # A fresh install: the other tests in this module pause the module's server.
    signed_in = h.signed_in_admin(server_factory(), client_factory)
    body = signed_in.get(PAUSE).json()

    assert body["paused"] is False
    # The in-flight policy is stated up front, because the assumption otherwise is that
    # a pause stops work dead.
    assert "already running finishes" in body["in_flight_policy"]


def test_a_pause_with_an_expiry_reports_when_it_lifts(admin) -> None:
    response = admin.put_csrf(PAUSE, {"paused": True, "pause_for_minutes": 120})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["paused"] is True
    assert body["paused_until"] is not None
    assert "automatically at" in body["reason"]


def test_a_pause_with_no_expiry_says_so_rather_than_implying_one(admin) -> None:
    body = admin.put_csrf(PAUSE, {"paused": True}).json()

    assert body["paused"] is True
    assert body["paused_until"] is None
    assert "when you resume it" in body["reason"]


def test_resuming_clears_the_expiry(admin) -> None:
    admin.put_csrf(PAUSE, {"paused": True, "pause_for_minutes": 30})

    body = admin.put_csrf(PAUSE, {"paused": False}).json()

    assert body["paused"] is False
    assert body["paused_until"] is None


def test_scan_while_paused_can_be_turned_off(admin) -> None:
    body = admin.put_csrf(PAUSE, {"paused": True, "scan_while_paused": False}).json()

    assert body["scan_while_paused"] is False


def test_a_pause_change_without_a_csrf_token_is_refused(admin) -> None:
    response = admin.put(PAUSE, json={"paused": True, "scan_while_paused": True})

    assert response.status_code == 422


def test_an_out_of_range_duration_is_refused(admin) -> None:
    response = admin.put_csrf(PAUSE, {"paused": True, "pause_for_minutes": 0})

    assert response.status_code == 422
