import { useEffect, useMemo, useState } from "react";
import { mmActionButtonClass } from "../../lib/ui/mm-control-roles";
import type { SubberMovieRow } from "../../lib/subber/subber-api";
import {
  useSubberLibraryMoviesQuery,
  useSubberSearchAllMissingMoviesMutation,
  useSubberSearchNowMutation,
  useSubberSettingsQuery,
} from "../../lib/subber/subber-queries";
import {
  SubberDetailsChevron,
  SubberLanguageTracksDetails,
  SubberMediaFilePathBlock,
} from "./subber-library-details";
import {
  SubberLibraryPager,
  readSubberLibraryPageSize,
  writeSubberLibraryPageSize,
  type SubberLibraryPageSize,
} from "./subber-library-pager";

function langBadge(status: string, code: string) {
  const ok = status === "found";
  return (
    <span
      key={code}
      className={`inline-flex min-w-[2.25rem] items-center justify-center rounded-full px-2 py-0.5 text-xs font-medium ${
        ok ? "bg-emerald-600/25 text-emerald-200" : "bg-red-600/25 text-red-200"
      }`}
    >
      {code.toUpperCase()}
      {ok ? " ✓" : " ✗"}
    </span>
  );
}

function pickSearchStateId(
  row: SubberMovieRow,
  prefs: string[],
): number | null {
  for (const p of prefs) {
    const lang = row.languages.find(
      (l) => l.language_code.toLowerCase() === p.toLowerCase(),
    );
    if (lang && lang.status !== "found") return lang.state_id;
  }
  const any = row.languages.find((l) => l.status !== "found");
  return any?.state_id ?? null;
}

function coverageState(row: SubberMovieRow, prefs: string[]): string {
  const preferredRows = prefs
    .map((code) =>
      row.languages.find(
        (item) => item.language_code.toLowerCase() === code.toLowerCase(),
      ),
    )
    .filter((item): item is NonNullable<typeof item> => Boolean(item));
  if (
    preferredRows.length > 0 &&
    preferredRows.every((item) => item.status === "found")
  ) {
    return "Preferred subtitle found";
  }
  return "Still missing";
}

export function SubberMoviesTab({ canOperate }: { canOperate: boolean }) {
  const settingsQ = useSubberSettingsQuery();
  const prefs = settingsQ.data?.language_preferences ?? ["en"];
  const [status, setStatus] = useState<string>("all");
  const [search, setSearch] = useState("");
  const [language, setLanguage] = useState("");
  const [pageSize, setPageSizeState] = useState<SubberLibraryPageSize>(() =>
    readSubberLibraryPageSize(),
  );
  const [page, setPage] = useState(0);

  const filters = useMemo(
    () => ({
      status: status === "all" ? undefined : status,
      search: search.trim() || undefined,
      language: language.trim() || undefined,
      limit: pageSize,
      offset: page * pageSize,
    }),
    [status, search, language, pageSize, page],
  );
  const libQ = useSubberLibraryMoviesQuery(filters);
  const searchNow = useSubberSearchNowMutation();
  const searchAll = useSubberSearchAllMissingMoviesMutation();

  const total = libQ.data?.total ?? 0;
  const movies = libQ.data?.movies ?? [];
  const hasActiveFilters =
    status !== "all" || Boolean(search.trim()) || Boolean(language.trim());

  useEffect(() => {
    setPage(0);
  }, [status, search, language]);

  useEffect(() => {
    const maxPage = Math.max(0, Math.ceil(total / pageSize) - 1);
    if (page > maxPage) {
      setPage(maxPage);
    }
  }, [total, pageSize, page]);

  const setPageSize = (n: SubberLibraryPageSize) => {
    writeSubberLibraryPageSize(n);
    setPageSizeState(n);
    setPage(0);
  };

  return (
    <div className="space-y-4" data-testid="subber-movies-tab">
      <div className="rounded-xl border border-[var(--mm-border)] bg-[var(--mm-card-bg)]/30 p-4">
        <p className="mb-3 text-xs font-medium uppercase tracking-wide text-[var(--mm-text2)]">
          Filters
        </p>
        <div className="flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1 text-xs text-[var(--mm-text2)]">
            Search
            <input
              className="mm-input min-w-[12rem]"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Title or path"
            />
          </label>
          <label className="flex flex-col gap-1 text-xs text-[var(--mm-text2)]">
            Subtitles
            <select
              className="mm-input min-w-[11rem]"
              value={status}
              onChange={(e) => setStatus(e.target.value)}
            >
              <option value="all">All titles</option>
              <option value="missing">Missing subtitles</option>
              <option value="complete">All preferred languages found</option>
            </select>
          </label>
          <label className="flex flex-col gap-1 text-xs text-[var(--mm-text2)]">
            Language code
            <input
              className="mm-input w-28"
              value={language}
              onChange={(e) => setLanguage(e.target.value)}
              placeholder="e.g. en"
            />
          </label>
          {canOperate ? (
            <button
              type="button"
              className={mmActionButtonClass({ variant: "primary" })}
              disabled={searchAll.isPending}
              onClick={() => searchAll.mutate()}
              data-testid="subber-movies-search-all-missing"
            >
              Search all missing Movies
            </button>
          ) : null}
        </div>
      </div>
      {libQ.isLoading ? (
        <p className="text-sm text-[var(--mm-text2)]">Loading movies…</p>
      ) : null}
      {libQ.isError ? (
        <p className="text-sm text-red-600">{(libQ.error as Error).message}</p>
      ) : null}
      {!libQ.isLoading && !libQ.isError && total === 0 ? (
        <p
          className="text-sm text-[var(--mm-text2)]"
          data-testid="subber-movies-empty"
        >
          {hasActiveFilters
            ? "No movies match the current filters. Try All titles or clear search."
            : "No movies are tracked yet. Open Connections and run Sync Movies library from Radarr, or wait for a new Radarr import."}
        </p>
      ) : null}
      {!libQ.isLoading && !libQ.isError && total > 0 ? (
        <SubberLibraryPager
          total={total}
          page={page}
          pageSize={pageSize}
          onPageChange={setPage}
          onPageSizeChange={setPageSize}
          itemLabel="movies"
        />
      ) : null}
      <ul className="space-y-2">
        {movies.map((m) => {
          const sid = pickSearchStateId(m, prefs);
          const hasMissing = m.languages.some((l) => l.status !== "found");
          return (
            <li
              key={m.file_path}
              className="rounded-xl border border-[var(--mm-border)] bg-[var(--mm-card-bg)]/35 p-4 text-sm shadow-sm"
            >
              <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between sm:gap-4">
                <div className="min-w-0 flex-1 space-y-2">
                  <h3 className="text-base font-semibold leading-tight text-[var(--mm-text)]">
                    {m.movie_title ?? m.file_path}
                    {m.movie_year != null ? (
                      <span className="text-[var(--mm-text2)]">
                        {" "}
                        ({m.movie_year})
                      </span>
                    ) : null}
                  </h3>
                  <p className="text-sm text-[var(--mm-text2)]">
                    {coverageState(m, prefs)}
                  </p>
                  <div className="flex flex-wrap gap-1">
                    {m.languages.map((l) =>
                      langBadge(l.status, l.language_code),
                    )}
                  </div>
                </div>
                {canOperate && hasMissing && sid != null ? (
                  <div className="flex shrink-0 sm:pt-0.5">
                    <button
                      type="button"
                      className={mmActionButtonClass({ variant: "secondary" })}
                      disabled={searchNow.isPending}
                      data-testid="subber-movies-search-now"
                      onClick={() => searchNow.mutate(sid)}
                    >
                      Search now
                    </button>
                  </div>
                ) : null}
              </div>
              <details className="group mt-3 rounded-lg border border-[var(--mm-border)] open:border-[var(--mm-accent)]/25 open:bg-black/10">
                <summary className="flex cursor-pointer list-none items-center gap-2 px-3 py-2.5 text-sm font-medium text-[var(--mm-text)] outline-none marker:hidden hover:bg-black/[0.08] [&::-webkit-details-marker]:hidden">
                  <SubberDetailsChevron />
                  Path & subtitle details
                </summary>
                <div className="space-y-4 border-t border-[var(--mm-border)] px-3 pb-4 pt-4">
                  <SubberMediaFilePathBlock path={m.file_path} />
                  <SubberLanguageTracksDetails languages={m.languages} />
                </div>
              </details>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
