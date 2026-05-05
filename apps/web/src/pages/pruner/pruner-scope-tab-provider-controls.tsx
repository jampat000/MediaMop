import type { ReactNode } from "react";
import { MmOnOffSwitch } from "../../components/ui/mm-on-off-switch";
import type { PrunerServerInstance } from "../../lib/pruner/api";
import { type PrunerPeopleRoleId } from "./pruner-people-roles";
import { PrunerGenreMultiSelect } from "./pruner-genre-multi-select";

export type PrunerScopeProviderSubsectionProps = {
  scope: "tv" | "movies";
  provSub?: "rules" | "filters" | "people";
  instanceId: number;
  disabledMode?: boolean;
  isPlex: boolean;
  busy: boolean;
  showInteractiveControls: boolean;
  scopeRow: PrunerServerInstance["scopes"][number] | undefined;
  watchedTvEnabled: boolean;
  setWatchedTvEnabled: (enabled: boolean) => void;
  rulesTvOlderDaysStr: string;
  setRulesTvOlderDaysStr: (value: string) => void;
  watchedMoviesEnabled: boolean;
  setWatchedMoviesEnabled: (enabled: boolean) => void;
  rulesMoviesLowRatingStr: string;
  setRulesMoviesLowRatingStr: (value: string) => void;
  rulesMoviesUnwatchedDaysStr: string;
  setRulesMoviesUnwatchedDaysStr: (value: string) => void;
  genreSelection: string[];
  setGenreSelection: (value: string[]) => void;
  yearMinStr: string;
  setYearMinStr: (value: string) => void;
  yearMaxStr: string;
  setYearMaxStr: (value: string) => void;
  studioText: string;
  setStudioText: (value: string) => void;
  peopleText: string;
  setPeopleText: (value: string) => void;
  peopleRoles: PrunerPeopleRoleId[];
  setPeopleRoles: (value: PrunerPeopleRoleId[]) => void;
  bundleMsg: string | null;
  err: string | null;
  saveProviderTvRulesBundle: () => Promise<void>;
  saveProviderMoviesRulesBundle: () => Promise<void>;
  saveProviderFiltersBundle: () => Promise<void>;
  saveProviderPeopleBundle: () => Promise<void>;
};

export function renderProviderRulesControls(
  props: PrunerScopeProviderSubsectionProps,
): ReactNode {
  const {
    scope,
    isPlex,
    instanceId,
    busy,
    showInteractiveControls,
    scopeRow,
    watchedTvEnabled,
    setWatchedTvEnabled,
    rulesTvOlderDaysStr,
    setRulesTvOlderDaysStr,
    watchedMoviesEnabled,
    setWatchedMoviesEnabled,
    rulesMoviesLowRatingStr,
    setRulesMoviesLowRatingStr,
    rulesMoviesUnwatchedDaysStr,
    setRulesMoviesUnwatchedDaysStr,
  } = props;
  if (scope === "tv") {
    if (isPlex) {
      return (
        <div
          className="mm-bubble-stack"
          data-testid="pruner-provider-plex-tv-unsupported-rules"
        >
          <div className="space-y-1.5">
            <p className="text-sm font-medium text-[var(--mm-text1)]">
              Watched TV removal
            </p>
            <p className="text-xs leading-relaxed text-[var(--mm-text3)]">
              Not supported for Plex.
            </p>
          </div>
          <div className="space-y-1.5">
            <p className="text-sm font-medium text-[var(--mm-text1)]">
              Unwatched TV older than N days
            </p>
            <p className="text-xs leading-relaxed text-[var(--mm-text3)]">
              Not supported for Plex.
            </p>
          </div>
        </div>
      );
    }
    return (
      <div className="mm-bubble-stack">
        <div data-testid="pruner-watched-tv-panel">
          {showInteractiveControls ? (
            <MmOnOffSwitch
              id={`pruner-provider-tv-watched-${instanceId}`}
              label="Watched TV removal"
              enabled={watchedTvEnabled}
              disabled={busy}
              onChange={setWatchedTvEnabled}
            />
          ) : (
            <p className="text-xs text-[var(--mm-text2)]">
              Watched TV removal:{" "}
              <strong>{scopeRow?.watched_tv_reported_enabled ? "On" : "Off"}</strong>
            </p>
          )}
          <p className="mt-2 text-xs leading-relaxed text-[var(--mm-text3)]">
            Delete items marked watched for this provider user.
          </p>
        </div>
        <div data-testid="pruner-never-played-stale-panel">
          <p className="text-sm font-medium text-[var(--mm-text1)]">
            Unwatched TV older than N days
          </p>
          {showInteractiveControls ? (
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <input
                type="number"
                min={0}
                max={3650}
                className="mm-input w-24"
                value={rulesTvOlderDaysStr}
                disabled={busy}
                onChange={(e) => setRulesTvOlderDaysStr(e.target.value)}
              />
              <span className="text-sm text-[var(--mm-text2)]">days</span>
            </div>
          ) : (
            <p className="mt-2 text-xs text-[var(--mm-text2)]">
              Days:{" "}
              <strong>
                {!scopeRow?.never_played_stale_reported_enabled
                  ? "0 (off)"
                  : scopeRow.never_played_min_age_days}
              </strong>
            </p>
          )}
          <p className="mt-1 text-xs leading-relaxed text-[var(--mm-text3)]">
            Set 0 to disable. Minimum 7 days when active.
          </p>
        </div>
      </div>
    );
  }
  return (
    <div className="mm-bubble-stack">
      <div data-testid="pruner-watched-movies-panel">
        {showInteractiveControls ? (
          <MmOnOffSwitch
            id={`pruner-provider-movies-watched-${instanceId}`}
            label="Watched movies removal"
            enabled={watchedMoviesEnabled}
            disabled={busy}
            onChange={setWatchedMoviesEnabled}
          />
        ) : (
          <p className="text-xs text-[var(--mm-text2)]">
            Watched movies removal:{" "}
            <strong>{scopeRow?.watched_movies_reported_enabled ? "On" : "Off"}</strong>
          </p>
        )}
        <p className="mt-2 text-xs leading-relaxed text-[var(--mm-text3)]">
          {isPlex
            ? "Uses Plex watched state from allLeaves."
            : "Uses provider watched state for movie items."}
        </p>
      </div>
      <div data-testid="pruner-watched-low-rating-panel">
        <p className="text-sm font-medium text-[var(--mm-text1)]">
          Low-rating watched movies
        </p>
        <p className="mt-1 text-xs text-[var(--mm-text3)]">
          {isPlex
            ? "Plex audienceRating max (0–10)"
            : "Jellyfin/Emby CommunityRating max (0–10)"}
        </p>
        {showInteractiveControls ? (
          <input
            type="number"
            min={0}
            max={10}
            step="0.1"
            className="mm-input mt-2 w-28"
            value={rulesMoviesLowRatingStr}
            disabled={busy}
            onChange={(e) => setRulesMoviesLowRatingStr(e.target.value)}
          />
        ) : (
          <p className="mt-2 text-xs text-[var(--mm-text2)]">
            Max rating / off:{" "}
            <strong>
              {!scopeRow?.watched_movie_low_rating_reported_enabled
                ? "0 (off)"
                : isPlex
                  ? scopeRow.watched_movie_low_rating_max_plex_audience_rating
                  : scopeRow.watched_movie_low_rating_max_jellyfin_emby_community_rating}
            </strong>
          </p>
        )}
        <p className="mt-1 text-xs leading-relaxed text-[var(--mm-text3)]">
          Set 0 to disable.
        </p>
      </div>
      <div data-testid="pruner-unwatched-stale-panel">
        <p className="text-sm font-medium text-[var(--mm-text1)]">
          Unwatched movies older than N days
        </p>
        {showInteractiveControls ? (
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <input
              type="number"
              min={0}
              max={3650}
              className="mm-input w-24"
              value={rulesMoviesUnwatchedDaysStr}
              disabled={busy}
              onChange={(e) => setRulesMoviesUnwatchedDaysStr(e.target.value)}
            />
            <span className="text-sm text-[var(--mm-text2)]">days</span>
          </div>
        ) : (
          <p className="mt-2 text-xs text-[var(--mm-text2)]">
            Days:{" "}
            <strong>
              {!scopeRow?.unwatched_movie_stale_reported_enabled
                ? "0 (off)"
                : scopeRow.unwatched_movie_stale_min_age_days}
            </strong>
          </p>
        )}
        <p className="mt-1 text-xs leading-relaxed text-[var(--mm-text3)]">
          Set 0 to disable.
        </p>
      </div>
      {isPlex ? (
        <p
          className="text-xs text-[var(--mm-text3)]"
          data-testid="pruner-plex-other-rules-note"
          role="status"
        >
          Plex: watched TV and never-played stale are unsupported on the TV
          scope.
        </p>
      ) : null}
    </div>
  );
}

export function renderProviderFiltersControls(
  props: PrunerScopeProviderSubsectionProps,
): ReactNode {
  const {
    isPlex,
    scope,
    showInteractiveControls,
    genreSelection,
    setGenreSelection,
    busy,
    instanceId,
    scopeRow,
    yearMinStr,
    setYearMinStr,
    yearMaxStr,
    setYearMaxStr,
    studioText,
    setStudioText,
  } = props;
  return (
    <div className="mm-bubble-stack">
      {isPlex && scope === "tv" ? (
        <p
          className="text-xs leading-relaxed text-amber-100/90"
          data-testid="pruner-plex-tv-filters-scope-note"
          role="status"
        >
          On Plex, filters apply to the missing primary art rule only.
        </p>
      ) : null}
      <div className="space-y-2" data-testid="pruner-genre-filters-panel">
        <p className="text-sm font-medium text-[var(--mm-text1)]">Genres</p>
        {showInteractiveControls ? (
          <PrunerGenreMultiSelect
            value={genreSelection}
            onChange={setGenreSelection}
            disabled={busy}
            testId={`pruner-genre-multiselect-provider-${instanceId}-${scope}`}
            filterHelperText=""
          />
        ) : (
          <p className="text-xs text-[var(--mm-text2)]">
            {(scopeRow?.preview_include_genres ?? []).join(", ") || "—"}
          </p>
        )}
        <p className="text-xs text-[var(--mm-text3)]">
          Leave none selected to include every genre.
        </p>
      </div>
      <div className="space-y-2" data-testid="pruner-year-filters-panel">
        <p className="text-sm font-medium text-[var(--mm-text1)]">Year range</p>
        {showInteractiveControls ? (
          <div className="flex flex-wrap items-end gap-3">
            <label className="text-sm text-[var(--mm-text2)]">
              Min year
              <input
                type="number"
                min={1900}
                max={2100}
                className="mm-input ml-2 mt-1 w-24"
                placeholder="Min"
                value={yearMinStr}
                disabled={busy}
                onChange={(e) => setYearMinStr(e.target.value)}
              />
            </label>
            <label className="text-sm text-[var(--mm-text2)]">
              Max year
              <input
                type="number"
                min={1900}
                max={2100}
                className="mm-input ml-2 mt-1 w-24"
                placeholder="Max"
                value={yearMaxStr}
                disabled={busy}
                onChange={(e) => setYearMaxStr(e.target.value)}
              />
            </label>
          </div>
        ) : (
          <p className="text-xs text-[var(--mm-text2)]">
            {scopeRow?.preview_year_min ?? "—"} to{" "}
            {scopeRow?.preview_year_max ?? "—"}
          </p>
        )}
        <p className="text-xs text-[var(--mm-text3)]">
          Leave blank for open-ended. Range 1900–2100.
        </p>
      </div>
      <div className="space-y-2" data-testid="pruner-studio-preview-panel">
        <p className="text-sm font-medium text-[var(--mm-text1)]">Studio</p>
        {showInteractiveControls ? (
          <input
            type="text"
            className="mm-input w-full"
            placeholder="e.g. Warner Bros., BBC"
            value={studioText}
            disabled={busy}
            onChange={(e) => setStudioText(e.target.value)}
          />
        ) : (
          <p className="text-xs text-[var(--mm-text2)]">
            {(scopeRow?.preview_include_studios ?? []).join(", ") || "—"}
          </p>
        )}
        <p className="text-xs text-[var(--mm-text3)]">
          Leave blank to include all studios.
        </p>
      </div>
    </div>
  );
}
