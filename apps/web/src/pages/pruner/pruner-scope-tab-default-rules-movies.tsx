import type { PrunerServerInstance } from "../../lib/pruner/api";

type ScopeRow = PrunerServerInstance["scopes"][number] | undefined;

type PrunerScopeTabDefaultRulesMoviesProps = {
  scope: "tv" | "movies";
  isPlex: boolean;
  busy: boolean;
  showInteractiveControls: boolean;
  scopeRow: ScopeRow;
  watchedMoviesEnabled: boolean;
  setWatchedMoviesEnabled: (value: boolean) => void;
  watchedMoviesMsg: string | null;
  saveWatchedMoviesSettings: () => Promise<void>;
  runWatchedMoviesPreview: () => Promise<void>;
  lowRatingEnabled: boolean;
  setLowRatingEnabled: (value: boolean) => void;
  lowRatingMax: string;
  setLowRatingMax: (value: string) => void;
  lowRatingMsg: string | null;
  saveLowRatingMovieSettings: () => Promise<void>;
  runLowRatingMoviesPreview: () => Promise<void>;
  unwatchedStaleEnabled: boolean;
  setUnwatchedStaleEnabled: (value: boolean) => void;
  unwatchedStaleDays: number;
  setUnwatchedStaleDays: (value: number) => void;
  unwatchedStaleMsg: string | null;
  saveUnwatchedStaleMovieSettings: () => Promise<void>;
  runUnwatchedStaleMoviesPreview: () => Promise<void>;
};

export function PrunerScopeTabDefaultRulesMovies({
  scope,
  isPlex,
  busy,
  showInteractiveControls,
  scopeRow,
  watchedMoviesEnabled,
  setWatchedMoviesEnabled,
  watchedMoviesMsg,
  saveWatchedMoviesSettings,
  runWatchedMoviesPreview,
  lowRatingEnabled,
  setLowRatingEnabled,
  lowRatingMax,
  setLowRatingMax,
  lowRatingMsg,
  saveLowRatingMovieSettings,
  runLowRatingMoviesPreview,
  unwatchedStaleEnabled,
  setUnwatchedStaleEnabled,
  unwatchedStaleDays,
  setUnwatchedStaleDays,
  unwatchedStaleMsg,
  saveUnwatchedStaleMovieSettings,
  runUnwatchedStaleMoviesPreview,
}: PrunerScopeTabDefaultRulesMoviesProps) {
  if (scope !== "movies") return null;
  return (
    <>
      {isPlex ? (
        <p className="text-xs text-[var(--mm-text2)]">
          On Plex, watched movies, low-score movies, and old unwatched movies
          all use the same on-server details MediaMop already reads for other
          scans — watched means the server shows you played it; low score uses
          Plex audience rating; old unwatched uses when Plex says the title was
          added to the library.
        </p>
      ) : null}
      <div
        className="space-y-2 rounded-md border border-[var(--mm-border)] bg-[var(--mm-card-bg)] px-4 py-3 text-sm text-[var(--mm-text)]"
        data-testid="pruner-watched-movies-panel"
      >
        <p className="text-sm font-semibold text-[var(--mm-text)]">
          {isPlex
            ? "Delete watched movies — Plex"
            : "Delete watched movies — Jellyfin / Emby"}
        </p>
        <p className="text-xs text-[var(--mm-text2)]">
          {isPlex
            ? "Uses Plex watched flags for your MediaMop user."
            : "Uses the server watched flag for each movie."}
        </p>
        {showInteractiveControls ? (
          <div className="space-y-2">
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={watchedMoviesEnabled}
                disabled={busy}
                onChange={(e) => setWatchedMoviesEnabled(e.target.checked)}
              />
              Turn on watched-movie cleanup
            </label>
            <button
              type="button"
              className="rounded-md border border-[var(--mm-border)] px-3 py-1 text-sm font-medium text-[var(--mm-text)] disabled:opacity-50"
              disabled={busy}
              onClick={() => void saveWatchedMoviesSettings()}
            >
              Save watched movies rule
            </button>
            {watchedMoviesMsg ? (
              <p className="text-xs text-green-600">{watchedMoviesMsg}</p>
            ) : null}
            <button
              type="button"
              className="rounded-md bg-[var(--mm-surface2)] px-3 py-1.5 text-sm font-medium text-[var(--mm-text)] ring-1 ring-[var(--mm-border)] disabled:opacity-50"
              disabled={busy || !watchedMoviesEnabled}
              title={
                !watchedMoviesEnabled
                  ? "Turn the rule on and save before running this scan."
                  : undefined
              }
              onClick={() => void runWatchedMoviesPreview()}
            >
              Scan for watched movies
            </button>
          </div>
        ) : (
          <p className="text-xs text-[var(--mm-text2)]">
            Watched movies rule is{" "}
            <strong>
              {scopeRow?.watched_movies_reported_enabled ? "on" : "off"}
            </strong>{" "}
            for this library. Sign in as an operator to change it.
          </p>
        )}
      </div>
      <div
        className="space-y-2 rounded-md border border-[var(--mm-border)] bg-[var(--mm-card-bg)] px-4 py-3 text-sm text-[var(--mm-text)]"
        data-testid="pruner-watched-low-rating-panel"
      >
        <p className="text-sm font-semibold text-[var(--mm-text)]">
          {isPlex
            ? "Delete low-score watched movies — Plex"
            : "Delete low-score watched movies — Jellyfin / Emby"}
        </p>
        <p className="text-xs text-[var(--mm-text2)]">
          {isPlex
            ? "Uses Plex audience rating."
            : "Uses your server’s community rating."}
        </p>
        {showInteractiveControls ? (
          <div className="space-y-2">
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={lowRatingEnabled}
                disabled={busy}
                onChange={(e) => setLowRatingEnabled(e.target.checked)}
              />
              Turn on low-score watched-movie cleanup
            </label>
            <label className="flex flex-wrap items-center gap-2 text-sm text-[var(--mm-text2)]">
              {isPlex
                ? "Highest Plex audience rating to keep (0-10)"
                : "Highest community rating to keep (0-10)"}
              <input
                type="number"
                min={0}
                max={10}
                step="0.1"
                className="w-24 rounded border border-[var(--mm-border)] bg-[var(--mm-surface2)] px-2 py-1 text-sm text-[var(--mm-text)]"
                value={lowRatingMax}
                disabled={busy}
                onChange={(e) => setLowRatingMax(e.target.value)}
              />
            </label>
            <button
              type="button"
              className="rounded-md border border-[var(--mm-border)] px-3 py-1 text-sm font-medium text-[var(--mm-text)] disabled:opacity-50"
              disabled={busy}
              onClick={() => void saveLowRatingMovieSettings()}
            >
              Save low-rating rule
            </button>
            {lowRatingMsg ? (
              <p className="text-xs text-green-600">{lowRatingMsg}</p>
            ) : null}
            <button
              type="button"
              className="rounded-md bg-[var(--mm-surface2)] px-3 py-1.5 text-sm font-medium text-[var(--mm-text)] ring-1 ring-[var(--mm-border)] disabled:opacity-50"
              disabled={busy || !lowRatingEnabled}
              title={
                !lowRatingEnabled
                  ? "Turn the rule on and save before running this scan."
                  : undefined
              }
              onClick={() => void runLowRatingMoviesPreview()}
            >
              Scan for low-score watched movies
            </button>
          </div>
        ) : (
          <p className="text-xs text-[var(--mm-text2)]">
            Low-score rule is{" "}
            <strong>
              {scopeRow?.watched_movie_low_rating_reported_enabled
                ? "on"
                : "off"}
            </strong>
            {scopeRow?.watched_movie_low_rating_reported_enabled ? (
              <>
                {" "}
                (delete watched movies rated below{" "}
                {isPlex
                  ? scopeRow.watched_movie_low_rating_max_plex_audience_rating
                  : scopeRow.watched_movie_low_rating_max_jellyfin_emby_community_rating}
                ).
              </>
            ) : null}{" "}
            Sign in as an operator to change it.
          </p>
        )}
      </div>
      <div
        className="space-y-2 rounded-md border border-[var(--mm-border)] bg-[var(--mm-card-bg)] px-4 py-3 text-sm text-[var(--mm-text)]"
        data-testid="pruner-unwatched-stale-panel"
      >
        <p className="text-sm font-semibold text-[var(--mm-text)]">
          {isPlex
            ? "Delete old unwatched movies — Plex"
            : "Delete old unwatched movies — Jellyfin / Emby"}
        </p>
        <p className="text-xs text-[var(--mm-text2)]">
          {isPlex
            ? "Never watched, using when Plex added the title."
            : "Never watched, using when the server created the title."}
        </p>
        {showInteractiveControls ? (
          <div className="space-y-2">
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={unwatchedStaleEnabled}
                disabled={busy}
                onChange={(e) => setUnwatchedStaleEnabled(e.target.checked)}
              />
              Turn on old unwatched movie cleanup
            </label>
            <label className="flex flex-wrap items-center gap-2 text-sm text-[var(--mm-text2)]">
              Minimum age (days, 7-3650)
              <input
                type="number"
                min={7}
                max={3650}
                className="w-24 rounded border border-[var(--mm-border)] bg-[var(--mm-surface2)] px-2 py-1 text-sm text-[var(--mm-text)]"
                value={unwatchedStaleDays}
                disabled={busy}
                onChange={(e) =>
                  setUnwatchedStaleDays(parseInt(e.target.value, 10) || 90)
                }
              />
            </label>
            <button
              type="button"
              className="rounded-md border border-[var(--mm-border)] px-3 py-1 text-sm font-medium text-[var(--mm-text)] disabled:opacity-50"
              disabled={busy}
              onClick={() => void saveUnwatchedStaleMovieSettings()}
            >
              Save unwatched stale rule
            </button>
            {unwatchedStaleMsg ? (
              <p className="text-xs text-green-600">{unwatchedStaleMsg}</p>
            ) : null}
            <button
              type="button"
              className="rounded-md bg-[var(--mm-surface2)] px-3 py-1.5 text-sm font-medium text-[var(--mm-text)] ring-1 ring-[var(--mm-border)] disabled:opacity-50"
              disabled={busy || !unwatchedStaleEnabled}
              title={
                !unwatchedStaleEnabled
                  ? "Turn the rule on and save before running this scan."
                  : undefined
              }
              onClick={() => void runUnwatchedStaleMoviesPreview()}
            >
              Scan for old unwatched movies
            </button>
          </div>
        ) : (
          <p className="text-xs text-[var(--mm-text2)]">
            Unwatched stale rule is{" "}
            <strong>
              {scopeRow?.unwatched_movie_stale_reported_enabled ? "on" : "off"}
            </strong>{" "}
            (min age {scopeRow?.unwatched_movie_stale_min_age_days} days). Sign
            in as an operator to change it.
          </p>
        )}
      </div>
    </>
  );
}
