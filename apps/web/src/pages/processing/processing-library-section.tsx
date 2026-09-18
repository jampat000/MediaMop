/**
 * The **Library** tab (issues #505 and #568). It shows what a library holds and the state of it, with its own
 * sub-navigation — Overview, Files, Codecs, Languages, Problems — over one library at a time.
 *
 * Every total and breakdown is a SQL aggregate from the server (`library-overview`), and the Files table is
 * server-sorted, server-filtered and paged (`library-files`), so a library of thousands of files never has to
 * reach the browser to be counted (#568 point 7).
 */
import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { LibraryRemovalConfirmationDialog } from "../../components/processing/library-removal-confirmation-dialog";
import { PageLoading } from "../../components/shared/page-loading";
import {
  WorkspaceTabList,
  type WorkspaceTabOption,
} from "../../components/shared/workspace-shell";
import { useMeQuery } from "../../lib/auth/queries";
import {
  formatBytes,
  LIBRARY_FACET_LABELS,
  type LibraryConfirmationRequired,
  type LibraryFacet,
  type LibraryFileFilters,
  type LibraryProblemKind,
  type LibraryScanInfo,
} from "../../lib/processing/library-api";
import {
  useCleanLibraryFiles,
  useLibraryFilesQuery,
  useLibraryOverviewQuery,
  useLibraryProblemsQuery,
  useLibraryRedownloadsQuery,
  useLibrarySettingsQuery,
  useRequestLibraryRedownload,
  useSaveLibraryFolders,
  useSaveLibraryPreflightSettings,
  useSetLibrarySchedule,
  useTriggerLibraryScan,
} from "../../lib/processing/library-queries";
import { useProcessingLibrariesQuery } from "../../lib/processing/libraries-queries";
import {
  mmActionButtonClass,
  mmSelectFieldClass,
} from "../../lib/ui/mm-control-roles";
import { LibraryBreakdownTable } from "./library/library-breakdown-table";
import { LibraryFilesView } from "./library/library-files-view";
import { LibraryOverviewView } from "./library/library-overview-view";
import { LibraryProblemsView } from "./library/library-problems-view";
import { LibraryRedownloadsPanel } from "./library/library-redownloads-panel";
import { LibrarySettingsPanel } from "./library/library-settings-panel";

/** The sub-views, in the order the tab strip shows them. */
export type LibraryViewId =
  "overview" | "files" | "codecs" | "languages" | "problems";

const LIBRARY_VIEWS = [
  { id: "overview", label: "Overview" },
  { id: "files", label: "Files" },
  { id: "codecs", label: "Codecs" },
  { id: "languages", label: "Languages" },
  { id: "problems", label: "Problems" },
] as const satisfies readonly WorkspaceTabOption<LibraryViewId>[];

/** The facets each of the two breakdown sub-views shows. */
const CODEC_FACETS: LibraryFacet[] = ["video_codec", "resolution", "audio"];
const LANGUAGE_FACETS: LibraryFacet[] = ["audio_language", "subtitle_language"];

/**
 * The sub-view named by `?view=`. Anything unknown (an old bookmark, a typo) falls back to Overview rather
 * than rendering nothing.
 */
export function libraryViewFromQuery(value: string | null): LibraryViewId {
  const allowed = LIBRARY_VIEWS.map((view) => view.id) as LibraryViewId[];
  return allowed.includes(value as LibraryViewId)
    ? (value as LibraryViewId)
    : "overview";
}

function canEdit(role: string | undefined): boolean {
  return role === "operator" || role === "admin";
}

function scanSentence(
  scan: LibraryScanInfo | null | undefined,
  hasFiles: boolean,
): string {
  if (!scan) return "This library has not been scanned yet.";
  if (scan.running) return "Scanning now…";
  if (scan.generated_at) {
    return `Last scanned ${new Date(scan.generated_at * 1000).toLocaleString()}.`;
  }
  // Job-row retention can prune the scan job long after it ran, taking the timestamp with it but not the
  // file index it produced (#557). Files without a date means that, not a scan that failed.
  return hasFiles
    ? "Scanned, though Weir no longer has a record of when."
    : "The last scan did not finish.";
}

const SCAN_EXPLANATION =
  "A scan reads every file in this library's folders and works out, with this library's rules, whether each one already matches, would change, or cannot be processed. It never writes to a file.";

export function ProcessingLibrarySection() {
  const me = useMeQuery();
  const editable = canEdit(me.data?.role);
  const libraries = useProcessingLibrariesQuery();
  const [libraryId, setLibraryId] = useState<number | null>(null);
  const [searchParams, setSearchParams] = useSearchParams();
  const [view, setView] = useState<LibraryViewId>(() =>
    libraryViewFromQuery(searchParams.get("view")),
  );

  useEffect(() => {
    setView(libraryViewFromQuery(searchParams.get("view")));
  }, [searchParams]);

  useEffect(() => {
    if (libraryId === null && libraries.data && libraries.data.length > 0) {
      setLibraryId(libraries.data[0].id);
    }
  }, [libraries.data, libraryId]);

  const selectView = (next: LibraryViewId) => {
    setView(next);
    const params = new URLSearchParams(searchParams);
    if (next === "overview") params.delete("view");
    else params.set("view", next);
    setSearchParams(params, { replace: true });
  };

  const settings = useLibrarySettingsQuery(libraryId ?? 0, libraryId !== null);
  const overview = useLibraryOverviewQuery(libraryId ?? 0, libraryId !== null);
  const problems = useLibraryProblemsQuery(
    libraryId ?? 0,
    libraryId !== null && view === "problems",
  );
  const saveFolders = useSaveLibraryFolders(libraryId ?? 0);
  const savePreflight = useSaveLibraryPreflightSettings(libraryId ?? 0);
  const scheduleMutation = useSetLibrarySchedule(libraryId ?? 0);
  const scanMutation = useTriggerLibraryScan(libraryId ?? 0);

  const [folderError, setFolderError] = useState<string | null>(null);
  const [preflightError, setPreflightError] = useState<string | null>(null);
  const [cleanNotice, setCleanNotice] = useState<{
    queued: number;
    skipped: string[];
    warnings: string[];
  } | null>(null);

  const [filters, setFilters] = useState<LibraryFileFilters>({});
  const files = useLibraryFilesQuery(
    libraryId ?? 0,
    filters,
    libraryId !== null && view === "files",
  );

  const [selected, setSelected] = useState<Set<string>>(new Set());
  const cleanMutation = useCleanLibraryFiles(libraryId ?? 0);
  const redownloads = useLibraryRedownloadsQuery(
    libraryId ?? 0,
    libraryId !== null && view === "problems",
  );
  const redownloadMutation = useRequestLibraryRedownload(libraryId ?? 0);
  const [redownloadError, setRedownloadError] = useState<string | null>(null);
  const [cleanConfirmation, setCleanConfirmation] =
    useState<LibraryConfirmationRequired | null>(null);
  const [cleanError, setCleanError] = useState<string | null>(null);
  const [scheduleConfirmation, setScheduleConfirmation] =
    useState<LibraryConfirmationRequired | null>(null);
  const [scheduleError, setScheduleError] = useState<string | null>(null);

  const selectedPaths = useMemo(() => [...selected], [selected]);
  const scan = overview.data?.scan ?? files.data?.scan ?? null;
  const scanning = scanMutation.isPending || scan?.running === true;
  const nothingScanned = (overview.data?.totals.files ?? 0) === 0;

  if (libraries.isLoading) {
    return <PageLoading label="Loading libraries…" />;
  }

  if (!libraries.data || libraries.data.length === 0) {
    return (
      <p className="text-sm text-[var(--mm-text2)]">
        Add a library first, under the Libraries tab.
      </p>
    );
  }

  const addFolder = (folder: string) => {
    if (!settings.data || libraryId === null) return;
    setFolderError(null);
    saveFolders.mutate(
      Array.from(new Set([...settings.data.library_folders, folder])),
      { onError: (error) => setFolderError((error as Error).message) },
    );
  };

  const removeFolder = (folder: string) => {
    if (!settings.data || libraryId === null) return;
    saveFolders.mutate(
      settings.data.library_folders.filter((f) => f !== folder),
      { onError: (error) => setFolderError((error as Error).message) },
    );
  };

  const runClean = (confirm: boolean) => {
    if (selectedPaths.length === 0 || libraryId === null) return;
    setCleanError(null);
    cleanMutation.mutate(
      { paths: selectedPaths, confirm },
      {
        onSuccess: (result) => {
          if (result.kind === "confirmation_required") {
            setCleanConfirmation(result);
          } else {
            setCleanConfirmation(null);
            setSelected(new Set());
            setCleanNotice(
              result.skipped_paths.length > 0 || result.warnings.length > 0
                ? {
                    queued: result.queued,
                    skipped: result.skipped_paths,
                    warnings: result.warnings,
                  }
                : null,
            );
          }
        },
        onError: (error) => setCleanError((error as Error).message),
      },
    );
  };

  const togglePreflightSetting = (
    field: "clean_hardlinked_files" | "skip_if_manager_would_redownload",
    next: boolean,
  ) => {
    if (!settings.data) return;
    setPreflightError(null);
    savePreflight.mutate(
      { library_folders: settings.data.library_folders, [field]: next },
      { onError: (error) => setPreflightError((error as Error).message) },
    );
  };

  const toggleSchedule = (enabled: boolean, confirm: boolean) => {
    setScheduleError(null);
    scheduleMutation.mutate(
      { enabled, confirm },
      {
        onSuccess: (result) =>
          setScheduleConfirmation("kind" in result ? result : null),
        onError: (error) => setScheduleError((error as Error).message),
      },
    );
  };

  const toggleSelected = (path: string) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });

  const selectAllOnPage = (paths: string[], select: boolean) =>
    setSelected((prev) => {
      const next = new Set(prev);
      for (const path of paths) {
        if (select) next.add(path);
        else next.delete(path);
      }
      return next;
    });

  /** A "show files" link: jump to the Files sub-view with one facet pinned. */
  const showFilesForFacet = (facet: LibraryFacet, value: string) => {
    setFilters((current) => ({
      ...current,
      facets: { ...current.facets, [facet]: value },
      problem: undefined,
      page: 1,
    }));
    selectView("files");
  };

  const showFilesForProblem = (kind: LibraryProblemKind) => {
    setFilters((current) => ({ ...current, problem: kind, page: 1 }));
    selectView("files");
  };

  const emptyState = (
    <section
      className="mm-bubble space-y-2 p-4"
      data-testid="library-empty-state"
    >
      <h3 className="text-sm font-semibold text-[var(--mm-text1)]">
        Nothing scanned yet
      </h3>
      <p className="max-w-prose text-sm text-[var(--mm-text2)]">
        {SCAN_EXPLANATION}
      </p>
      {settings.data && settings.data.library_folders.length === 0 ? (
        <p className="text-sm text-[var(--mm-text3)]">
          Add at least one library folder below, then scan.
        </p>
      ) : null}
      {editable ? (
        <button
          type="button"
          className={mmActionButtonClass({
            variant: "primary",
            disabled: scanning || settings.data?.library_folders.length === 0,
          })}
          disabled={scanning || settings.data?.library_folders.length === 0}
          onClick={() => scanMutation.mutate()}
        >
          {scanning ? "Scanning…" : "Scan now"}
        </button>
      ) : null}
    </section>
  );

  const totals = overview.data?.totals;

  return (
    <div className="mm-bubble-stack flex w-full min-w-0 flex-col gap-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <label className="block max-w-md text-sm font-medium text-[var(--mm-text1)]">
          Library
          <select
            className={mmSelectFieldClass}
            value={libraryId ?? ""}
            onChange={(e) => {
              setLibraryId(Number(e.target.value));
              setSelected(new Set());
              setFilters({});
            }}
          >
            {libraries.data.map((library) => (
              <option key={library.id} value={library.id}>
                {library.name}
              </option>
            ))}
          </select>
        </label>

        <div className="flex flex-wrap items-center gap-3">
          <span
            className="text-sm text-[var(--mm-text2)]"
            data-testid="library-scan-state"
          >
            {scanSentence(scan, !nothingScanned)}
            {totals && totals.files > 0
              ? ` ${totals.files} file(s), ${formatBytes(totals.size_bytes)}.`
              : ""}
          </span>
          {editable ? (
            <button
              type="button"
              className={mmActionButtonClass({
                variant: "secondary",
                disabled:
                  scanning || settings.data?.library_folders.length === 0,
              })}
              disabled={scanning || settings.data?.library_folders.length === 0}
              onClick={() => scanMutation.mutate()}
              data-testid="library-scan-button"
            >
              {scanning ? "Scanning…" : "Scan now"}
            </button>
          ) : null}
        </div>
      </div>

      {scan?.errors?.length ? (
        <div
          className="mm-bubble space-y-1 p-3 text-sm text-[var(--mm-status-warning-text)]"
          data-testid="library-scan-errors"
        >
          {scan.errors.map((error) => (
            <p key={error}>{error}</p>
          ))}
        </div>
      ) : null}

      <WorkspaceTabList
        tabs={LIBRARY_VIEWS}
        activeId={view}
        onSelect={selectView}
        ariaLabel="Library sections"
        idPrefix="library-view-tab"
        panelId="library-view-panel"
        dataTestId="library-view-tabs"
      />

      <section
        id="library-view-panel"
        role="tabpanel"
        aria-labelledby={`library-view-tab-${view}`}
        className="flex w-full min-w-0 flex-col gap-4"
      >
        {view === "overview" ? (
          <>
            {overview.isLoading ? (
              <PageLoading label="Loading this library…" />
            ) : null}
            {overview.data ? (
              <LibraryOverviewView
                overview={overview.data}
                onShowFiles={showFilesForFacet}
                onOpenProblems={() => selectView("problems")}
                emptyState={emptyState}
              />
            ) : null}
            {settings.data ? (
              <LibrarySettingsPanel
                settings={settings.data}
                editable={editable}
                savingFolders={saveFolders.isPending}
                savingPreflight={savePreflight.isPending}
                savingSchedule={scheduleMutation.isPending}
                folderError={folderError}
                preflightError={preflightError}
                scheduleError={scheduleError}
                onAddFolder={addFolder}
                onRemoveFolder={removeFolder}
                onToggleSchedule={(enabled) => toggleSchedule(enabled, false)}
                onTogglePreflight={togglePreflightSetting}
              />
            ) : null}
          </>
        ) : null}

        {view === "files" && libraryId !== null ? (
          <>
            <LibraryFilesView
              libraryId={libraryId}
              editable={editable}
              filters={filters}
              onFiltersChange={setFilters}
              files={files.data}
              loading={files.isLoading}
              breakdowns={overview.data?.breakdowns}
              selected={selected}
              onToggleSelected={toggleSelected}
              onSelectAllOnPage={selectAllOnPage}
              onClean={() => runClean(false)}
              cleaning={cleanMutation.isPending}
              cleanError={cleanError}
              emptyState={
                nothingScanned ? (
                  emptyState
                ) : (
                  <p className="text-sm text-[var(--mm-text3)]">
                    No file matches these filters.
                  </p>
                )
              }
            />
            {cleanNotice ? (
              <div
                className="mm-bubble space-y-1 p-3 text-sm text-[var(--mm-text2)]"
                data-testid="library-clean-notice"
              >
                <p>
                  {cleanNotice.queued} file(s) queued to clean
                  {cleanNotice.skipped.length > 0
                    ? `; ${cleanNotice.skipped.length} skipped (still shared with a download)`
                    : ""}
                  .
                </p>
                {cleanNotice.warnings.map((warning) => (
                  <p key={warning} className="text-xs text-[var(--mm-text3)]">
                    {warning}
                  </p>
                ))}
              </div>
            ) : null}
          </>
        ) : null}

        {view === "codecs" || view === "languages" ? (
          <>
            {overview.isLoading ? (
              <PageLoading label="Loading breakdowns…" />
            ) : null}
            {overview.data && nothingScanned ? emptyState : null}
            {overview.data && !nothingScanned
              ? (view === "codecs" ? CODEC_FACETS : LANGUAGE_FACETS).map(
                  (facet) => (
                    <LibraryBreakdownTable
                      key={facet}
                      facet={facet}
                      heading={LIBRARY_FACET_LABELS[facet]}
                      rows={overview.data.breakdowns[facet] ?? []}
                      onShowFiles={showFilesForFacet}
                      emptyMessage="Nothing scanned carries this yet."
                    />
                  ),
                )
              : null}
          </>
        ) : null}

        {view === "problems" ? (
          <>
            {problems.isLoading ? (
              <PageLoading label="Loading problems…" />
            ) : null}
            {problems.data ? (
              <LibraryProblemsView
                groups={problems.data.groups}
                onShowFiles={showFilesForProblem}
                emptyState={
                  nothingScanned ? (
                    emptyState
                  ) : (
                    <p
                      className="text-sm text-[var(--mm-text2)]"
                      data-testid="library-no-problems"
                    >
                      Nothing is in the way: every file Weir found is either
                      already right or ready to clean.
                    </p>
                  )
                }
              />
            ) : null}
            <LibraryRedownloadsPanel
              titles={redownloads.data?.titles ?? []}
              editable={editable}
              requesting={redownloadMutation.isPending}
              error={redownloadError}
              onRequest={(path, done) => {
                setRedownloadError(null);
                redownloadMutation.mutate(path, {
                  onSuccess: done,
                  onError: (error) =>
                    setRedownloadError((error as Error).message),
                });
              }}
            />
          </>
        ) : null}
      </section>

      {cleanConfirmation ? (
        <LibraryRemovalConfirmationDialog
          filesCount={cleanConfirmation.files_count}
          tracksCount={cleanConfirmation.tracks_count}
          estimatedBytesSaved={cleanConfirmation.estimated_bytes_saved}
          warnings={cleanConfirmation.warnings ?? []}
          busy={cleanMutation.isPending}
          error={cleanError}
          confirmLabel="Clean"
          onCancel={() => setCleanConfirmation(null)}
          onConfirm={() => runClean(true)}
        />
      ) : null}

      {scheduleConfirmation ? (
        <LibraryRemovalConfirmationDialog
          filesCount={scheduleConfirmation.files_count}
          tracksCount={scheduleConfirmation.tracks_count}
          estimatedBytesSaved={scheduleConfirmation.estimated_bytes_saved}
          warnings={scheduleConfirmation.warnings ?? []}
          busy={scheduleMutation.isPending}
          error={scheduleError}
          confirmLabel="Turn schedule on"
          onCancel={() => setScheduleConfirmation(null)}
          onConfirm={() => toggleSchedule(true, true)}
        />
      ) : null}
    </div>
  );
}
