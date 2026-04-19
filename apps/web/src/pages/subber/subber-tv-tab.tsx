import { useMemo, useState } from "react";
import { mmActionButtonClass } from "../../lib/ui/mm-control-roles";
import { subberLanguageLabel } from "../../lib/subber/subber-languages";
import type { SubberTvEpisode } from "../../lib/subber/subber-api";
import {
  useSubberLibraryTvQuery,
  useSubberSearchAllMissingTvMutation,
  useSubberSearchNowMutation,
  useSubberSettingsQuery,
} from "../../lib/subber/subber-queries";

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

function subberProviderLabel(key: string | null | undefined): string {
  if (!key) return "—";
  const labels: Record<string, string> = {
    opensubtitles_org: "OpenSubtitles.org",
    opensubtitles_com: "OpenSubtitles.com",
    podnapisi: "Podnapisi",
    subscene: "Subscene",
    addic7ed: "Addic7ed",
  };
  return labels[key] ?? key;
}

function pickSearchStateId(ep: SubberTvEpisode, prefs: string[]): number | null {
  for (const p of prefs) {
    const row = ep.languages.find((l) => l.language_code.toLowerCase() === p.toLowerCase());
    if (row && row.status !== "found") return row.state_id;
  }
  const any = ep.languages.find((l) => l.status !== "found");
  return any?.state_id ?? null;
}

export function SubberTvTab({ canOperate }: { canOperate: boolean }) {
  const settingsQ = useSubberSettingsQuery();
  const prefs = settingsQ.data?.language_preferences ?? ["en"];
  const [status, setStatus] = useState<string>("all");
  const [search, setSearch] = useState("");
  const [language, setLanguage] = useState("");
  const filters = useMemo(
    () => ({
      status: status === "all" ? undefined : status,
      search: search.trim() || undefined,
      language: language.trim() || undefined,
    }),
    [status, search, language],
  );
  const libQ = useSubberLibraryTvQuery(filters);
  const searchNow = useSubberSearchNowMutation();
  const searchAll = useSubberSearchAllMissingTvMutation();

  return (
    <div className="space-y-4" data-testid="subber-tv-tab">
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
          Status
          <select className="mm-input" value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="all">All</option>
            <option value="missing">Missing</option>
            <option value="complete">Complete</option>
          </select>
        </label>
        <label className="flex flex-col gap-1 text-xs text-[var(--mm-text2)]">
          Language
          <input className="mm-input w-28" value={language} onChange={(e) => setLanguage(e.target.value)} placeholder="ISO code" />
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
      {libQ.isLoading ? <p className="text-sm text-[var(--mm-text2)]">Loading TV library…</p> : null}
      {libQ.isError ? <p className="text-sm text-red-600">{(libQ.error as Error).message}</p> : null}
      {libQ.data && !libQ.data.shows.length ? (
        <p className="text-sm text-[var(--mm-text2)]" data-testid="subber-tv-empty">
          No TV episodes tracked yet. Go to Settings and use the Sync TV library button to import your Sonarr library, or Subber will populate this automatically when Sonarr imports a new file.
        </p>
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
                      <li key={ep.file_path} className="rounded border border-[var(--mm-border)] bg-black/10 p-2 text-sm">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="text-[var(--mm-text)]">
                            S{String(season.season_number ?? 0).padStart(2, "0")}E{String(ep.episode_number ?? 0).padStart(2, "0")} ·{" "}
                            {ep.episode_title ?? "Episode"}
                          </span>
                          <span className="flex flex-wrap gap-1">
                            {ep.languages.map((l) => langBadge(l.status, l.language_code))}
                          </span>
                          {canOperate && hasMissing && sid != null ? (
                            <button
                              type="button"
                              className={mmActionButtonClass({ variant: "secondary" })}
                              disabled={searchNow.isPending}
                              data-testid="subber-tv-search-now"
                              onClick={() => searchNow.mutate(sid)}
                            >
                              Search now
                            </button>
                          ) : null}
                        </div>
                        <details className="mt-2 text-xs text-[var(--mm-text2)]">
                          <summary className="cursor-pointer text-[var(--mm-text)]">Details</summary>
                          <dl className="mt-2 grid gap-1 sm:grid-cols-2">
                            <div>
                              <dt className="text-[var(--mm-text2)]">File</dt>
                              <dd className="break-all font-mono">{ep.file_path}</dd>
                            </div>
                            <div>
                              <dt className="text-[var(--mm-text2)]">Subtitle paths</dt>
                              <dd className="break-all">
                                {ep.languages
                                  .map((l) => l.subtitle_path)
                                  .filter(Boolean)
                                  .join(" · ") || "—"}
                              </dd>
                            </div>
                            {ep.languages.map((l) => (
                              <div key={l.state_id} className="sm:col-span-2">
                                <dt className="text-[var(--mm-text2)]">
                                  {subberLanguageLabel(l.language_code)} ({l.language_code})
                                </dt>
                                <dd>
                                  Last searched: {l.last_searched_at ?? "—"} · Count: {l.search_count} · Source: {l.source ?? "—"}
                                  <br />
                                  Found via: {subberProviderLabel(l.provider_key)} · Upgraded:{" "}
                                  {(l.upgrade_count ?? 0) > 0 ? `${l.upgrade_count} times` : "Never upgraded"}
                                </dd>
                              </div>
                            ))}
                          </dl>
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
