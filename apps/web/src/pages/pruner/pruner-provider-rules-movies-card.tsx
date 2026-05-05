import { MmOnOffSwitch } from "../../components/ui/mm-on-off-switch";
import { mmActionButtonClass } from "../../lib/ui/mm-control-roles";
import { PrunerGenreMultiSelect } from "./pruner-genre-multi-select";
import { PrunerPeopleRoleCheckboxes, type PrunerPeopleRoleId } from "./pruner-people-roles";
import { CommaField, YearRange } from "./pruner-provider-people-card";
import { PrunerStudioMultiSelect } from "./pruner-studio-multi-select";

type PrunerProviderRulesMoviesCardProps = {
  provider: "emby" | "jellyfin" | "plex";
  instanceId: number;
  isPlex: boolean;
  narrowingLabelClass: string;
  moviesControlsDisabled: boolean;
  watchedMovies: boolean;
  setWatchedMovies: (v: boolean) => void;
  lowRatingMovies: string;
  setLowRatingMovies: (v: string) => void;
  unwatchedDays: string;
  setUnwatchedDays: (v: string) => void;
  missingPrimaryMovies: boolean;
  setMissingPrimaryMovies: (v: boolean) => void;
  genreMovies: string[];
  setGenreMovies: (v: string[]) => void;
  moviesPeople: string;
  setMoviesPeople: (v: string) => void;
  moviesRoles: PrunerPeopleRoleId[];
  setMoviesRoles: (v: PrunerPeopleRoleId[]) => void;
  studioMovies: string[];
  setStudioMovies: (v: string[]) => void;
  yearMinMovies: string;
  setYearMinMovies: (v: string) => void;
  yearMaxMovies: string;
  setYearMaxMovies: (v: string) => void;
  moviesCollections: string;
  setMoviesCollections: (v: string) => void;
  canOperate: boolean;
  saveDisabledMovies: boolean;
  saveMovies: () => Promise<void>;
  busyMovies: boolean;
  msgMovies: string | null;
  errMovies: string | null;
};

export function PrunerProviderRulesMoviesCard({
  provider,
  instanceId,
  isPlex,
  narrowingLabelClass,
  moviesControlsDisabled,
  watchedMovies,
  setWatchedMovies,
  lowRatingMovies,
  setLowRatingMovies,
  unwatchedDays,
  setUnwatchedDays,
  missingPrimaryMovies,
  setMissingPrimaryMovies,
  genreMovies,
  setGenreMovies,
  moviesPeople,
  setMoviesPeople,
  moviesRoles,
  setMoviesRoles,
  studioMovies,
  setStudioMovies,
  yearMinMovies,
  setYearMinMovies,
  yearMaxMovies,
  setYearMaxMovies,
  moviesCollections,
  setMoviesCollections,
  canOperate,
  saveDisabledMovies,
  saveMovies,
  busyMovies,
  msgMovies,
  errMovies,
}: PrunerProviderRulesMoviesCardProps) {
  return (
    <fieldset
      disabled={moviesControlsDisabled}
      className="mm-card mm-dash-card min-w-0 border border-[var(--mm-border)] bg-[var(--mm-card-bg)] p-5 sm:p-6"
    >
      <div
        className="flex min-h-0 min-w-0 flex-1 flex-col"
        data-testid={`pruner-provider-movies-config-${provider}`}
      >
        <div className="mm-card-action-body min-h-0 flex-1">
          <div className="flex items-center gap-2 border-b border-[var(--mm-border)] pb-2">
            <span className="text-sm font-semibold uppercase tracking-wide text-[var(--mm-text1)]">
              Movies
            </span>
          </div>
          <p className={narrowingLabelClass}>Rules</p>
          <MmOnOffSwitch
            id={`pruner-op-mov-watched-${provider}`}
            label="Delete movies you have already watched"
            enabled={watchedMovies}
            disabled={moviesControlsDisabled}
            onChange={setWatchedMovies}
          />
          <label
            className="block text-sm text-[var(--mm-text1)]"
            htmlFor={`pruner-op-mov-lowrating-${provider}`}
          >
            <span className="mb-1 block text-xs text-[var(--mm-text3)]">
              {isPlex
                ? "Delete watched movies rated below this score - uses Plex audience rating (0-10, 0 = off)"
                : "Delete watched movies rated below this score - uses your server's community rating (0-10, 0 = off)"}
            </span>
            <input
              id={`pruner-op-mov-lowrating-${provider}`}
              type="number"
              min={0}
              max={10}
              step={0.1}
              className="mm-input w-full max-w-xs"
              value={lowRatingMovies}
              onChange={(e) => setLowRatingMovies(e.target.value)}
              disabled={moviesControlsDisabled}
            />
          </label>
          <label className="block text-sm text-[var(--mm-text2)]">
            <span className="mb-1 block text-xs text-[var(--mm-text3)]">
              Delete movies you have not watched that are older than ___ days (0 = off)
            </span>
            <input
              type="number"
              min={0}
              max={3650}
              className="mm-input w-full max-w-xs"
              value={unwatchedDays}
              onChange={(e) => setUnwatchedDays(e.target.value)}
              disabled={moviesControlsDisabled}
            />
          </label>
          {!isPlex ? (
            <MmOnOffSwitch
              id={`pruner-op-mov-missing-${provider}`}
              label="Delete movies missing a main poster"
              enabled={missingPrimaryMovies}
              disabled={moviesControlsDisabled}
              onChange={setMissingPrimaryMovies}
            />
          ) : null}

          <div className="border-t border-[var(--mm-border)] pt-4 mt-1" aria-hidden="true" />

          <div className="space-y-1">
            <span className="mb-1 block text-xs font-medium text-[var(--mm-text3)]">
              Delete content in these genres
            </span>
            <PrunerGenreMultiSelect
              value={genreMovies}
              onChange={setGenreMovies}
              disabled={moviesControlsDisabled}
              testId={`pruner-rules-genre-movies-${provider}`}
            />
          </div>
          <label
            className="block text-sm text-[var(--mm-text2)]"
            data-testid={`pruner-provider-movies-people-${provider}`}
          >
            <span className="mb-1 block text-xs font-medium text-[var(--mm-text3)]">
              Delete content involving these people
            </span>
            <textarea
              className="mm-input min-h-[6rem] w-full font-sans text-sm"
              rows={5}
              placeholder="e.g. Alex Carter, Jordan Lee (comma or one per line)"
              value={moviesPeople}
              disabled={moviesControlsDisabled}
              onChange={(e) => setMoviesPeople(e.target.value)}
            />
            <span className="mt-1 block text-xs text-[var(--mm-text3)]">
              Leave empty to skip.
            </span>
          </label>
          <PrunerPeopleRoleCheckboxes
            value={moviesRoles}
            onChange={setMoviesRoles}
            disabled={moviesControlsDisabled}
            variant={isPlex ? "plex" : "emby-jellyfin"}
            testId={`pruner-provider-movies-people-roles-${provider}`}
            rolesHeading="Check these credits when matching names"
          />
          <div className="space-y-1">
            <span className="mb-1 block text-xs font-medium text-[var(--mm-text3)]">
              Delete content from these studios
            </span>
            <PrunerStudioMultiSelect
              value={studioMovies}
              onChange={setStudioMovies}
              disabled={moviesControlsDisabled}
              instanceId={instanceId}
              scope="movies"
              testId={`pruner-rules-studio-movies-${provider}`}
            />
          </div>
          <YearRange
            min={yearMinMovies}
            max={yearMaxMovies}
            onMin={setYearMinMovies}
            onMax={setYearMaxMovies}
            disabled={moviesControlsDisabled}
            title="Delete content released in these years"
            helperText="Leave empty to skip."
          />
          {isPlex ? (
            <CommaField
              label="Delete content in these collections"
              placeholder="e.g. MCU, Pixar"
              helper="Leave empty to skip."
              value={moviesCollections}
              onChange={setMoviesCollections}
              disabled={moviesControlsDisabled}
            />
          ) : null}
        </div>
        <div className="mm-card-action-footer">
          {canOperate ? (
            <button
              type="button"
              className={mmActionButtonClass({
                variant: "primary",
                disabled: saveDisabledMovies,
              })}
              disabled={saveDisabledMovies}
              onClick={() => void saveMovies()}
            >
              {busyMovies ? "Saving..." : "Save Movies settings"}
            </button>
          ) : null}
          {msgMovies ? (
            <p className="text-sm text-green-600" role="status">
              {msgMovies}
            </p>
          ) : null}
          {errMovies ? (
            <p className="text-sm text-red-500" role="alert">
              {errMovies}
            </p>
          ) : null}
        </div>
      </div>
    </fieldset>
  );
}
