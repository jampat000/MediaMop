/**
 * Library mode (#505): clean files already in a library, in place. Weir server (.NET) only.
 */
import { useEffect, useMemo, useState } from "react";

import { LibraryRemovalConfirmationDialog } from "../../components/refiner/library-removal-confirmation-dialog";
import { PageLoading } from "../../components/shared/page-loading";
import { useMeQuery } from "../../lib/auth/queries";
import {
  formatBytes,
  LIBRARY_FILE_CLASSIFICATION_LABELS,
  LIBRARY_MANAGER_FILTER_OPTIONS,
  type LibraryConfirmationRequired,
  type LibraryFileClassification,
} from "../../lib/refiner/library-api";
import {
  useCleanLibraryFiles,
  useLibraryFilesQuery,
  useLibraryRedownloadsQuery,
  useLibrarySettingsQuery,
  useRequestLibraryRedownload,
  useSaveLibraryFolders,
  useSaveLibraryPreflightSettings,
  useSetLibrarySchedule,
  useTriggerLibraryScan,
} from "../../lib/refiner/library-queries";
import { useRefinerLibrariesQuery } from "../../lib/refiner/libraries-queries";
import {
  mmActionButtonClass,
  mmCheckboxControlClass,
  mmEditableTextFieldClass,
  mmSelectFieldClass,
} from "../../lib/ui/mm-control-roles";
import { MmOnOffSwitch } from "../../components/ui/mm-on-off-switch";

function canEdit(role: string | undefined): boolean {
  return role === "operator" || role === "admin";
}

export function RefinerLibrarySection() {
  const me = useMeQuery();
  const editable = canEdit(me.data?.role);
  const libraries = useRefinerLibrariesQuery();
  const [libraryId, setLibraryId] = useState<number | null>(null);

  useEffect(() => {
    if (libraryId === null && libraries.data && libraries.data.length > 0) {
      setLibraryId(libraries.data[0].id);
    }
  }, [libraries.data, libraryId]);

  const settings = useLibrarySettingsQuery(libraryId ?? 0, libraryId !== null);
  const saveFolders = useSaveLibraryFolders(libraryId ?? 0);
  const savePreflight = useSaveLibraryPreflightSettings(libraryId ?? 0);
  const scheduleMutation = useSetLibrarySchedule(libraryId ?? 0);
  const scanMutation = useTriggerLibraryScan(libraryId ?? 0);

  const [newFolder, setNewFolder] = useState("");
  const [folderError, setFolderError] = useState<string | null>(null);
  const [preflightError, setPreflightError] = useState<string | null>(null);
  const [cleanNotice, setCleanNotice] = useState<{
    queued: number;
    skipped: string[];
    warnings: string[];
  } | null>(null);

  const [classification, setClassification] = useState<
    LibraryFileClassification | ""
  >("");
  const [manager, setManager] = useState("");
  const [search, setSearch] = useState("");
  const files = useLibraryFilesQuery(
    libraryId ?? 0,
    {
      classification: classification || undefined,
      manager: manager || undefined,
      q: search || undefined,
    },
    libraryId !== null,
  );

  const [selected, setSelected] = useState<Set<string>>(new Set());
  const cleanMutation = useCleanLibraryFiles(libraryId ?? 0);
  const redownloads = useLibraryRedownloadsQuery(
    libraryId ?? 0,
    libraryId !== null,
  );
  const redownloadMutation = useRequestLibraryRedownload(libraryId ?? 0);
  const [confirmingRedownload, setConfirmingRedownload] = useState<
    string | null
  >(null);
  const [redownloadError, setRedownloadError] = useState<string | null>(null);
  const [cleanConfirmation, setCleanConfirmation] =
    useState<LibraryConfirmationRequired | null>(null);
  const [cleanError, setCleanError] = useState<string | null>(null);
  const [scheduleConfirmation, setScheduleConfirmation] =
    useState<LibraryConfirmationRequired | null>(null);
  const [scheduleError, setScheduleError] = useState<string | null>(null);

  const selectedFiles = useMemo(
    () => (files.data?.files ?? []).filter((f) => selected.has(f.path)),
    [files.data, selected],
  );

  if (libraries.isLoading) {
    return <PageLoading label="Loading libraries…" />;
  }

  if (!libraries.data || libraries.data.length === 0) {
    return (
      <p className="text-sm text-[var(--mm-text2)]">
        Add a Refiner library first, under the Libraries tab.
      </p>
    );
  }

  const addFolder = () => {
    const trimmed = newFolder.trim();
    if (!trimmed || !settings.data || libraryId === null) return;
    const next = Array.from(
      new Set([...settings.data.library_folders, trimmed]),
    );
    setFolderError(null);
    saveFolders.mutate(next, {
      onSuccess: () => setNewFolder(""),
      onError: (error) => setFolderError((error as Error).message),
    });
  };

  const removeFolder = (folder: string) => {
    if (!settings.data || libraryId === null) return;
    saveFolders.mutate(
      settings.data.library_folders.filter((f) => f !== folder),
      { onError: (error) => setFolderError((error as Error).message) },
    );
  };

  const runClean = (confirm: boolean) => {
    if (selectedFiles.length === 0 || libraryId === null) return;
    setCleanError(null);
    cleanMutation.mutate(
      { paths: selectedFiles.map((f) => f.path), confirm },
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
        onSuccess: (result) => {
          if ("kind" in result) {
            setScheduleConfirmation(result);
          } else {
            setScheduleConfirmation(null);
          }
        },
        onError: (error) => setScheduleError((error as Error).message),
      },
    );
  };

  const toggleSelected = (path: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  };

  return (
    <div className="mm-bubble-stack flex w-full min-w-0 flex-col gap-4">
      <label className="block max-w-md text-sm font-medium text-[var(--mm-text1)]">
        Library
        <select
          className={mmSelectFieldClass}
          value={libraryId ?? ""}
          onChange={(e) => {
            setLibraryId(Number(e.target.value));
            setSelected(new Set());
          }}
        >
          {libraries.data.map((library) => (
            <option key={library.id} value={library.id}>
              {library.name}
            </option>
          ))}
        </select>
      </label>

      {libraryId !== null && settings.data ? (
        <section
          className="mm-bubble space-y-3 p-4"
          data-testid="library-folders-section"
        >
          <h3 className="text-sm font-semibold text-[var(--mm-text1)]">
            Library folders
          </h3>
          <p className="text-xs text-[var(--mm-text3)]">
            Where Weir looks for files to clean in place. Separate from this
            library&apos;s watched, work and output folders — they may be the
            same folders a media manager already watches, or different ones.
          </p>
          <ul className="space-y-1">
            {settings.data.library_folders.map((folder) => (
              <li
                key={folder}
                className="flex items-center justify-between gap-2 rounded border border-[var(--mm-border)] px-2 py-1 text-sm"
              >
                <span className="break-all">{folder}</span>
                {editable ? (
                  <button
                    type="button"
                    className={mmActionButtonClass({ variant: "tertiary" })}
                    onClick={() => removeFolder(folder)}
                    disabled={saveFolders.isPending}
                  >
                    Remove
                  </button>
                ) : null}
              </li>
            ))}
            {settings.data.library_folders.length === 0 ? (
              <li className="text-sm text-[var(--mm-text3)]">
                No library folders yet.
              </li>
            ) : null}
          </ul>
          {editable ? (
            <div className="flex flex-wrap items-center gap-2">
              <input
                className={mmEditableTextFieldClass}
                style={{ maxWidth: "24rem" }}
                placeholder="/srv/media/movies-4k"
                value={newFolder}
                onChange={(e) => setNewFolder(e.target.value)}
              />
              <button
                type="button"
                className={mmActionButtonClass({
                  variant: "secondary",
                  disabled: saveFolders.isPending || newFolder.trim() === "",
                })}
                disabled={saveFolders.isPending || newFolder.trim() === ""}
                onClick={addFolder}
              >
                Add folder
              </button>
            </div>
          ) : null}
          {folderError ? (
            <p
              className="text-sm text-[var(--mm-status-failed-text)]"
              role="alert"
            >
              {folderError}
            </p>
          ) : null}

          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-[var(--mm-border)] pt-3">
            <MmOnOffSwitch
              id="library-schedule-toggle"
              label="Scheduled scan and clean (uses this library's schedule window)"
              enabled={settings.data.library_schedule_enabled}
              disabled={!editable || scheduleMutation.isPending}
              onChange={(next) => toggleSchedule(next, false)}
            />
            <button
              type="button"
              className={mmActionButtonClass({
                variant: "secondary",
                disabled:
                  scanMutation.isPending ||
                  settings.data.library_folders.length === 0,
              })}
              disabled={
                scanMutation.isPending ||
                settings.data.library_folders.length === 0
              }
              onClick={() => scanMutation.mutate()}
            >
              {scanMutation.isPending ? "Scanning…" : "Scan now"}
            </button>
          </div>
          {scheduleError ? (
            <p
              className="text-sm text-[var(--mm-status-failed-text)]"
              role="alert"
            >
              {scheduleError}
            </p>
          ) : null}

          <div className="space-y-2 border-t border-[var(--mm-border)] pt-3">
            <MmOnOffSwitch
              id="library-clean-hardlinked-toggle"
              label="Clean files still shared with a download (seeding)"
              enabled={settings.data.clean_hardlinked_files}
              disabled={!editable || savePreflight.isPending}
              onChange={(next) =>
                togglePreflightSetting("clean_hardlinked_files", next)
              }
            />
            <p className="text-xs text-[var(--mm-text3)]">
              Off by default: cleaning a file another name still shares data
              with doesn&apos;t free anything, since the original bytes stay
              allocated under the other name.
            </p>
            <MmOnOffSwitch
              id="library-skip-redownload-risk-toggle"
              label="Skip a clean that would make a manager re-download the title"
              enabled={settings.data.skip_if_manager_would_redownload}
              disabled={!editable || savePreflight.isPending}
              onChange={(next) =>
                togglePreflightSetting("skip_if_manager_would_redownload", next)
              }
            />
          </div>
          {preflightError ? (
            <p
              className="text-sm text-[var(--mm-status-failed-text)]"
              role="alert"
            >
              {preflightError}
            </p>
          ) : null}
        </section>
      ) : null}

      {libraryId !== null ? (
        <section
          className="mm-bubble space-y-3 p-4"
          data-testid="library-files-section"
        >
          <div className="flex flex-wrap items-center gap-2">
            <select
              className={mmSelectFieldClass}
              style={{ maxWidth: "16rem" }}
              value={classification}
              onChange={(e) =>
                setClassification(
                  e.target.value as LibraryFileClassification | "",
                )
              }
            >
              <option value="">All files</option>
              {(
                Object.keys(
                  LIBRARY_FILE_CLASSIFICATION_LABELS,
                ) as LibraryFileClassification[]
              ).map((value) => (
                <option key={value} value={value}>
                  {LIBRARY_FILE_CLASSIFICATION_LABELS[value]}
                </option>
              ))}
            </select>
            <select
              className={mmSelectFieldClass}
              style={{ maxWidth: "12rem" }}
              value={manager}
              onChange={(e) => setManager(e.target.value)}
              aria-label="Filter by manager"
            >
              <option value="">All managers</option>
              {LIBRARY_MANAGER_FILTER_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
            <input
              className={mmEditableTextFieldClass}
              style={{ maxWidth: "20rem" }}
              placeholder="Search path"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>

          {files.data ? (
            <p
              className="text-sm text-[var(--mm-text2)]"
              data-testid="library-files-summary"
            >
              {files.data.summary.matches} match the rules,{" "}
              {files.data.summary.would_change} would change,{" "}
              {files.data.summary.cannot_process} cannot be processed. Estimated
              size saved if all &quot;would change&quot; files were cleaned:{" "}
              {formatBytes(files.data.summary.estimated_bytes_saved)}.
            </p>
          ) : null}

          {files.isLoading ? <PageLoading label="Loading files…" /> : null}

          {files.data ? (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[40rem] text-left text-sm">
                <thead>
                  <tr className="border-b border-[var(--mm-border)] text-[var(--mm-text3)]">
                    <th className="w-8 py-1" />
                    <th className="py-1">Path</th>
                    <th className="py-1">Status</th>
                    <th className="py-1">Manager</th>
                  </tr>
                </thead>
                <tbody>
                  {files.data.files.map((file) => (
                    <tr
                      key={file.path}
                      className="border-b border-[var(--mm-border)]/50 align-top"
                      data-testid="library-file-row"
                    >
                      <td className="py-2">
                        <input
                          type="checkbox"
                          className={mmCheckboxControlClass}
                          checked={selected.has(file.path)}
                          onChange={() => toggleSelected(file.path)}
                          disabled={
                            !editable || file.classification !== "would_change"
                          }
                          aria-label={`Select ${file.path}`}
                        />
                      </td>
                      <td className="py-2 break-all">{file.path}</td>
                      <td className="py-2">
                        <div>
                          {
                            LIBRARY_FILE_CLASSIFICATION_LABELS[
                              file.classification
                            ]
                          }
                        </div>
                        <div className="text-xs text-[var(--mm-text3)]">
                          {file.summary ?? file.reason ?? ""}
                        </div>
                      </td>
                      <td className="py-2 text-xs text-[var(--mm-text3)]">
                        {file.manager_title
                          ? `${file.manager_title}${file.manager_kind ? ` (${file.manager_kind})` : ""}`
                          : "Unmatched"}
                      </td>
                    </tr>
                  ))}
                  {files.data.files.length === 0 ? (
                    <tr>
                      <td colSpan={4} className="py-4 text-[var(--mm-text3)]">
                        No files yet. Scan this library first.
                      </td>
                    </tr>
                  ) : null}
                </tbody>
              </table>
            </div>
          ) : null}

          {editable ? (
            <button
              type="button"
              className={mmActionButtonClass({
                variant: "primary",
                disabled: selectedFiles.length === 0 || cleanMutation.isPending,
              })}
              disabled={selectedFiles.length === 0 || cleanMutation.isPending}
              onClick={() => runClean(false)}
              data-testid="library-clean-button"
            >
              Clean selected ({selectedFiles.length})
            </button>
          ) : null}
          {cleanError ? (
            <p
              className="text-sm text-[var(--mm-status-failed-text)]"
              role="alert"
            >
              {cleanError}
            </p>
          ) : null}
          {cleanNotice ? (
            <div
              className="space-y-1 rounded border border-[var(--mm-border)] p-2 text-sm text-[var(--mm-text2)]"
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
        </section>
      ) : null}

      {libraryId !== null &&
      redownloads.data &&
      redownloads.data.titles.length > 0 ? (
        <section
          className="mm-bubble space-y-3 p-4"
          data-testid="library-redownloads-section"
        >
          <h3 className="text-sm font-semibold text-[var(--mm-text1)]">
            Titles missing tracks your new rules keep
          </h3>
          <p className="text-xs text-[var(--mm-text3)]">
            A past clean removed these tracks for good; the only way to get one
            back is downloading the title again.
          </p>
          <ul className="space-y-2">
            {redownloads.data.titles.map((title) => (
              <li
                key={title.path}
                className="rounded border border-[var(--mm-border)] p-2 text-sm"
                data-testid="library-redownload-row"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <div className="break-all font-medium text-[var(--mm-text1)]">
                      {title.manager_title ?? title.path}
                    </div>
                    <div className="text-xs text-[var(--mm-text3)]">
                      {title.removed_tracks
                        .map((t) => `${t.language} ${t.type}`)
                        .join(", ")}
                    </div>
                  </div>
                  {editable && title.can_redownload ? (
                    <button
                      type="button"
                      className={mmActionButtonClass({ variant: "secondary" })}
                      onClick={() => setConfirmingRedownload(title.path)}
                    >
                      Download again
                    </button>
                  ) : (
                    <span className="text-xs text-[var(--mm-text3)]">
                      {title.unavailable_reason}
                    </span>
                  )}
                </div>
                {confirmingRedownload === title.path ? (
                  <div className="mt-2 space-y-2 border-t border-[var(--mm-border)] pt-2">
                    <p className="text-sm text-[var(--mm-status-failed-text)]">
                      {title.confirmation_message}
                    </p>
                    <div className="flex gap-2">
                      <button
                        type="button"
                        className={mmActionButtonClass({
                          variant: "primary",
                          disabled: redownloadMutation.isPending,
                        })}
                        disabled={redownloadMutation.isPending}
                        onClick={() => {
                          setRedownloadError(null);
                          redownloadMutation.mutate(title.path, {
                            onSuccess: () => setConfirmingRedownload(null),
                            onError: (error) =>
                              setRedownloadError((error as Error).message),
                          });
                        }}
                      >
                        {redownloadMutation.isPending
                          ? "Requesting…"
                          : "Confirm download again"}
                      </button>
                      <button
                        type="button"
                        className={mmActionButtonClass({
                          variant: "tertiary",
                        })}
                        onClick={() => setConfirmingRedownload(null)}
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                ) : null}
              </li>
            ))}
          </ul>
          {redownloadError ? (
            <p
              className="text-sm text-[var(--mm-status-failed-text)]"
              role="alert"
            >
              {redownloadError}
            </p>
          ) : null}
        </section>
      ) : null}

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
