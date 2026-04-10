"""Refiner Pass 2: anchor extraction and title/year ownership — contract tests (not Fetcher-style prefix rules)."""

from __future__ import annotations

from mediamop.modules.refiner.domain import (
    FileAnchorCandidate,
    RefinerQueueRowView,
    TitleYearAnchor,
    extract_title_tokens_and_year,
    extract_title_year_anchor,
    file_is_owned_by_queue,
    normalize_titleish,
    row_owns_by_title_year_anchor,
    should_block_for_upstream,
    strip_packaging_tokens,
    title_year_anchors_match,
    tokenize_normalized,
)


def test_helper_same_title_year_different_technical_token_order_matches() -> None:
    a = extract_title_year_anchor("The Towering Inferno 1974 BluRay 1080p")
    b = extract_title_year_anchor("the towering inferno 1974 1080p bluray x264 yts")
    assert a is not None and b is not None
    assert title_year_anchors_match(a, b)


def test_helper_title_year_match_with_codec_source_group_noise() -> None:
    q = extract_title_year_anchor("The Godfather 1972 WEB-DL 1080p x265-NTb")
    f = extract_title_year_anchor("The.Godfather.1972.1080p.BluRay.x264.YIFY")
    assert q is not None and f is not None
    assert title_year_anchors_match(q, f)


def test_helper_same_title_different_year_does_not_match() -> None:
    a = extract_title_year_anchor("Heat 1995 1080p")
    b = extract_title_year_anchor("Heat 1987 TV Series 1080p")  # different release/year
    assert a is not None and b is not None
    assert not title_year_anchors_match(a, b)


def test_helper_same_year_different_title_does_not_match() -> None:
    a = extract_title_year_anchor("The Conversation 1974")
    b = extract_title_year_anchor("The Parallax View 1974")
    assert a is not None and b is not None
    assert not title_year_anchors_match(a, b)


def test_helper_order_independent_title_tokens_after_strip() -> None:
    t1 = tokenize_normalized(normalize_titleish("inferno towering the 1974 1080p"))
    t2 = tokenize_normalized(normalize_titleish("the towering inferno 1974 bluray"))
    s1 = strip_packaging_tokens(t1)
    s2 = strip_packaging_tokens(t2)
    y1 = extract_title_tokens_and_year(s1, explicit_year=None)
    y2 = extract_title_tokens_and_year(s2, explicit_year=None)
    assert frozenset(y1[0]) == frozenset(y2[0]) and y1[1] == y2[1] == 1974


def test_helper_explicit_queue_year_without_year_in_title() -> None:
    row_side = extract_title_year_anchor("The Towering Inferno", explicit_year=1974)
    file_side = extract_title_year_anchor("The Towering Inferno 1974 1080p")
    assert row_side is not None and file_side is not None
    assert title_year_anchors_match(row_side, file_side)


def test_helper_no_usable_anchor_when_year_missing_on_either_side() -> None:
    incomplete = extract_title_year_anchor("Some Movie Without Year 1080p")
    assert incomplete is not None
    assert not incomplete.is_usable_for_match()


def test_row_no_queue_title_cannot_anchor_own() -> None:
    row = RefinerQueueRowView(
        applies_to_file=False,
        is_upstream_active=True,
        is_import_pending=False,
        queue_title=None,
    )
    cand = FileAnchorCandidate(title="Anything 1999")
    assert not row_owns_by_title_year_anchor(row, cand)


def test_ownership_by_explicit_path_without_candidate_ignores_queue_title() -> None:
    """Explicit applies_to_file does not require file_candidate or anchor agreement."""
    rows = (
        RefinerQueueRowView(
            applies_to_file=True,
            is_upstream_active=False,
            is_import_pending=False,
            queue_title="Completely Different 2001",
        ),
    )
    assert file_is_owned_by_queue(rows) is True
    assert (
        file_is_owned_by_queue(
            rows,
            file_candidate=FileAnchorCandidate(title="Other Title 2020"),
        )
        is True
    )


def test_ownership_by_anchor_when_not_explicit_applies() -> None:
    cand = FileAnchorCandidate(title="The Towering Inferno 1974")
    rows = (
        RefinerQueueRowView(
            applies_to_file=False,
            is_upstream_active=False,
            is_import_pending=False,
            queue_title="The Towering Inferno 1974 BluRay 1080p",
        ),
    )
    assert file_is_owned_by_queue(rows, file_candidate=cand) is True


def test_blocking_uses_same_applicability_as_ownership_with_candidate() -> None:
    """Anchor-relevant row that is inactive owns but does not block."""
    cand = FileAnchorCandidate(title="Solaris 1972 1080p")
    rows = (
        RefinerQueueRowView(
            applies_to_file=False,
            is_upstream_active=False,
            is_import_pending=False,
            queue_title="Solaris 1972 x265 WEBDL",
        ),
    )
    assert file_is_owned_by_queue(rows, file_candidate=cand) is True
    assert should_block_for_upstream(rows, file_candidate=cand) is False


def test_blocking_true_when_anchor_applies_and_upstream_active() -> None:
    cand = FileAnchorCandidate(title="Stalker 1979")
    rows = (
        RefinerQueueRowView(
            applies_to_file=False,
            is_upstream_active=True,
            is_import_pending=False,
            queue_title="Stalker 1979 1080p Bluray",
        ),
    )
    assert file_is_owned_by_queue(rows, file_candidate=cand) is True
    assert should_block_for_upstream(rows, file_candidate=cand) is True


def test_import_pending_anchor_ownership_without_blocking() -> None:
    cand = FileAnchorCandidate(title="Nashville 1975")
    rows = (
        RefinerQueueRowView(
            applies_to_file=False,
            is_upstream_active=False,
            is_import_pending=True,
            queue_title="Nashville 1975 720p HDTV",
        ),
    )
    assert file_is_owned_by_queue(rows, file_candidate=cand) is True
    assert should_block_for_upstream(rows, file_candidate=cand) is False


def test_mixed_explicit_and_anchor_rows() -> None:
    cand = FileAnchorCandidate(title="Alien 1979")
    rows = (
        RefinerQueueRowView(
            applies_to_file=True,
            is_upstream_active=False,
            is_import_pending=False,
        ),
        RefinerQueueRowView(
            applies_to_file=False,
            is_upstream_active=True,
            is_import_pending=False,
            queue_title="Alien 1979 Remux",
        ),
    )
    assert file_is_owned_by_queue(rows, file_candidate=cand) is True
    assert should_block_for_upstream(rows, file_candidate=cand) is True


def test_ownership_without_candidate_requires_explicit_applies() -> None:
    rows = (
        RefinerQueueRowView(
            applies_to_file=False,
            is_upstream_active=True,
            is_import_pending=False,
            queue_title="The Thing 1982 1080p",
        ),
    )
    assert file_is_owned_by_queue(rows) is False
    assert should_block_for_upstream(rows) is False


def test_technical_tokens_do_not_need_to_overlap_for_match() -> None:
    """Packaging stripped — extra technical tokens on one side only do not veto."""
    left = extract_title_year_anchor("Film 2000 1080p x264")
    right = extract_title_year_anchor("Film 2000 2160p HEVC AMZN")
    assert left is not None and right is not None
    assert title_year_anchors_match(left, right)
