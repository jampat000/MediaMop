import { useEffect, useMemo, useState } from "react";
import { mmActionButtonClass } from "../../lib/ui/mm-control-roles";
import type {
  SubberSubtitleLangState,
  SubberTvEpisode,
  SubberTvSeason,
  SubberTvShow,
} from "../../lib/subber/subber-api";
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

type CoverageCounts = {
  complete: number;
  missing: number;
  total: number;
};

function langBadge(lang: SubberSubtitleLangState) {
  const ok = lang.status === "found";
  return (
    <span
      key={lang.state_id}
      title={`${lang.language_code.toUpperCase()} ${
        ok ? "subtitle found" : "subtitle missing"
      }`}
      className={`inline-flex min-w-[3rem] items-center justify-center rounded-full border px-2 py-0.5 text-[0.7rem] font-semibold ${
        ok
          ? "border-emerald-400/30 bg-emerald-600/20 text-emerald-100"
          : "border-red-400/35 bg-red-600/20 text-red-100"
      }`}
    >
      {lang.language_code.toUpperCase()}
      <span className="ml-1 text-[0.6rem] uppercase">{ok ? "ok" : "miss"}</span>
    </span>
  );
}

function pickSearchStateId(
  ep: SubberTvEpisode,
  prefs: string[],
): number | null {
  for (const p of prefs) {
    const row = ep.languages.find(
      (l) => l.language_code.toLowerCase() === p.toLowerCase(),
    );
    if (row && row.status !== "found") return row.state_id;
  }
  const any = ep.languages.find((l) => l.status !== "found");
  return any?.state_id ?? null;
}

function preferredLanguageRows(
  ep: SubberTvEpisode,
  prefs: string[],
): SubberSubtitleLangState[] {
  return prefs
    .map((code) =>
      ep.languages.find(
        (row) => row.language_code.toLowerCase() === code.toLowerCase(),
      ),
    )
    .filter((row): row is SubberSubtitleLangState => Boolean(row));
}

function hasPreferredCoverage(ep: SubberTvEpisode, prefs: string[]): boolean {
  const preferredRows = preferredLanguageRows(ep, prefs);
  return (
    preferredRows.length > 0 &&
    preferredRows.every((row) => row.status === "found")
  );
}

function countCoverage(
  episodes: SubberTvEpisode[],
  prefs: string[],
): CoverageCounts {
  const complete = episodes.filter((ep) =>
    hasPreferredCoverage(ep, prefs),
  ).length;
  return {
    complete,
    missing: episodes.length - complete,
    total: episodes.length,
  };
}

function showEpisodes(show: SubberTvShow): SubberTvEpisode[] {
  return show.seasons.flatMap((season) => season.episodes);
}

function formatEpisodeCode(
  season: SubberTvSeason,
  ep: SubberTvEpisode,
): string {
  return `S${String(season.season_number ?? 0).padStart(2, "0")}E${String(
    ep.episode_number ?? 0,
  ).padStart(2, "0")}`;
}

function CoverageMeter({ counts }: { counts: CoverageCounts }) {
  const completePercent =
    counts.total > 0 ? Math.round((counts.complete / counts.total) * 100) : 0;
  return (
    <div className="min-w-[9rem]">
      <div className="flex items-center justify-between gap-3 text-xs text-[var(--mm-text2)]">
        <span>{completePercent}% covered</span>
        <span>
          {counts.complete}/{counts.total}
        </span>
      </div>
      <div className="mt-1.5 h-2 overflow-hidden rounded-full bg-red-950/45">
        <div
          className="h-full rounded-full bg-emerald-400/80"
          style={{ width: `${completePercent}%` }}
        />
      </div>
    </div>
  );
}

function CoverageSummaryPill({
  tone,
  label,
  value,
}: {
  tone: "good" | "warn" | "neutral";
  label: string;
  value: number;
}) {
  const toneClass =
    tone === "good"
      ? "border-emerald-400/30 bg-emerald-500/10 text-emerald-100"
      : tone === "warn"
        ? "border-red-400/30 bg-red-500/10 text-red-100"
        : "border-[var(--mm-border)] bg-black/15 text-[var(--mm-text)]";
  return (
    <span
      className={`inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-medium ${toneClass}`}
    >
      <span className="text-sm font-semibold">{value}</span>
      {label}
    </span>
  );
}

function EpisodeStatusPill({ complete }: { complete: boolean }) {
  return (
    <span
      className={`inline-flex w-fit items-center rounded-full border px-2.5 py-1 text-xs font-semibold ${
        complete
          ? "border-emerald-400/30 bg-emerald-500/10 text-emerald-100"
          : "border-red-400/35 bg-red-500/10 text-red-100"
      }`}
    >
      {complete ? "Complete" : "Needs subtitles"}
    </span>
  );
}

function EpisodeSubtitleSummary({
  ep,
  prefs,
}: {
  ep: SubberTvEpisode;
  prefs: string[];
}) {
  const preferredRows = preferredLanguageRows(ep, prefs);
  const visibleRows = preferredRows.length > 0 ? preferredRows : ep.languages;
  const missingPreferred = visibleRows.filter((row) => row.status !== "found");
  return (
    <div className="space-y-1.5">
      <p className="text-xs text-[var(--mm-text2)]">
        {missingPreferred.length > 0
          ? `Missing ${missingPreferred
              .map((row) => row.language_code.toUpperCase())
              .join(", ")}`
          : "Preferred subtitles found"}
      </p>
      <div className="flex flex-wrap gap-1.5">
        {visibleRows.map((lang) => langBadge(lang))}
      </div>
    </div>
  );
}

export function SubberTvTab({ canOperate }: { canOperate: boolean }) {
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
  const libQ = useSubberLibraryTvQuery(filters);
  const searchNow = useSubberSearchNowMutation();
  const searchAll = useSubberSearchAllMissingTvMutation();

  const total = libQ.data?.total ?? 0;
  const visibleEpisodes = useMemo(
    () => (libQ.data?.shows ?? []).flatMap(showEpisodes),
    [libQ.data?.shows],
  );
  const visibleCounts = countCoverage(visibleEpisodes, prefs);
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
    <div className="space-y-4" data-testid="subber-tv-tab">
      <div className="rounded-xl border border-[var(--mm-border)] bg-[var(--mm-card-bg)]/30 p-4">
        <div className="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
          <div>
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
                  placeholder="Show, episode, or path"
                />
              </label>
              <label className="flex flex-col gap-1 text-xs text-[var(--mm-text2)]">
                Subtitles
                <select
                  className="mm-input min-w-[11rem]"
                  value={status}
                  onChange={(e) => setStatus(e.target.value)}
                >
                  <option value="all">All episodes</option>
                  <option value="missing">Missing subtitles</option>
                  <option value="complete">
                    All preferred languages found
                  </option>
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
          {total > 0 ? (
            <div className="flex flex-wrap gap-2 xl:justify-end">
              <CoverageSummaryPill
                tone="neutral"
                label="shown"
                value={visibleCounts.total}
              />
              <CoverageSummaryPill
                tone="good"
                label="complete"
                value={visibleCounts.complete}
              />
              <CoverageSummaryPill
                tone="warn"
                label="need subtitles"
                value={visibleCounts.missing}
              />
            </div>
          ) : null}
        </div>
      </div>
      {libQ.isLoading ? (
        <p className="text-sm text-[var(--mm-text2)]">Loading TV library...</p>
      ) : null}
      {libQ.isError ? (
        <p className="text-sm text-red-600">{(libQ.error as Error).message}</p>
      ) : null}
      {!libQ.isLoading && !libQ.isError && total === 0 ? (
        <p
          className="text-sm text-[var(--mm-text2)]"
          data-testid="subber-tv-empty"
        >
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
      <div className="space-y-3">
        {libQ.data?.shows.map((show) => {
          const showCounts = countCoverage(showEpisodes(show), prefs);
          return (
            <section
              key={show.show_title}
              className="overflow-hidden rounded-xl border border-[var(--mm-border)] bg-[var(--mm-card-bg)]/35 shadow-sm"
            >
              <header className="flex flex-col gap-3 border-b border-[var(--mm-border)] bg-black/15 px-4 py-3 lg:flex-row lg:items-center lg:justify-between">
                <div className="min-w-0">
                  <h3 className="truncate text-lg font-semibold leading-tight text-[var(--mm-text)]">
                    {show.show_title}
                  </h3>
                  <p className="mt-1 text-sm text-[var(--mm-text2)]">
                    {showCounts.missing > 0
                      ? `${showCounts.missing} episode${
                          showCounts.missing === 1 ? "" : "s"
                        } still ${
                          showCounts.missing === 1 ? "needs" : "need"
                        } subtitles`
                      : "All shown episodes have preferred subtitles"}
                  </p>
                </div>
                <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
                  <div className="flex flex-wrap gap-2">
                    <CoverageSummaryPill
                      tone="neutral"
                      label="episodes"
                      value={showCounts.total}
                    />
                    <CoverageSummaryPill
                      tone="warn"
                      label="missing"
                      value={showCounts.missing}
                    />
                  </div>
                  <CoverageMeter counts={showCounts} />
                </div>
              </header>
              <div className="divide-y divide-[var(--mm-border)]">
                {show.seasons.map((season) => {
                  const seasonCounts = countCoverage(season.episodes, prefs);
                  return (
                    <section key={String(season.season_number)} className="p-4">
                      <div className="mb-2.5 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                        <div>
                          <h4 className="text-sm font-semibold text-[var(--mm-text)]">
                            Season {season.season_number ?? "?"}
                          </h4>
                          <p className="text-xs text-[var(--mm-text2)]">
                            {seasonCounts.missing > 0
                              ? `${seasonCounts.missing} missing, ${seasonCounts.complete} complete`
                              : "Season complete"}
                          </p>
                        </div>
                        <CoverageMeter counts={seasonCounts} />
                      </div>
                      <ul className="rounded-lg border border-[var(--mm-border)]">
                        {season.episodes.map((ep) => {
                          const sid = pickSearchStateId(ep, prefs);
                          const complete = hasPreferredCoverage(ep, prefs);
                          const hasMissing = ep.languages.some(
                            (l) => l.status !== "found",
                          );
                          return (
                            <li
                              key={ep.file_path}
                              className={`border-b border-[var(--mm-border)] bg-black/10 last:border-b-0 ${
                                complete
                                  ? "border-l-4 border-l-emerald-400/70"
                                  : "border-l-4 border-l-red-400/70"
                              }`}
                            >
                              <div className="grid gap-3 px-3 py-3 md:grid-cols-[minmax(15rem,1fr)_minmax(12rem,18rem)_auto] md:items-center">
                                <div className="min-w-0">
                                  <div className="flex flex-wrap items-center gap-2">
                                    <span className="rounded-md bg-black/25 px-2 py-1 font-mono text-xs font-semibold text-[var(--mm-text)]">
                                      {formatEpisodeCode(season, ep)}
                                    </span>
                                    <EpisodeStatusPill complete={complete} />
                                  </div>
                                  <p className="mt-2 truncate text-sm font-semibold text-[var(--mm-text)]">
                                    {ep.episode_title ?? "Episode"}
                                  </p>
                                </div>
                                <EpisodeSubtitleSummary ep={ep} prefs={prefs} />
                                <div className="flex items-center md:justify-end">
                                  {canOperate && hasMissing && sid != null ? (
                                    <button
                                      type="button"
                                      className={mmActionButtonClass({
                                        variant: "secondary",
                                      })}
                                      disabled={searchNow.isPending}
                                      data-testid="subber-tv-search-now"
                                      onClick={() => searchNow.mutate(sid)}
                                    >
                                      Search now
                                    </button>
                                  ) : null}
                                </div>
                                <details className="group md:col-span-3">
                                  <summary className="flex w-fit cursor-pointer list-none items-center gap-1.5 rounded-md border border-[var(--mm-border)] px-2.5 py-2 text-xs font-medium text-[var(--mm-text)] outline-none marker:hidden hover:bg-black/[0.12] [&::-webkit-details-marker]:hidden">
                                    <SubberDetailsChevron />
                                    Path, provider, and search details
                                  </summary>
                                  <div className="mt-3 space-y-4 rounded-lg border border-[var(--mm-border)] bg-[var(--mm-card-bg)] p-3">
                                    <SubberMediaFilePathBlock
                                      path={ep.file_path}
                                    />
                                    <SubberLanguageTracksDetails
                                      languages={ep.languages}
                                    />
                                  </div>
                                </details>
                              </div>
                            </li>
                          );
                        })}
                      </ul>
                    </section>
                  );
                })}
              </div>
            </section>
          );
        })}
      </div>
    </div>
  );
}
