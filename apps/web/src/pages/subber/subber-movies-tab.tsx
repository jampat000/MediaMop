import { useMemo, useState } from "react";
import { mmActionButtonClass } from "../../lib/ui/mm-control-roles";
import { subberLanguageLabel } from "../../lib/subber/subber-languages";
import type { SubberMovieRow } from "../../lib/subber/subber-api";
import {
  useSubberLibraryMoviesQuery,
  useSubberSearchAllMissingMoviesMutation,
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

function pickSearchStateId(row: SubberMovieRow, prefs: string[]): number | null {
  for (const p of prefs) {
    const lang = row.languages.find((l) => l.language_code.toLowerCase() === p.toLowerCase());
    if (lang && lang.status !== "found") return lang.state_id;
  }
  const any = row.languages.find((l) => l.status !== "found");
  return any?.state_id ?? null;
}

export function SubberMoviesTab({ canOperate }: { canOperate: boolean }) {
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
  const libQ = useSubberLibraryMoviesQuery(filters);
  const searchNow = useSubberSearchNowMutation();
  const searchAll = useSubberSearchAllMissingMoviesMutation();

  const movies = useMemo(() => {
    const m = libQ.data?.movies ?? [];
    return [...m].sort((a, b) => {
      const ta = `${a.movie_title ?? ""} ${a.movie_year ?? 0}`.toLowerCase();
      const tb = `${b.movie_title ?? ""} ${b.movie_year ?? 0}`.toLowerCase();
      return ta.localeCompare(tb);
    });
  }, [libQ.data?.movies]);

  return (
    <div className="space-y-4" data-testid="subber-movies-tab">
      <div className="flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1 text-xs text-[var(--mm-text2)]">
          Search
          <input className="mm-input min-w-[12rem]" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Title" />
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
            data-testid="subber-movies-search-all-missing"
          >
            Search all missing Movies
          </button>
        ) : null}
      </div>
      {libQ.isLoading ? <p className="text-sm text-[var(--mm-text2)]">Loading movies…</p> : null}
      {libQ.isError ? <p className="text-sm text-red-600">{(libQ.error as Error).message}</p> : null}
      {!libQ.isLoading && movies.length === 0 ? (
        <p className="text-sm text-[var(--mm-text2)]" data-testid="subber-movies-empty">
          No movies tracked yet. Subber will start tracking when Radarr imports a file or when a library scan runs.
        </p>
      ) : null}
      <ul className="space-y-2">
        {movies.map((m) => {
          const sid = pickSearchStateId(m, prefs);
          const hasMissing = m.languages.some((l) => l.status !== "found");
          return (
            <li key={m.file_path} className="rounded-lg border border-[var(--mm-border)] bg-black/10 p-3 text-sm">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-medium text-[var(--mm-text)]">
                  {m.movie_title ?? m.file_path}
                  {m.movie_year != null ? ` (${m.movie_year})` : ""}
                </span>
                <span className="flex flex-wrap gap-1">{m.languages.map((l) => langBadge(l.status, l.language_code))}</span>
                {canOperate && hasMissing && sid != null ? (
                  <button
                    type="button"
                    className={mmActionButtonClass({ variant: "secondary" })}
                    disabled={searchNow.isPending}
                    data-testid="subber-movies-search-now"
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
                    <dd className="break-all font-mono">{m.file_path}</dd>
                  </div>
                  {m.languages.map((l) => (
                    <div key={l.state_id} className="sm:col-span-2">
                      <dt className="text-[var(--mm-text2)]">{subberLanguageLabel(l.language_code)}</dt>
                      <dd>
                        {l.subtitle_path ?? "—"} · Last: {l.last_searched_at ?? "—"} · Count: {l.search_count} · Source: {l.source ?? "—"}
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
  );
}
