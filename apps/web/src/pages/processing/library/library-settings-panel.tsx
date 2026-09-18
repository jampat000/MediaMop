/**
 * The library's own library-mode settings (#505 folders and schedule, #508's two preflight choices), lifted
 * out of the old single-panel Library tab when #568 gave it sub-navigation. It lives on Overview, next to the
 * numbers those settings decide.
 */
import { useState } from "react";

import { MmOnOffSwitch } from "../../../components/ui/mm-on-off-switch";
import type { LibrarySettings } from "../../../lib/processing/library-api";
import {
  mmActionButtonClass,
  mmEditableTextFieldClass,
} from "../../../lib/ui/mm-control-roles";

export type LibrarySettingsPanelProps = {
  settings: LibrarySettings;
  editable: boolean;
  savingFolders: boolean;
  savingPreflight: boolean;
  savingSchedule: boolean;
  folderError: string | null;
  preflightError: string | null;
  scheduleError: string | null;
  onAddFolder: (folder: string) => void;
  onRemoveFolder: (folder: string) => void;
  onToggleSchedule: (enabled: boolean) => void;
  onTogglePreflight: (
    field: "clean_hardlinked_files" | "skip_if_manager_would_redownload",
    next: boolean,
  ) => void;
};

export function LibrarySettingsPanel({
  settings,
  editable,
  savingFolders,
  savingPreflight,
  savingSchedule,
  folderError,
  preflightError,
  scheduleError,
  onAddFolder,
  onRemoveFolder,
  onToggleSchedule,
  onTogglePreflight,
}: LibrarySettingsPanelProps) {
  const [newFolder, setNewFolder] = useState("");

  const add = () => {
    const trimmed = newFolder.trim();
    if (!trimmed) return;
    onAddFolder(trimmed);
    setNewFolder("");
  };

  return (
    <section
      className="mm-bubble space-y-3 p-4"
      data-testid="library-folders-section"
    >
      <h3 className="text-sm font-semibold text-[var(--mm-text1)]">
        Library folders
      </h3>
      <p className="text-xs text-[var(--mm-text3)]">
        Where Weir looks for files to clean in place. Separate from this
        library&apos;s watched, work and output folders — they may be the same
        folders a media manager already watches, or different ones.
      </p>
      <ul className="space-y-1">
        {settings.library_folders.map((folder) => (
          <li
            key={folder}
            className="flex items-center justify-between gap-2 rounded border border-[var(--mm-border)] px-2 py-1 text-sm"
          >
            <span className="break-all">{folder}</span>
            {editable ? (
              <button
                type="button"
                className={mmActionButtonClass({ variant: "tertiary" })}
                onClick={() => onRemoveFolder(folder)}
                disabled={savingFolders}
              >
                Remove
              </button>
            ) : null}
          </li>
        ))}
        {settings.library_folders.length === 0 ? (
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
            aria-label="Library folder to add"
            value={newFolder}
            onChange={(e) => setNewFolder(e.target.value)}
          />
          <button
            type="button"
            className={mmActionButtonClass({
              variant: "secondary",
              disabled: savingFolders || newFolder.trim() === "",
            })}
            disabled={savingFolders || newFolder.trim() === ""}
            onClick={add}
          >
            Add folder
          </button>
        </div>
      ) : null}
      {folderError ? (
        <p className="text-sm text-[var(--mm-status-failed-text)]" role="alert">
          {folderError}
        </p>
      ) : null}

      <div className="border-t border-[var(--mm-border)] pt-3">
        <MmOnOffSwitch
          id="library-schedule-toggle"
          label="Scheduled scan and clean (uses this library's schedule window)"
          enabled={settings.library_schedule_enabled}
          disabled={!editable || savingSchedule}
          onChange={onToggleSchedule}
        />
      </div>
      {scheduleError ? (
        <p className="text-sm text-[var(--mm-status-failed-text)]" role="alert">
          {scheduleError}
        </p>
      ) : null}

      <div className="space-y-2 border-t border-[var(--mm-border)] pt-3">
        <MmOnOffSwitch
          id="library-clean-hardlinked-toggle"
          label="Clean files still shared with a download (seeding)"
          enabled={settings.clean_hardlinked_files}
          disabled={!editable || savingPreflight}
          onChange={(next) => onTogglePreflight("clean_hardlinked_files", next)}
        />
        <p className="text-xs text-[var(--mm-text3)]">
          Off by default: cleaning a file another name still shares data with
          doesn&apos;t free anything, since the original bytes stay allocated
          under the other name.
        </p>
        <MmOnOffSwitch
          id="library-skip-redownload-risk-toggle"
          label="Skip a clean that would make a manager re-download the title"
          enabled={settings.skip_if_manager_would_redownload}
          disabled={!editable || savingPreflight}
          onChange={(next) =>
            onTogglePreflight("skip_if_manager_would_redownload", next)
          }
        />
      </div>
      {preflightError ? (
        <p className="text-sm text-[var(--mm-status-failed-text)]" role="alert">
          {preflightError}
        </p>
      ) : null}
    </section>
  );
}
