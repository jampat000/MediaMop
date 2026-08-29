"""Seeding Refiner libraries in tests, now that the singleton settings tables are gone.

Before #363 a test seeded ``refiner_path_settings`` with a Movies and a TV set of paths.
The libraries are the only store now, so this does the same job against the table that
actually holds them — and it seeds *both* scopes by default, because the singleton always
had both and a test that quietly only covered Movies would be a weaker test than the one
it replaced.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from mediamop.modules.refiner.refiner_library_model import RefinerLibraryRow


def seed_refiner_library(
    session: Session,
    *,
    media_scope: str = "movie",
    name: str | None = None,
    watched_folder: str = "",
    work_folder: str = "",
    output_folder: str = "",
    display_order: int | None = None,
    **overrides: object,
) -> RefinerLibraryRow:
    """One library, replacing the scope's row if a test already seeded one.

    ``merge``-like by scope rather than by id, because tests used to ``merge`` the
    singleton at ``id=1`` and calling this twice for the same scope should mean "set these
    paths", not "add a second library that shadows the first".
    """

    existing = session.scalars(
        select(RefinerLibraryRow).where(RefinerLibraryRow.media_scope == media_scope).order_by(RefinerLibraryRow.id)
    ).first()
    row = existing or RefinerLibraryRow(
        name=name or ("TV" if media_scope == "tv" else "Movies"),
        media_scope=media_scope,
    )
    row.enabled = True
    row.watched_folder = watched_folder
    row.work_folder = work_folder
    row.output_folder = output_folder
    if name is not None:
        row.name = name
    if display_order is not None:
        row.display_order = display_order
    for key, value in overrides.items():
        setattr(row, key, value)
    if existing is None:
        session.add(row)
    session.flush()
    return row


def seed_refiner_libraries(
    session: Session,
    *,
    watched_folder: str = "",
    work_folder: str = "",
    output_folder: str = "",
    tv_watched_folder: str = "",
    tv_work_folder: str = "",
    tv_output_folder: str = "",
    **overrides: object,
) -> tuple[RefinerLibraryRow, RefinerLibraryRow]:
    """Movies and TV together, the way the singleton row used to hold both."""

    movies = seed_refiner_library(
        session,
        media_scope="movie",
        watched_folder=watched_folder,
        work_folder=work_folder,
        output_folder=output_folder,
        display_order=1,
        **overrides,
    )
    tv = seed_refiner_library(
        session,
        media_scope="tv",
        watched_folder=tv_watched_folder,
        work_folder=tv_work_folder,
        output_folder=tv_output_folder,
        display_order=2,
        **overrides,
    )
    return movies, tv
