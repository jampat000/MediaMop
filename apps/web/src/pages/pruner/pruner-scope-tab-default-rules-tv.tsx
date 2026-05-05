import { Fragment } from "react";
import type { PrunerServerInstance } from "../../lib/pruner/api";

type ScopeRow = PrunerServerInstance["scopes"][number] | undefined;

type PrunerScopeTabDefaultRulesTvProps = {
  scope: "tv" | "movies";
  libraryTabPhrase: string;
  busy: boolean;
  showInteractiveControls: boolean;
  scopeRow: ScopeRow;
  staleNeverEnabled: boolean;
  setStaleNeverEnabled: (value: boolean) => void;
  staleNeverDays: number;
  setStaleNeverDays: (value: number) => void;
  staleNeverMsg: string | null;
  saveStaleNeverSettings: () => Promise<void>;
  runStaleNeverPreview: () => Promise<void>;
  watchedTvEnabled: boolean;
  setWatchedTvEnabled: (value: boolean) => void;
  watchedTvMsg: string | null;
  saveWatchedTvSettings: () => Promise<void>;
  runWatchedTvPreview: () => Promise<void>;
};

export function PrunerScopeTabDefaultRulesTv({
  scope,
  libraryTabPhrase,
  busy,
  showInteractiveControls,
  scopeRow,
  staleNeverEnabled,
  setStaleNeverEnabled,
  staleNeverDays,
  setStaleNeverDays,
  staleNeverMsg,
  saveStaleNeverSettings,
  runStaleNeverPreview,
  watchedTvEnabled,
  setWatchedTvEnabled,
  watchedTvMsg,
  saveWatchedTvSettings,
  runWatchedTvPreview,
}: PrunerScopeTabDefaultRulesTvProps) {
  return (
    <Fragment>
      <div
        className="space-y-2 rounded-md border border-[var(--mm-border)] bg-[var(--mm-card-bg)] px-4 py-3 text-sm text-[var(--mm-text)]"
        data-testid="pruner-never-played-stale-panel"
      >
        <p className="text-sm font-semibold text-[var(--mm-text)]">
          {scope === "tv"
            ? "Delete TV shows not watched in the last N days — Jellyfin / Emby"
            : "Delete TV or movies never started and older than N days — Jellyfin / Emby"}
        </p>
        <p className="text-xs text-[var(--mm-text2)]">
          Only titles with no play time and older than this age.
        </p>
        {showInteractiveControls ? (
          <div className="space-y-2">
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={staleNeverEnabled}
                disabled={busy}
                onChange={(e) => setStaleNeverEnabled(e.target.checked)}
              />
              {scope === "tv"
                ? "Turn on never-watched TV older than this age"
                : "Turn on never-watched TV or movies older than this age"}
            </label>
            <div className="flex flex-wrap items-center gap-2">
              <label className="text-sm text-[var(--mm-text2)]">
                Minimum age (days, 7-3650):{" "}
                <input
                  type="number"
                  min={7}
                  max={3650}
                  className="w-24 rounded border border-[var(--mm-border)] bg-[var(--mm-surface2)] px-2 py-1 text-sm text-[var(--mm-text)]"
                  value={staleNeverDays}
                  disabled={busy}
                  onChange={(e) =>
                    setStaleNeverDays(parseInt(e.target.value, 10) || 90)
                  }
                />
              </label>
              <button
                type="button"
                className="rounded-md border border-[var(--mm-border)] px-3 py-1 text-sm font-medium text-[var(--mm-text)] disabled:opacity-50"
                disabled={busy}
                onClick={() => void saveStaleNeverSettings()}
              >
                Save never-watched age rule
              </button>
            </div>
            {staleNeverMsg ? <p className="text-xs text-green-600">{staleNeverMsg}</p> : null}
            <button
              type="button"
              className="rounded-md bg-[var(--mm-surface2)] px-3 py-1.5 text-sm font-medium text-[var(--mm-text)] ring-1 ring-[var(--mm-border)] disabled:opacity-50"
              disabled={busy || !staleNeverEnabled}
              title={!staleNeverEnabled ? "Turn the rule on and save before running this scan." : undefined}
              onClick={() => void runStaleNeverPreview()}
            >
              {scope === "tv"
                ? "Scan for unwatched TV shows older than your setting"
                : "Scan for unwatched TV or movies older than your setting"}
            </button>
          </div>
        ) : (
          <p className="text-xs text-[var(--mm-text2)]">
            Rule is{" "}
            <strong>{scopeRow?.never_played_stale_reported_enabled ? "on" : "off"}</strong>
            {scopeRow ? (
              <>
                {" "}
                (minimum age {scopeRow.never_played_min_age_days} days). Sign in
                as an operator to change it.
              </>
            ) : null}
          </p>
        )}
      </div>
      {scope === "tv" ? (
        <div
          className="space-y-2 rounded-md border border-[var(--mm-border)] bg-[var(--mm-card-bg)] px-4 py-3 text-sm text-[var(--mm-text)]"
          data-testid="pruner-watched-tv-panel"
        >
          <p className="text-sm font-semibold text-[var(--mm-text)]">
            Delete watched TV episodes — Jellyfin / Emby
          </p>
          <p className="text-xs text-[var(--mm-text2)]">
            Uses the watched flag for your MediaMop user on this server.
          </p>
          {showInteractiveControls ? (
            <div className="space-y-2">
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={watchedTvEnabled}
                  disabled={busy}
                  onChange={(e) => setWatchedTvEnabled(e.target.checked)}
                />
                Turn on watched-TV cleanup
              </label>
              <button
                type="button"
                className="rounded-md border border-[var(--mm-border)] px-3 py-1 text-sm font-medium text-[var(--mm-text)] disabled:opacity-50"
                disabled={busy}
                onClick={() => void saveWatchedTvSettings()}
              >
                Save watched TV rule
              </button>
              {watchedTvMsg ? <p className="text-xs text-green-600">{watchedTvMsg}</p> : null}
              <button
                type="button"
                className="rounded-md bg-[var(--mm-surface2)] px-3 py-1.5 text-sm font-medium text-[var(--mm-text)] ring-1 ring-[var(--mm-border)] disabled:opacity-50"
                disabled={busy || !watchedTvEnabled}
                title={!watchedTvEnabled ? "Turn the rule on and save before running this scan." : undefined}
                onClick={() => void runWatchedTvPreview()}
              >
                Scan for watched TV shows
              </button>
            </div>
          ) : (
            <p className="text-xs text-[var(--mm-text2)]">
              Watched TV rule is{" "}
              <strong>{scopeRow?.watched_tv_reported_enabled ? "on" : "off"}</strong>{" "}
              for this {libraryTabPhrase}. Sign in as an operator to change it.
            </p>
          )}
        </div>
      ) : null}
    </Fragment>
  );
}
