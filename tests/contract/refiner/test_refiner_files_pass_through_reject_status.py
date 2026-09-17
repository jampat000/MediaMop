"""Correct behaviour for #530: GET /api/v1/refiner/files must not 500 on a page containing a
``passed_through`` or ``rejected`` row, and filtering by either status must work.

On Python, ``RefinerFileOut.status`` (``schemas_refiner_files.py``) does not list ``passed_through``
or ``rejected`` even though #471 added both as file statuses, so pydantic response validation raises
and the endpoint answers 500 for any page containing one. ``file_status=passed_through`` (or
``rejected``) as a *filter* is refused for the same reason: it is outside the ``Literal``.

``tests/contract/processing/_helpers.py``'s ``file_state_after_stop`` reads SQLite directly today
because of this bug on Python; see the comment there.

.NET's ``RefinerFilesEndpoints`` (port/refiner-apis, #522) already lists both statuses and both
filter values, so this passes there.
"""

from __future__ import annotations

import pytest

from tests.contract.refiner import _helpers as h
from tests.contract.support import seed
from tests.contract.support.client import API
from tests.contract.support.launcher import ServerUnderTest

FILES = f"{API}/refiner/files"


def test_refiner_files_lists_and_filters_passed_through_and_rejected_rows(server_factory, client_factory) -> None:
    sut: ServerUnderTest = server_factory()
    # signed_in_admin must come after seed.stopped: stopping and restarting the server picks a new
    # port (ServerUnderTest.start), so a client created before the restart would be talking to a
    # port nothing is listening on any more.
    with seed.stopped(sut) as conn:
        library_id = h.first_library_id(conn)
        h.insert_file(
            conn,
            library_id=library_id,
            relative_path="PassThrough/one.mkv",
            status="passed_through",
            status_reason="Weir could not process this file, so it handed the original back unchanged.",
        )
        h.insert_file(
            conn,
            library_id=library_id,
            relative_path="Rejected/one.mkv",
            status="rejected",
            status_reason="Weir rejected this release: no retainable audio.",
        )
    admin = h.signed_in_admin(sut, client_factory)

    r = admin.get(FILES)
    assert r.status_code == 200, r.text
    statuses = {row["relative_path"]: row["status"] for row in r.json()["files"]}
    assert statuses["PassThrough/one.mkv"] == "passed_through"
    assert statuses["Rejected/one.mkv"] == "rejected"

    by_pass_through = admin.get(FILES, params={"file_status": "passed_through"})
    assert by_pass_through.status_code == 200, by_pass_through.text
    assert [f["relative_path"] for f in by_pass_through.json()["files"]] == ["PassThrough/one.mkv"]

    by_rejected = admin.get(FILES, params={"file_status": "rejected"})
    assert by_rejected.status_code == 200, by_rejected.text
    assert [f["relative_path"] for f in by_rejected.json()["files"]] == ["Rejected/one.mkv"]
