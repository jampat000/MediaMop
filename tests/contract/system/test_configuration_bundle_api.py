"""Port of apps/backend/tests/test_configuration_bundle_api.py."""

from __future__ import annotations

from copy import deepcopy

import pytest

from tests.contract.support.client import API
from tests.contract.system import _helpers as h

BUNDLE = f"{API}/system/suite-configuration-bundle"


@pytest.fixture(scope="module", autouse=True)
def _users(server) -> None:
    h.seed_users(server)


def test_configuration_bundle_get_requires_operator(server, client_factory) -> None:
    viewer = h.signed_in_viewer(server, client_factory)
    r = viewer.get(BUNDLE)
    assert r.status_code == 403


def test_configuration_bundle_get_legacy_path_still_works(admin) -> None:
    r = admin.get(f"{API}/suite/configuration-bundle")
    assert r.status_code == 200, r.text
    assert r.json()["format_version"] == 4


def test_configuration_bundle_round_trip_suite_name(admin) -> None:
    r0 = admin.get(BUNDLE)
    assert r0.status_code == 200, r0.text
    bundle = r0.json()
    assert bundle["format_version"] == 4
    assert "suite_settings" in bundle
    assert "arr_library_operator_settings" in bundle

    b2 = deepcopy(bundle)
    b2["suite_settings"] = dict(bundle["suite_settings"])
    b2["suite_settings"]["product_display_name"] = "Bundle Restore Test"

    r_put = admin.put_csrf(BUNDLE, {"bundle": b2})
    assert r_put.status_code == 200, r_put.text
    assert r_put.json()["suite_settings"]["product_display_name"] == "Bundle Restore Test"

    r_restore = admin.put_csrf(BUNDLE, {"bundle": bundle})
    assert r_restore.status_code == 200, r_restore.text
    assert (
        r_restore.json()["suite_settings"]["product_display_name"] == bundle["suite_settings"]["product_display_name"]
    )


def test_configuration_bundle_no_longer_carries_pruner_and_ignores_it_on_restore(admin) -> None:
    """Pruner moved to Deluno (#473): exports drop its sections, older backups still restore."""

    r0 = admin.get(BUNDLE)
    assert r0.status_code == 200, r0.text
    bundle = r0.json()
    assert not any(key.startswith("pruner_") for key in bundle)

    older = deepcopy(bundle)
    older["suite_settings"] = dict(bundle["suite_settings"])
    older["suite_settings"]["product_display_name"] = "Restored From Older Backup"
    older["pruner_server_instances"] = [{"id": 1, "provider": "plex", "display_name": "Living room"}]
    older["pruner_scope_settings"] = [{"id": 1, "server_instance_id": 1, "media_scope": "movies"}]

    r_put = admin.put_csrf(BUNDLE, {"bundle": older})
    assert r_put.status_code == 200, r_put.text
    assert r_put.json()["suite_settings"]["product_display_name"] == "Restored From Older Backup"

    r_restore = admin.put_csrf(BUNDLE, {"bundle": bundle})
    assert r_restore.status_code == 200, r_restore.text


def test_configuration_bundle_put_rejects_bad_version(admin) -> None:
    r0 = admin.get(BUNDLE)
    assert r0.status_code == 200
    bundle = r0.json()
    bundle["format_version"] = 999
    r_put = admin.put_csrf(BUNDLE, {"bundle": bundle})
    assert r_put.status_code == 400


def test_configuration_backup_list_shape(admin) -> None:
    r = admin.get(f"{API}/system/suite-configuration-backups")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "directory" in body
    assert isinstance(body["items"], list)
