import { useEffect, useMemo, useState } from "react";
import { mmActionButtonClass } from "../../lib/ui/mm-control-roles";
import type { SubberTvEpisode } from "../../lib/subber/subber-api";
import {
  useSubberLibraryTvQuery,
  useSubberSearchAllMissingTvMutation,
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

function pickSearchStateId(ep: SubberTvEpisode, prefs: string[]): number | null {
  for (const p of prefs) {
    const row = ep.languages.find((l) => l.language_code.toLowerCase() === p.toLowerCase());
    if (row && row.status !== "found") return row.state_id;
  }
  const any = ep.languages.find((l) => l.status !== "found");
  return any?.state_id ?? null;
}

function coverageState(ep: SubberTvEpisode, prefs: string[]): string {
  const preferredRows = prefs
    .map((code) => ep.languages.find((row) => row.language_code.toLowerCase() === code.toLowerCase()))
    .filter((row): row is NonNullable<typeof row> => Boolean(row));
  if (preferredRows.length > 0 && preferredRows.every((row) => row.status === "found")) {
    return "Preferred subtitle found";
  }
  return "Still missing";
}

export function SubberTvTab({ canOperate }: { canOperate: boolean }) {
  const settingsQ = useSubberSettingsQuery();
  const prefs = settingsQ.data?.language_preferences ?? ["en"];
  const [status, setStatus] = useState<string>("all");
  const [search, setSearch] = useState("");
  const [language, setLanguage] = useState("");
  const [pageSize, setPageSizeState] = useState<SubberLibraryPageSize>(() => readSubberLibraryPageSize());
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
  const libQ = useSubberLibraryTvQuery(filters);
  const searchNow = useSubberSearchNowMutation();
  const searchAll = useSubberSearchAllMissingTvMutation();

  const total = libQ.data?.total ?? 0;
  const hasActiveFilters = status !== "all" || Boolean(search.trim()) || Boolean(language.trim());

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
    <div className="space-y-4" data-testid="subber-tv-tab">
      <div className="rounded-xl border border-[var(--mm-border)] bg-[var(--mm-card-bg)]/30 p-4">
        <p className="mb-3 text-xs font-medium uppercase tracking-wide text-[var(--mm-text2)]">Filters</p>
        <div className="flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1 text-xs text-[var(--mm-text2)]">
            Search
            <input
              className="mm-input min-w-[12rem]"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Show, episode, or path"
            />
          </label>
          <label className="flex flex-col gap-1 text-xs text-[var(--mm-text2)]">
            Subtitles
            <select className="mm-input min-w-[11rem]" value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="all">All episodes</option>
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
              data-testid="subber-tv-search-all-missing"
            >
              Search all missing TV
            </button>
          ) : null}
        </div>
      </div>
      {libQ.isLoading ? <p className="text-sm text-[var(--mm-text2)]">Loading TV library…</p> : null}
      {libQ.isError ? <p className="text-sm text-red-600">{(libQ.error as Error).message}</p> : null}
      {!libQ.isLoading && !libQ.isError && total === 0 ? (
        <p className="text-sm text-[var(--mm-text2)]" data-testid="subber-tv-empty">
          {hasActiveFilters
            ? "No episodes match the current filters. Try All episodes or clear search."
            : "No TV episodes are tracked yet. Open Connections and run Sync TV library from Sonarr, or wait for a new Sonarr import."}
        </p>
      ) : null}
      {!libQ.isLoading && !libQ.isError && total > 0 ? (
        <SubberLibraryPager
          total={total}
          page={page}
          pageSize={pageSize}
          onPageChange={setPage}
          onPageSizeChange={setPageSize}
          itemLabel="episodes"
        />
      ) : null}
      {libQ.data?.shows.map((show) => (
        <section key={show.show_title} className="rounded-lg border border-[var(--mm-border)] bg-black/10 p-3">
          <h3 className="text-base font-semibold text-[var(--mm-text)]">{show.show_title}</h3>
          <div className="mt-2 space-y-3">
            {show.seasons.map((season) => (
              <div key={String(season.season_number)}>
                <p className="text-sm font-medium text-[var(--mm-text2)]">Season {season.season_number ?? "?"}</p>
                <ul className="mt-1 space-y-2">
                  {season.episodes.map((ep) => {
                    const sid = pickSearchStateId(ep, prefs);
                    const hasMissing = ep.languages.some((l) => l.status !== "found");
                    return (
                      <li
                        key={ep.file_path}
                        className="rounded-lg border border-[var(--mm-border)] bg-[var(--mm-card-bg)]/35 p-3 text-sm shadow-sm"
                      >
                        <div className="flex flex-col gap-2.5 sm:flex-row sm:items-start sm:justify-between sm:gap-3">
                          <div className="min-w-0 flex-1 space-y-2">
                            <h4 className="text-sm font-semibold leading-snug text-[var(--mm-text)]">
                              S{String(season.season_number ?? 0).padStart(2, "0")}E{String(ep.episode_number ?? 0).padStart(2, "0")}
                              <span className="font-normal text-[var(--mm-text2)]"> · </span>
                              {ep.episode_title ?? "Episode"}
                            </h4>
                            <p className="text-sm text-[var(--mm-text2)]">{coverageState(ep, prefs)}</p>
                            <div className="flex flex-wrap gap-1">{ep.languages.map((l) => langBadge(l.status, l.language_code))}</div>
                          </div>
                          {canOperate && hasMissing && sid != null ? (
                            <div className="flex shrink-0">
                              <button
                                type="button"
                                className={mmActionButtonClass({ variant: "secondary" })}
                                disabled={searchNow.isPending}
                                data-testid="subber-tv-search-now"
                                onClick={() => searchNow.mutate(sid)}
                              >
                                Search now
                              </button>
                            </div>
                          ) : null}
                        </div>
                        <details className="group mt-2.5 rounded-lg border border-[var(--mm-border)] open:border-[var(--mm-accent)]/25 open:bg-black/10">
                          <summary className="flex cursor-pointer list-none items-center gap-2 px-2.5 py-2 text-sm font-medium text-[var(--mm-text)] outline-none marker:hidden hover:bg-black/[0.08] [&::-webkit-details-marker]:hidden">
                            <SubberDetailsChevron />
                            Path & subtitle details
                          </summary>
                          <div className="space-y-4 border-t border-[var(--mm-border)] px-2.5 pb-3.5 pt-3.5">
                            <SubberMediaFilePathBlock path={ep.file_path} />
                            <SubberLanguageTracksDetails languages={ep.languages} />
                          </div>
                        </details>
                      </li>
                    );
                  })}
                </ul>
              </div>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
