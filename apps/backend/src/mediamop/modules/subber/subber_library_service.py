"""Group subtitle state rows for TV / Movies library APIs."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence

from mediamop.modules.subber.subber_schemas import (
    SubberMovieRowOut,
    SubberMoviesLibraryOut,
    SubberSubtitleLangStateOut,
    SubberTvEpisodeOut,
    SubberTvLibraryOut,
    SubberTvSeasonOut,
    SubberTvShowOut,
)
from mediamop.modules.subber.subber_subtitle_state_model import SubberSubtitleState


def _norm(s: str | None) -> str:
    return (s or "").strip().lower()


def _matches_search(rows: Sequence[SubberSubtitleState], q: str) -> bool:
    if not q:
        return True
    qn = q.strip().lower()
    for r in rows:
        for fld in (r.show_title, r.episode_title, r.file_path, r.movie_title):
            if fld and qn in str(fld).lower():
                return True
    return False


def _lang_states(rows: Sequence[SubberSubtitleState], lang_filter: str | None) -> list[SubberSubtitleState]:
    if not lang_filter:
        return list(rows)
    lf = lang_filter.strip().lower()
    return [r for r in rows if r.language_code.lower() == lf]


def _episode_status_filter(rows: Sequence[SubberSubtitleState], status: str | None, prefs: list[str]) -> bool:
    if not status or status == "all":
        return True
    langs = {r.language_code.lower(): r.status for r in rows}
    if status == "missing":
        return any(langs.get(p, "missing") in ("missing", "searching") for p in prefs) or any(
            langs.get(p) is None for p in prefs
        )
    if status == "complete":
        return all(langs.get(p) == "found" for p in prefs)
    return True


def build_tv_library(
    rows: Sequence[SubberSubtitleState],
    *,
    prefs: list[str],
    status: str | None,
    search: str | None,
    lang_filter: str | None,
) -> SubberTvLibraryOut:
    by_file: dict[str, list[SubberSubtitleState]] = defaultdict(list)
    for r in rows:
        if r.media_scope != "tv":
            continue
        by_file[r.file_path].append(r)

    shows: dict[str, dict[int | None, list[SubberTvEpisodeOut]]] = defaultdict(lambda: defaultdict(list))
    for _fp, grp in sorted(by_file.items(), key=lambda kv: kv[0]):
        if not _matches_search(grp, search or ""):
            continue
        if not _episode_status_filter(grp, status, prefs):
            continue
        g0 = grp[0]
        show = g0.show_title or "Unknown show"
        season = g0.season_number
        lang_rows = _lang_states(grp, lang_filter)
        langs_out = [
            SubberSubtitleLangStateOut(
                state_id=int(x.id),
                language_code=x.language_code,
                status=x.status,
                subtitle_path=x.subtitle_path,
                last_searched_at=x.last_searched_at,
                search_count=int(x.search_count or 0),
                source=x.source,
            )
            for x in sorted(lang_rows, key=lambda z: z.language_code)
        ]
        if not langs_out:
            continue
        ep = SubberTvEpisodeOut(
            file_path=g0.file_path,
            episode_number=g0.episode_number,
            episode_title=g0.episode_title,
            languages=langs_out,
        )
        shows[show][season].append(ep)

    show_out: list[SubberTvShowOut] = []
    for show_title in sorted(shows.keys(), key=lambda s: s.lower()):
        seasons_map = shows[show_title]
        seasons: list[SubberTvSeasonOut] = []
        for sn in sorted(seasons_map.keys(), key=lambda x: (x is None, x or -1)):
            eps = sorted(
                seasons_map[sn],
                key=lambda e: (e.episode_number is None, e.episode_number or -1, e.file_path),
            )
            seasons.append(SubberTvSeasonOut(season_number=sn, episodes=eps))
        show_out.append(SubberTvShowOut(show_title=show_title, seasons=seasons))
    return SubberTvLibraryOut(shows=show_out)


def build_movies_library(
    rows: Sequence[SubberSubtitleState],
    *,
    prefs: list[str],
    status: str | None,
    search: str | None,
    lang_filter: str | None,
) -> SubberMoviesLibraryOut:
    by_file: dict[str, list[SubberSubtitleState]] = defaultdict(list)
    for r in rows:
        if r.media_scope != "movies":
            continue
        by_file[r.file_path].append(r)
    out: list[SubberMovieRowOut] = []
    for fp in sorted(by_file.keys(), key=lambda p: p.lower()):
        grp = by_file[fp]
        if not _matches_search(grp, search or ""):
            continue
        if not _episode_status_filter(grp, status, prefs):
            continue
        g0 = grp[0]
        lang_rows = _lang_states(grp, lang_filter)
        langs_out = [
            SubberSubtitleLangStateOut(
                state_id=int(x.id),
                language_code=x.language_code,
                status=x.status,
                subtitle_path=x.subtitle_path,
                last_searched_at=x.last_searched_at,
                search_count=int(x.search_count or 0),
                source=x.source,
            )
            for x in sorted(lang_rows, key=lambda z: z.language_code)
        ]
        if not langs_out:
            continue
        title_key = (g0.movie_title or fp).lower()
        out.append(
            SubberMovieRowOut(
                file_path=fp,
                movie_title=g0.movie_title,
                movie_year=g0.movie_year,
                languages=langs_out,
            ),
        )
    out.sort(key=lambda m: (m.movie_title or m.file_path).lower())
    return SubberMoviesLibraryOut(movies=out)
