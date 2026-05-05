import type { Dispatch, SetStateAction } from "react";
import type { PrunerServerInstance } from "../../lib/pruner/api";
import { PrunerScopeTabDefaultActions } from "./pruner-scope-tab-default-actions";
import { PrunerScopeTabDefaultFilters } from "./pruner-scope-tab-default-filters";
import { PrunerScopeTabDefaultIntro } from "./pruner-scope-tab-default-intro";
import { PrunerScopeTabDefaultRulesMovies } from "./pruner-scope-tab-default-rules-movies";
import { PrunerScopeTabDefaultRulesTv } from "./pruner-scope-tab-default-rules-tv";
import type { PrunerPeopleRoleId } from "./pruner-people-roles";

type ScopeRow = PrunerServerInstance["scopes"][number] | undefined;

type PrunerScopeTabDefaultLayoutProps = {
  instanceId: number;
  scope: "tv" | "movies";
  disabledMode?: boolean;
  label: string;
  libraryTabPhrase: string;
  isPlex: boolean;
  showInteractiveControls: boolean;
  busy: boolean;
  scopeRow: ScopeRow;
  previewMaxItems: number;
  setPreviewMaxItems: (value: number) => void;
  previewMaxItemsMsg: string | null;
  savePreviewMaxItemsSettings: () => Promise<void>;
  genreSelection: string[];
  setGenreSelection: (value: string[]) => void;
  saveGenreFilters: () => Promise<void>;
  genreMsg: string | null;
  peopleText: string;
  setPeopleText: (value: string) => void;
  peopleRoles: PrunerPeopleRoleId[];
  setPeopleRoles: (value: PrunerPeopleRoleId[]) => void;
  savePeopleFilters: () => Promise<void>;
  peopleMsg: string | null;
  yearMinStr: string;
  setYearMinStr: (value: string) => void;
  yearMaxStr: string;
  setYearMaxStr: (value: string) => void;
  savePreviewYearBounds: () => Promise<void>;
  yearMsg: string | null;
  studioText: string;
  setStudioText: (value: string) => void;
  saveStudioPreviewFilters: () => Promise<void>;
  studioMsg: string | null;
  collectionText: string;
  setCollectionText: (value: string) => void;
  saveCollectionPreviewFilters: () => Promise<void>;
  collectionMsg: string | null;
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
  runPreview: () => Promise<void>;
  loadJsonFor: (runUuid?: string | null) => Promise<void>;
  schedEnabled: boolean;
  setSchedEnabled: (value: boolean) => void;
  schedIntervalSec: number;
  schedIntervalMinDraft: string | null;
  setSchedIntervalMinDraft: (value: string | null) => void;
  schedHoursLimited: boolean;
  setSchedHoursLimited: (value: boolean) => void;
  schedDays: string;
  setSchedDays: (value: string) => void;
  schedStart: string;
  setSchedStart: (value: string) => void;
  schedEnd: string;
  setSchedEnd: (value: string) => void;
  fmt: ReturnType<typeof import("../../lib/ui/mm-format-date").useAppDateFormatter>;
  schedMsg: string | null;
  saveSchedule: () => Promise<void>;
  runs: unknown;
  runsLoading: boolean;
  runsError: Error | null;
  canOperate: boolean;
  provider: PrunerServerInstance["provider"] | undefined;
  ruleFamilyColumnLabel: (id: string) => string;
  openApplyModal: (runUuid: string) => void;
  applyModalRunId: string | null;
  applySnapshotOperatorLabel: string | null;
  applyEligibilityLoading: boolean;
  applyEligibilityError: Error | null;
  applyEligibilityData: unknown;
  applySnapshotConfirmed: boolean;
  setApplySnapshotConfirmed: Dispatch<SetStateAction<boolean>>;
  closeApplyModal: () => void;
  confirmApplyFromSnapshot: () => Promise<void>;
  err: string | null;
  preview: string | null;
  jsonPreview: string | null;
};

export function PrunerScopeTabDefaultLayout(props: PrunerScopeTabDefaultLayoutProps) {
  return (
    <>
      <PrunerScopeTabDefaultIntro
        scope={props.scope}
        label={props.label}
        libraryTabPhrase={props.libraryTabPhrase}
        disabledMode={props.disabledMode}
        showInteractiveControls={props.showInteractiveControls}
        busy={props.busy}
        isPlex={props.isPlex}
        previewMaxItems={props.previewMaxItems}
        setPreviewMaxItems={props.setPreviewMaxItems}
        previewMaxItemsMsg={props.previewMaxItemsMsg}
        scopePreviewMaxItems={props.scopeRow?.preview_max_items}
        savePreviewMaxItemsSettings={props.savePreviewMaxItemsSettings}
      />
      <PrunerScopeTabDefaultFilters {...props} />
      {props.isPlex ? (
        <div
          className="rounded-md border border-amber-600/40 bg-amber-950/20 px-3 py-2 text-xs text-[var(--mm-text)]"
          role="status"
          data-testid="pruner-plex-other-rules-note"
        >
          <p className="font-medium text-amber-100">
            {props.scope === "movies"
              ? "Plex does not support watched-TV or never-started cleanup on the Movies tab."
              : "Plex does not support watched-TV or never-started TV cleanup on the TV tab."}
          </p>
        </div>
      ) : null}
      {!props.isPlex ? <PrunerScopeTabDefaultRulesTv {...props} /> : null}
      <div>
        <h3
          className="text-base font-semibold text-[var(--mm-text)]"
          data-testid="pruner-rules-section-heading"
        >
          Cleanup rules
        </h3>
        <p className="text-xs text-[var(--mm-text2)]">
          Turn a rule on, save, then run its scan when you are ready.
        </p>
      </div>
      <PrunerScopeTabDefaultRulesMovies {...props} />
      <PrunerScopeTabDefaultActions {...props} />
    </>
  );
}
