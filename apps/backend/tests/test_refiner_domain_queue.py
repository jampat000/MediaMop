"""Refiner domain: ownership vs blocking are separate; importPending ownership is not active-gated."""

from __future__ import annotations

from weir.refiner.domain import (
    RefinerQueueRowView,
    file_is_owned_by_queue,
    should_block_for_upstream,
)


def test_no_rows_not_owned_and_not_blocked() -> None:
    assert file_is_owned_by_queue(()) is False
    assert should_block_for_upstream(()) is False


def test_active_row_that_applies_owns_and_blocks() -> None:
    rows = (
        RefinerQueueRowView(
            applies_to_file=True,
            is_upstream_active=True,
            is_import_pending=False,
        ),
    )
    assert file_is_owned_by_queue(rows) is True
    assert should_block_for_upstream(rows) is True


def test_inactive_row_that_applies_owns_but_does_not_block() -> None:
    rows = (
        RefinerQueueRowView(
            applies_to_file=True,
            is_upstream_active=False,
            is_import_pending=False,
        ),
    )
    assert file_is_owned_by_queue(rows) is True
    assert should_block_for_upstream(rows) is False


def test_import_pending_row_owns_when_applies_even_if_not_upstream_active() -> None:
    """importPending counts as ownership via applies_to_file; blocking is separate."""
    rows = (
        RefinerQueueRowView(
            applies_to_file=True,
            is_upstream_active=False,
            is_import_pending=True,
        ),
    )
    assert file_is_owned_by_queue(rows) is True
    assert should_block_for_upstream(rows) is False


def test_import_pending_row_owns_and_blocks_when_upstream_active_unsuppressed() -> None:
    rows = (
        RefinerQueueRowView(
            applies_to_file=True,
            is_upstream_active=True,
            is_import_pending=True,
        ),
    )
    assert file_is_owned_by_queue(rows) is True
    assert should_block_for_upstream(rows) is True


def test_import_pending_ownership_does_not_require_upstream_active_flag() -> None:
    """Ownership never consults is_upstream_active — only applies_to_file."""
    rows = (
        RefinerQueueRowView(
            applies_to_file=True,
            is_upstream_active=False,
            is_import_pending=True,
        ),
    )
    assert file_is_owned_by_queue(rows) is True


def test_blocking_suppressed_import_wait_still_owns() -> None:
    rows = (
        RefinerQueueRowView(
            applies_to_file=True,
            is_upstream_active=True,
            is_import_pending=True,
            blocking_suppressed_for_import_wait=True,
        ),
    )
    assert file_is_owned_by_queue(rows) is True
    assert should_block_for_upstream(rows) is False


def test_mixed_rows_one_inactive_owner_one_active_blocker() -> None:
    rows = (
        RefinerQueueRowView(
            applies_to_file=True,
            is_upstream_active=False,
            is_import_pending=False,
        ),
        RefinerQueueRowView(
            applies_to_file=True,
            is_upstream_active=True,
            is_import_pending=False,
        ),
    )
    assert file_is_owned_by_queue(rows) is True
    assert should_block_for_upstream(rows) is True


def test_mixed_rows_owned_but_fully_unblocked_when_only_suppressed_actives() -> None:
    rows = (
        RefinerQueueRowView(
            applies_to_file=True,
            is_upstream_active=True,
            is_import_pending=True,
            blocking_suppressed_for_import_wait=True,
        ),
        RefinerQueueRowView(
            applies_to_file=True,
            is_upstream_active=False,
            is_import_pending=False,
        ),
    )
    assert file_is_owned_by_queue(rows) is True
    assert should_block_for_upstream(rows) is False


def test_non_applicable_rows_do_not_own_or_block() -> None:
    rows = (
        RefinerQueueRowView(
            applies_to_file=False,
            is_upstream_active=True,
            is_import_pending=True,
        ),
    )
    assert file_is_owned_by_queue(rows) is False
    assert should_block_for_upstream(rows) is False


def test_ownership_and_blocking_can_differ_explicitly() -> None:
    """Contract proof: owned != blocking in general."""
    owned_not_blocking = (
        RefinerQueueRowView(
            applies_to_file=True,
            is_upstream_active=False,
            is_import_pending=True,
        ),
    )
    assert file_is_owned_by_queue(owned_not_blocking) is True
    assert should_block_for_upstream(owned_not_blocking) is False

    not_owned = ()
    assert file_is_owned_by_queue(not_owned) is False
    assert should_block_for_upstream(not_owned) is False
