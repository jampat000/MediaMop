import { useEffect, useState } from "react";
import { showFailedImportCleanupPolicyEditor } from "../../lib/fetcher/failed-imports/eligibility";
import {
  useFailedImportCleanupPolicyQuery,
  useFailedImportCleanupPolicySaveMoviesMutation,
  useFailedImportCleanupPolicySaveTvMutation,
} from "../../lib/fetcher/failed-imports/queries";
import type {
  FailedImportCleanupPolicyAxis,
  FailedImportQueueHandlingAction,
} from "../../lib/fetcher/failed-imports/types";
import { fetcherMenuButtonClass } from "./fetcher-menu-button";
import {
  FETCHER_FI_POLICY_SAVE_RADARR,
  FETCHER_FI_POLICY_SAVE_SONARR,
  FETCHER_FI_POLICY_SAVING,
  FETCHER_FI_POLICY_VIEWER_NOTE,
} from "../../lib/fetcher/failed-imports/user-copy";
import { MmListboxPicker } from "../../components/ui/mm-listbox-picker";
import { draftDiffersFromCommittedLabel } from "./fetcher-numeric-settings-draft";

function cloneAxis(a: FailedImportCleanupPolicyAxis): FailedImportCleanupPolicyAxis {
  return { ...a };
}

type HandlingField = keyof Pick<
  FailedImportCleanupPolicyAxis,
  | "handling_quality_rejection"
  | "handling_unmatched_manual_import"
  | "handling_sample_release"
  | "handling_corrupt_import"
  | "handling_failed_download"
  | "handling_failed_import"
>;

const HANDLING_FIELDS: HandlingField[] = [
  "handling_quality_rejection",
  "handling_unmatched_manual_import",
  "handling_sample_release",
  "handling_corrupt_import",
  "handling_failed_download",
  "handling_failed_import",
];

const ROW_LABELS: Record<HandlingField, string> = {
  handling_quality_rejection: "Quality issue",
  handling_unmatched_manual_import: "Manual import required",
  handling_sample_release: "Sample / junk release",
  handling_corrupt_import: "Corrupt / integrity failure",
  handling_failed_download: "Download failed",
  handling_failed_import: "Generic import error",
};

const FI_HANDLING_ACTION_OPTIONS = [
  { value: "leave_alone", label: "Ignore" },
  { value: "remove_only", label: "Remove" },
  { value: "remove_and_blocklist", label: "Remove + block" },
] as const;

/** Map persisted `blocklist_only` to the closest listbox value for display (state unchanged until user edits). */
function handlingActionForSelect(action: FailedImportQueueHandlingAction): FailedImportQueueHandlingAction {
  if (action === "leave_alone" || action === "remove_only" || action === "remove_and_blocklist") {
    return action;
  }
  return "remove_and_blocklist";
}

const RUN_INTERVAL_MIN_MINUTES = 0;
const RUN_INTERVAL_MAX_MINUTES = 7 * 24 * 60;

/** Blank failed-import cleanup run interval restores to 60 minutes (timed cleanup on). */
const DEFAULT_FAILED_IMPORT_CLEANUP_RUN_INTERVAL_SECONDS = 60 * 60;

function clampCleanupIntervalSeconds(seconds: number): number {
  return Math.min(Math.max(Math.round(seconds), 60), 7 * 24 * 3600);
}

function committedCleanupRunIntervalMinutesText(axis: FailedImportCleanupPolicyAxis): string {
  if (!axis.cleanup_drive_schedule_enabled) {
    return "";
  }
  return String(Math.round(axis.cleanup_drive_schedule_interval_seconds / 60));
}

function finalizeFailedImportCleanupRunIntervalDraft(
  draft: string | null,
  value: FailedImportCleanupPolicyAxis,
): FailedImportCleanupPolicyAxis {
  if (draft === null) {
    return value;
  }
  const raw = draft.trim();
  if (raw === "") {
    return {
      ...value,
      cleanup_drive_schedule_enabled: true,
      cleanup_drive_schedule_interval_seconds: DEFAULT_FAILED_IMPORT_CLEANUP_RUN_INTERVAL_SECONDS,
    };
  }
  const minutes = Number(raw);
  if (!Number.isFinite(minutes)) {
    return {
      ...value,
      cleanup_drive_schedule_enabled: true,
      cleanup_drive_schedule_interval_seconds: DEFAULT_FAILED_IMPORT_CLEANUP_RUN_INTERVAL_SECONDS,
    };
  }
  const m = Math.min(Math.max(Math.trunc(minutes), RUN_INTERVAL_MIN_MINUTES), RUN_INTERVAL_MAX_MINUTES);
  if (m <= 0) {
    return { ...value, cleanup_drive_schedule_enabled: false, cleanup_drive_schedule_interval_seconds: 3600 };
  }
  const seconds = clampCleanupIntervalSeconds(m * 60);
  return { ...value, cleanup_drive_schedule_enabled: true, cleanup_drive_schedule_interval_seconds: seconds };
}

type CleanupAxis = "tv" | "movies";

function CleanupAxisCard({
  value,
  onChange,
  runIntervalDraft,
  setRunIntervalDraft,
  optionsDisabled,
  optionsGroupId,
  canEdit,
  saveLabel,
  saveTestId,
  savedTestId,
  onSave,
  saveDisabled,
  savePending,
  showSaved,
  showError,
  errorMessage,
}: {
  value: FailedImportCleanupPolicyAxis;
  onChange: (next: FailedImportCleanupPolicyAxis) => void;
  runIntervalDraft: string | null;
  setRunIntervalDraft: (next: string | null) => void;
  optionsDisabled: boolean;
  optionsGroupId: string;
  canEdit: boolean;
  saveLabel: string;
  saveTestId: string;
  savedTestId: string;
  onSave: () => void;
  saveDisabled: boolean;
  savePending: boolean;
  showSaved: boolean;
  showError: boolean;
  errorMessage: string;
}) {
  const runIntervalInputValue =
    runIntervalDraft !== null ? runIntervalDraft : committedCleanupRunIntervalMinutesText(value);

  const commitRunIntervalFromDraft = () => {
    if (runIntervalDraft === null) {
      return;
    }
    const next = finalizeFailedImportCleanupRunIntervalDraft(runIntervalDraft, value);
    setRunIntervalDraft(null);
    if (
      next.cleanup_drive_schedule_enabled !== value.cleanup_drive_schedule_enabled ||
      next.cleanup_drive_schedule_interval_seconds !== value.cleanup_drive_schedule_interval_seconds
    ) {
      onChange(next);
    }
  };

  return (
    <div
      className={[
        "flex w-full min-w-0 flex-col overflow-visible rounded-lg border border-[var(--mm-border)] bg-[var(--mm-surface2)]/25 p-5 shadow-sm transition-shadow duration-200",
        showSaved
          ? "ring-2 ring-[var(--mm-accent-ring)] ring-offset-2 ring-offset-[var(--mm-bg-main)] shadow-[0_0_0_1px_rgba(212,175,55,0.12)]"
          : "",
      ].join(" ")}
    >
      <div data-testid={`${optionsGroupId}-rows`}>
        {HANDLING_FIELDS.map((field, rowIdx) => (
          <div
            key={field}
            className={[
              "flex w-full items-center justify-between gap-4 py-[10px]",
              rowIdx < HANDLING_FIELDS.length - 1 ? "border-b-[0.5px] border-[var(--mm-border)]" : "",
            ].join(" ")}
          >
            <span className="min-w-0 flex-1 text-sm text-[var(--mm-text1)]">{ROW_LABELS[field]}</span>
            <MmListboxPicker
              className="w-[11rem] shrink-0"
              options={FI_HANDLING_ACTION_OPTIONS}
              value={handlingActionForSelect(value[field])}
              disabled={optionsDisabled}
              data-testid={`${optionsGroupId}-${field}-action-segments`}
              placeholder="Select…"
              onChange={(next) =>
                onChange({
                  ...value,
                  [field]: next as FailedImportQueueHandlingAction,
                })
              }
            />
          </div>
        ))}
      </div>

      <div className="mt-1 flex items-center justify-between border-t-[0.5px] border-[var(--mm-border)] pt-[14px]">
        <span className="text-sm text-[var(--mm-text1)]">Automatic check interval</span>
        <div className="flex shrink-0 items-center gap-2">
          {canEdit ? (
            <div className="w-[11rem] shrink-0 flex items-center gap-2">
              <input
                id={`${optionsGroupId}-run-interval`}
                type="number"
                min={RUN_INTERVAL_MIN_MINUTES}
                max={RUN_INTERVAL_MAX_MINUTES}
                className="mm-input flex-1 min-w-0"
                disabled={optionsDisabled}
                data-testid={`${optionsGroupId}-run-interval`}
                value={runIntervalInputValue}
                onFocus={() => setRunIntervalDraft(committedCleanupRunIntervalMinutesText(value))}
                onChange={(e) => setRunIntervalDraft(e.target.value)}
                onBlur={() => commitRunIntervalFromDraft()}
              />
              <span className="text-sm text-[var(--mm-text3)]">min</span>
            </div>
          ) : (
            <p
              id={`${optionsGroupId}-run-interval`}
              className="text-sm text-[var(--mm-text2)]"
              data-testid={`${optionsGroupId}-run-interval-readonly`}
            >
              {value.cleanup_drive_schedule_enabled
                ? `${Math.round(value.cleanup_drive_schedule_interval_seconds / 60)} minutes`
                : "Off"}
            </p>
          )}
        </div>
      </div>

      {canEdit ? (
        <div className="mt-6 space-y-4 border-t border-[var(--mm-border)] pt-5">
          {showSaved ? (
            <p
              className="rounded-md border border-[rgba(212,175,55,0.45)] bg-[var(--mm-accent-soft)] px-3 py-2 text-sm font-medium text-[var(--mm-text1)]"
              role="status"
              data-testid={savedTestId}
            >
              Saved.
            </p>
          ) : null}
          {showError ? (
            <p className="text-sm text-red-400" role="alert">
              {errorMessage}
            </p>
          ) : null}
          <button
            type="button"
            data-testid={saveTestId}
            className={fetcherMenuButtonClass({
              variant: "primary",
              disabled: saveDisabled,
            })}
            disabled={saveDisabled}
            onClick={onSave}
          >
            {savePending ? FETCHER_FI_POLICY_SAVING : saveLabel}
          </button>
        </div>
      ) : null}
    </div>
  );
}

export type FetcherFailedImportsCleanupPolicyAxes = "tv" | "movies";

/** Fetcher failed-imports policy: per-class Sonarr/Radarr queue actions with per-axis save. */
export function FetcherFailedImportsCleanupPolicySection({
  role,
  axes,
}: {
  role: string | undefined;
  axes: FetcherFailedImportsCleanupPolicyAxes;
}) {
  const q = useFailedImportCleanupPolicyQuery();
  const saveTv = useFailedImportCleanupPolicySaveTvMutation();
  const saveMovies = useFailedImportCleanupPolicySaveMoviesMutation();
  const canEdit = showFailedImportCleanupPolicyEditor(role);

  const [movies, setMovies] = useState<FailedImportCleanupPolicyAxis | null>(null);
  const [tvShows, setTvShows] = useState<FailedImportCleanupPolicyAxis | null>(null);
  const [tvRunIntervalDraft, setTvRunIntervalDraft] = useState<string | null>(null);
  const [moviesRunIntervalDraft, setMoviesRunIntervalDraft] = useState<string | null>(null);
  const [savedTvFlash, setSavedTvFlash] = useState(false);
  const [savedMoviesFlash, setSavedMoviesFlash] = useState(false);
  const [errorAxis, setErrorAxis] = useState<CleanupAxis | null>(null);

  useEffect(() => {
    if (q.data) {
      setMovies(cloneAxis(q.data.movies));
      setTvShows(cloneAxis(q.data.tv_shows));
      setTvRunIntervalDraft(null);
      setMoviesRunIntervalDraft(null);
    }
  }, [q.data]);

  const dirtyTv = Boolean(
    q.data &&
      tvShows &&
      (JSON.stringify(tvShows) !== JSON.stringify(q.data.tv_shows) ||
        draftDiffersFromCommittedLabel(tvRunIntervalDraft, committedCleanupRunIntervalMinutesText(tvShows))),
  );
  const dirtyMovies = Boolean(
    q.data &&
      movies &&
      (JSON.stringify(movies) !== JSON.stringify(q.data.movies) ||
        draftDiffersFromCommittedLabel(moviesRunIntervalDraft, committedCleanupRunIntervalMinutesText(movies))),
  );

  useEffect(() => {
    if (dirtyTv) {
      setSavedTvFlash(false);
    }
  }, [dirtyTv]);

  useEffect(() => {
    if (dirtyMovies) {
      setSavedMoviesFlash(false);
    }
  }, [dirtyMovies]);

  useEffect(() => {
    if (!savedTvFlash) {
      return;
    }
    const t = window.setTimeout(() => setSavedTvFlash(false), 2400);
    return () => window.clearTimeout(t);
  }, [savedTvFlash]);

  useEffect(() => {
    if (!savedMoviesFlash) {
      return;
    }
    const t = window.setTimeout(() => setSavedMoviesFlash(false), 2400);
    return () => window.clearTimeout(t);
  }, [savedMoviesFlash]);

  const mutateSave = (axis: CleanupAxis) => {
    if (!movies || !tvShows || !q.data) {
      return;
    }
    let nextMovies = movies;
    let nextTv = tvShows;
    if (axis === "tv") {
      nextTv = finalizeFailedImportCleanupRunIntervalDraft(tvRunIntervalDraft, tvShows);
      setTvRunIntervalDraft(null);
      setTvShows(nextTv);
    } else {
      nextMovies = finalizeFailedImportCleanupRunIntervalDraft(moviesRunIntervalDraft, movies);
      setMoviesRunIntervalDraft(null);
      setMovies(nextMovies);
    }
    setErrorAxis(null);
    const mut = axis === "tv" ? saveTv : saveMovies;
    const payload = axis === "tv" ? nextTv : nextMovies;
    mut.mutate(payload, {
      onSuccess: () => {
        if (axis === "tv") {
          setSavedTvFlash(true);
        } else {
          setSavedMoviesFlash(true);
        }
      },
      onError: () => {
        setErrorAxis(axis);
      },
    });
  };

  const saveTvErrorMessage = saveTv.error instanceof Error ? saveTv.error.message : "Save failed.";
  const saveMoviesErrorMessage = saveMovies.error instanceof Error ? saveMovies.error.message : "Save failed.";

  return (
    <section
      className="mm-card mm-dash-card mm-fetcher-module-surface"
      aria-labelledby="mm-fetcher-fi-policy-heading"
      data-testid="fetcher-failed-imports-cleanup-policy"
    >
      <h2 id="mm-fetcher-fi-policy-heading" className="mm-card__title">
        Failed import actions
      </h2>

      {q.isPending ? (
        <p
          className="mm-card__body mm-card__body--tight mt-1 text-sm text-[var(--mm-text3)]"
          data-testid="fetcher-failed-imports-policy-loading"
        >
          Loading queue action settings…
        </p>
      ) : q.isError ? (
        <p
          className="mm-card__body mm-card__body--tight mt-1 text-sm text-red-400"
          data-testid="fetcher-failed-imports-policy-error"
          role="alert"
        >
          {q.error instanceof Error ? q.error.message : "Could not load queue action settings."}
        </p>
      ) : q.data && movies && tvShows ? (
        <div className="mm-card__body mm-card__body--tight mt-1 w-full min-w-0">
          {axes === "tv" ? (
            <CleanupAxisCard
              value={tvShows}
              onChange={setTvShows}
              runIntervalDraft={tvRunIntervalDraft}
              setRunIntervalDraft={setTvRunIntervalDraft}
              optionsDisabled={!canEdit || saveTv.isPending}
              optionsGroupId="mm-fi-cleanup-tv-options"
              canEdit={canEdit}
              saveLabel={FETCHER_FI_POLICY_SAVE_SONARR}
              saveTestId="fetcher-failed-imports-policy-save-tv"
              savedTestId="fetcher-failed-imports-policy-saved-tv"
              onSave={() => mutateSave("tv")}
              saveDisabled={!dirtyTv || saveTv.isPending}
              savePending={saveTv.isPending}
              showSaved={savedTvFlash && !dirtyTv && !saveTv.isPending}
              showError={Boolean(saveTv.isError && errorAxis === "tv")}
              errorMessage={saveTvErrorMessage}
            />
          ) : (
            <CleanupAxisCard
              value={movies}
              onChange={setMovies}
              runIntervalDraft={moviesRunIntervalDraft}
              setRunIntervalDraft={setMoviesRunIntervalDraft}
              optionsDisabled={!canEdit || saveMovies.isPending}
              optionsGroupId="mm-fi-cleanup-movies-options"
              canEdit={canEdit}
              saveLabel={FETCHER_FI_POLICY_SAVE_RADARR}
              saveTestId="fetcher-failed-imports-policy-save-movies"
              savedTestId="fetcher-failed-imports-policy-saved-movies"
              onSave={() => mutateSave("movies")}
              saveDisabled={!dirtyMovies || saveMovies.isPending}
              savePending={saveMovies.isPending}
              showSaved={savedMoviesFlash && !dirtyMovies && !saveMovies.isPending}
              showError={Boolean(saveMovies.isError && errorAxis === "movies")}
              errorMessage={saveMoviesErrorMessage}
            />
          )}
          {!canEdit ? (
            <p className="mt-4 text-sm text-[var(--mm-text3)]">{FETCHER_FI_POLICY_VIEWER_NOTE}</p>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
