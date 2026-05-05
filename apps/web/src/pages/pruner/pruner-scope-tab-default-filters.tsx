import { PrunerGenreMultiSelect } from "./pruner-genre-multi-select";
import {
  PrunerPeopleRoleCheckboxes,
  type PrunerPeopleRoleId,
} from "./pruner-people-roles";
import type { PrunerServerInstance } from "../../lib/pruner/api";

type ScopeRow = PrunerServerInstance["scopes"][number] | undefined;

type PrunerScopeTabDefaultFiltersProps = {
  scope: "tv" | "movies";
  instanceId: number;
  libraryTabPhrase: string;
  isPlex: boolean;
  busy: boolean;
  showInteractiveControls: boolean;
  scopeRow: ScopeRow;
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
};

export function PrunerScopeTabDefaultFilters({
  scope,
  instanceId,
  libraryTabPhrase,
  isPlex,
  busy,
  showInteractiveControls,
  scopeRow,
  genreSelection,
  setGenreSelection,
  saveGenreFilters,
  genreMsg,
  peopleText,
  setPeopleText,
  peopleRoles,
  setPeopleRoles,
  savePeopleFilters,
  peopleMsg,
  yearMinStr,
  setYearMinStr,
  yearMaxStr,
  setYearMaxStr,
  savePreviewYearBounds,
  yearMsg,
  studioText,
  setStudioText,
  saveStudioPreviewFilters,
  studioMsg,
  collectionText,
  setCollectionText,
  saveCollectionPreviewFilters,
  collectionMsg,
}: PrunerScopeTabDefaultFiltersProps) {
  if (!scopeRow) return null;
  return (
    <>
      <div
        className="space-y-2 text-sm text-[var(--mm-text)]"
        data-testid="pruner-genre-filters-panel"
      >
        <p className="text-sm font-semibold text-[var(--mm-text)]">
          Optional genres (this {libraryTabPhrase} only)
        </p>
        <p className="text-xs text-[var(--mm-text2)]">
          Pick from the list below; leave none selected to include every genre.
        </p>
        {isPlex ? (
          <p
            className="text-xs text-amber-100/90"
            data-testid="pruner-plex-genre-empty-preview-note"
          >
            If a scan finishes with <strong>nothing listed</strong> while genres
            are selected, nothing in this pass matched both the rule and those
            genres — it does not prove your library is already clean.
          </p>
        ) : null}
        {showInteractiveControls ? (
          <div className="space-y-2">
            <PrunerGenreMultiSelect
              value={genreSelection}
              onChange={setGenreSelection}
              disabled={busy}
              testId={`pruner-genre-multiselect-${instanceId}-${scope}`}
              filterHelperText=""
            />
            <button
              type="button"
              className="rounded-md border border-[var(--mm-border)] px-3 py-1 text-sm font-medium text-[var(--mm-text)] disabled:opacity-50"
              disabled={busy}
              onClick={() => void saveGenreFilters()}
            >
              Save genre filters
            </button>
            {genreMsg ? (
              <p className="text-xs text-green-600">{genreMsg}</p>
            ) : null}
          </div>
        ) : (
          <p className="text-xs text-[var(--mm-text2)]">
            Current filters:{" "}
            <strong>
              {(scopeRow.preview_include_genres ?? []).length
                ? scopeRow.preview_include_genres.join(", ")
                : "none"}
            </strong>
            . Sign in as an operator to edit.
          </p>
        )}
      </div>
      <div
        className="space-y-2 text-sm text-[var(--mm-text)]"
        data-testid="pruner-people-filters-panel"
      >
        <p className="text-sm font-semibold text-[var(--mm-text)]">
          Optional cast and crew names (this {libraryTabPhrase} only)
        </p>
        <p className="text-xs text-[var(--mm-text2)]">
          Comma-separated full names.
        </p>
        {isPlex ? (
          <p
            className="text-xs text-[var(--mm-text2)]"
            data-testid="pruner-people-plex-note"
          >
            Plex: names apply to broken-poster scans plus the movie scans above.
            They come from cast, writer, and director lines on each title.
          </p>
        ) : (
          <p
            className="text-xs text-[var(--mm-text2)]"
            data-testid="pruner-people-jf-emby-note"
          >
            Jellyfin / Emby: names come from each item’s People list on the
            server and apply to every scan for this library.
          </p>
        )}
        {showInteractiveControls ? (
          <div className="space-y-3">
            <textarea
              rows={5}
              className="mm-input min-h-[7rem] w-full resize-y font-sans text-sm"
              placeholder="e.g. Alex Carter, Jordan Lee (comma or one per line)"
              value={peopleText}
              disabled={busy}
              onChange={(e) => setPeopleText(e.target.value)}
            />
            <p className="text-xs text-[var(--mm-text3)]">
              Leave blank to use no name filter.
            </p>
            <PrunerPeopleRoleCheckboxes
              value={peopleRoles}
              onChange={setPeopleRoles}
              disabled={busy}
              variant={isPlex ? "plex" : "emby-jellyfin"}
              testId={`pruner-people-filters-roles-${instanceId}-${scope}`}
            />
            <button
              type="button"
              className="rounded-md border border-[var(--mm-border)] px-3 py-1 text-sm font-medium text-[var(--mm-text)] disabled:opacity-50"
              disabled={busy}
              onClick={() => void savePeopleFilters()}
            >
              Save people filters
            </button>
            {peopleMsg ? (
              <p className="text-xs text-green-600">{peopleMsg}</p>
            ) : null}
          </div>
        ) : (
          <p className="text-xs text-[var(--mm-text2)]">
            Current people filters:{" "}
            <strong>
              {(scopeRow.preview_include_people ?? []).length
                ? scopeRow.preview_include_people.join(", ")
                : "none"}
            </strong>
            . Sign in as an operator to edit.
          </p>
        )}
      </div>
      <div
        className="space-y-2 rounded-md border border-[var(--mm-border)] bg-[var(--mm-card-bg)] px-4 py-3 text-sm text-[var(--mm-text)]"
        data-testid="pruner-year-filters-panel"
      >
        <p className="text-sm font-semibold text-[var(--mm-text)]">
          Optional release years (this {libraryTabPhrase} only)
        </p>
        <p className="text-xs text-[var(--mm-text2)]">
          Inclusive 1900-2100. Blank means open-ended.
        </p>
        {showInteractiveControls ? (
          <div className="flex flex-wrap items-end gap-2">
            <label className="text-xs text-[var(--mm-text2)]">
              Min year
              <input
                type="number"
                min={1900}
                max={2100}
                className="ml-1 w-24 rounded border border-[var(--mm-border)] bg-[var(--mm-surface2)] px-2 py-1 text-sm text-[var(--mm-text)]"
                value={yearMinStr}
                disabled={busy}
                onChange={(e) => setYearMinStr(e.target.value)}
              />
            </label>
            <label className="text-xs text-[var(--mm-text2)]">
              Max year
              <input
                type="number"
                min={1900}
                max={2100}
                className="ml-1 w-24 rounded border border-[var(--mm-border)] bg-[var(--mm-surface2)] px-2 py-1 text-sm text-[var(--mm-text)]"
                value={yearMaxStr}
                disabled={busy}
                onChange={(e) => setYearMaxStr(e.target.value)}
              />
            </label>
            <button
              type="button"
              className="rounded-md border border-[var(--mm-border)] px-3 py-1 text-sm font-medium text-[var(--mm-text)] disabled:opacity-50"
              disabled={busy}
              onClick={() => void savePreviewYearBounds()}
            >
              Save year bounds
            </button>
            {yearMsg ? (
              <p className="w-full text-xs text-green-600">{yearMsg}</p>
            ) : null}
          </div>
        ) : (
          <p className="text-xs text-[var(--mm-text2)]">
            Current bounds:{" "}
            <strong>
              {scopeRow.preview_year_min ?? "—"} to{" "}
              {scopeRow.preview_year_max ?? "—"}
            </strong>
            . Sign in as an operator to edit.
          </p>
        )}
      </div>
      <div
        className="space-y-2 rounded-md border border-[var(--mm-border)] bg-[var(--mm-card-bg)] px-4 py-3 text-sm text-[var(--mm-text)]"
        data-testid="pruner-studio-preview-panel"
      >
        <p className="text-sm font-semibold text-[var(--mm-text)]">
          Optional studios (this {libraryTabPhrase} only)
        </p>
        <p className="text-xs text-[var(--mm-text2)]">
          Comma-separated studio names.
        </p>
        {showInteractiveControls ? (
          <div className="space-y-2">
            <input
              type="text"
              className="w-full rounded border border-[var(--mm-border)] bg-[var(--mm-surface2)] px-2 py-1 text-sm text-[var(--mm-text)]"
              placeholder="e.g. Warner Bros., BBC"
              value={studioText}
              disabled={busy}
              onChange={(e) => setStudioText(e.target.value)}
            />
            <button
              type="button"
              className="rounded-md border border-[var(--mm-border)] px-3 py-1 text-sm font-medium text-[var(--mm-text)] disabled:opacity-50"
              disabled={busy}
              onClick={() => void saveStudioPreviewFilters()}
            >
              Save studio filters
            </button>
            {studioMsg ? (
              <p className="text-xs text-green-600">{studioMsg}</p>
            ) : null}
          </div>
        ) : (
          <p className="text-xs text-[var(--mm-text2)]">
            Current studio filters:{" "}
            <strong>
              {(scopeRow.preview_include_studios ?? []).length
                ? scopeRow.preview_include_studios.join(", ")
                : "none"}
            </strong>
            .
          </p>
        )}
      </div>
      {isPlex ? (
        <div
          className="space-y-2 rounded-md border border-[var(--mm-border)] bg-[var(--mm-card-bg)] px-4 py-3 text-sm text-[var(--mm-text)]"
          data-testid="pruner-collection-preview-panel"
        >
          <p className="text-sm font-semibold text-[var(--mm-text)]">
            Optional Plex movie collections
          </p>
          <p className="text-xs text-[var(--mm-text2)]">
            Comma-separated collection names.
          </p>
          {showInteractiveControls ? (
            <div className="space-y-2">
              <input
                type="text"
                className="w-full rounded border border-[var(--mm-border)] bg-[var(--mm-surface2)] px-2 py-1 text-sm text-[var(--mm-text)]"
                placeholder="e.g. Marvel Cinematic Universe"
                value={collectionText}
                disabled={busy}
                onChange={(e) => setCollectionText(e.target.value)}
              />
              <button
                type="button"
                className="rounded-md border border-[var(--mm-border)] px-3 py-1 text-sm font-medium text-[var(--mm-text)] disabled:opacity-50"
                disabled={busy}
                onClick={() => void saveCollectionPreviewFilters()}
              >
                Save collection filters
              </button>
              {collectionMsg ? (
                <p className="text-xs text-green-600">{collectionMsg}</p>
              ) : null}
            </div>
          ) : (
            <p className="text-xs text-[var(--mm-text2)]">
              Current collection filters:{" "}
              <strong>
                {(scopeRow.preview_include_collections ?? []).length
                  ? scopeRow.preview_include_collections.join(", ")
                  : "none"}
              </strong>
              .
            </p>
          )}
        </div>
      ) : null}
    </>
  );
}
