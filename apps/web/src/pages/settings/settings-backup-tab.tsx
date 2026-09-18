import type { ChangeEvent } from "react";
import { useRef } from "react";
import type { SuiteSettingsOut } from "../../lib/suite/types";
import type {
  useSuiteConfigurationBackupsQuery,
  useSuiteSettingsSaveMutation,
} from "../../lib/suite/queries";
import { mmActionButtonClass } from "../../lib/ui/mm-control-roles";
import { useAppDateFormatter } from "../../lib/ui/mm-format-date";
import {
  mmModuleTabBlurbBandClass,
  mmModuleTabBlurbTextClass,
} from "../../lib/ui/mm-module-tab-blurb";
import {
  QuietFieldGroup,
  quietActionRowClass,
} from "../../components/shared/quiet-section";
import {
  CONFIGURATION_BACKUP_INTERVAL_HOURS,
  SettingsQuietSection,
  formatBackupBytes,
} from "./settings-shared";

type SettingsBackupTabProps = {
  editable: boolean;
  settingsData: SuiteSettingsOut;
  save: ReturnType<typeof useSuiteSettingsSaveMutation>;
  backupScheduleDirty: boolean;
  lastSuiteSaveTarget: "timezone" | "logs" | "backup" | null;
  configurationBackupEnabled: boolean;
  setConfigurationBackupEnabled: (v: boolean) => void;
  configurationBackupIntervalHours: number;
  setConfigurationBackupIntervalHours: (v: number) => void;
  configurationBackupPreferredTime: string;
  setConfigurationBackupPreferredTime: (v: string) => void;
  backupsQ: ReturnType<typeof useSuiteConfigurationBackupsQuery>;
  backupBusy: boolean;
  backupMsg: string | null;
  backupErr: string | null;
  onSaveBackupSchedule: () => void;
  onDownloadConfiguration: () => void;
  onRestoreFileChange: (event: ChangeEvent<HTMLInputElement>) => void;
  onDownloadStoredBackup: (id: number, fileLabel: string) => void;
};

export function SettingsBackupTab({
  editable,
  settingsData,
  save,
  backupScheduleDirty,
  lastSuiteSaveTarget,
  configurationBackupEnabled,
  setConfigurationBackupEnabled,
  configurationBackupIntervalHours,
  setConfigurationBackupIntervalHours,
  configurationBackupPreferredTime,
  setConfigurationBackupPreferredTime,
  backupsQ,
  backupBusy,
  backupMsg,
  backupErr,
  onSaveBackupSchedule,
  onDownloadConfiguration,
  onRestoreFileChange,
  onDownloadStoredBackup,
}: SettingsBackupTabProps) {
  const restoreInputRef = useRef<HTMLInputElement>(null);
  const formatDate = useAppDateFormatter();

  return (
    <div data-testid="suite-settings-backup-tab" className="mm-quiet-stack">
      <div className={mmModuleTabBlurbBandClass}>
        <p className={mmModuleTabBlurbTextClass}>
          Export, restore, and automatically snapshot Weir configuration.
        </p>
      </div>

      {editable ? (
        <div
          className="mm-quiet-stack"
          data-testid="suite-settings-backup-restore"
        >
          <SettingsQuietSection
            headingId="suite-settings-backup-heading"
            heading="Backup and restore"
          >
            <p className="mm-quiet-note">
              Keep a clean copy of Weir settings and restore them if something
              goes wrong.
            </p>

            {/* Two distinct actions, each with its own scope and its own Save row.
                Rule 3: what says which button belongs to which is the eyebrow and the
                hairline over each group, not a box around it — and stacking them means
                a short group beside a long one can no longer leave a ragged column. */}
            <div className="mt-6 grid gap-10">
              <QuietFieldGroup
                title="Scheduled snapshots"
                detail="Weir keeps the latest five configuration snapshots using the same restore-safe JSON format."
              >
                <div className="max-w-xl space-y-4">
                  <label className="flex cursor-pointer items-start gap-2.5 text-sm text-[var(--mm-text2)]">
                    <input
                      type="checkbox"
                      className="mt-0.5 h-4 w-4 shrink-0 accent-[var(--mm-accent)]"
                      checked={configurationBackupEnabled}
                      disabled={!editable || save.isPending}
                      onChange={(e) =>
                        setConfigurationBackupEnabled(e.target.checked)
                      }
                    />
                    <span>Run scheduled configuration backups</span>
                  </label>
                  <label className="block text-sm text-[var(--mm-text2)]">
                    <span className="mb-1.5 block text-sm text-[var(--mm-text2)]">
                      Minimum time between runs
                    </span>
                    <select
                      className="mm-input w-full max-w-xs"
                      value={configurationBackupIntervalHours}
                      disabled={!editable || save.isPending}
                      onChange={(e) =>
                        setConfigurationBackupIntervalHours(
                          Number(e.target.value),
                        )
                      }
                    >
                      {CONFIGURATION_BACKUP_INTERVAL_HOURS.map((h) => (
                        <option key={h} value={h}>
                          {h === 168
                            ? "Every 7 days (168 h)"
                            : `Every ${h} hours`}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="block text-sm text-[var(--mm-text2)]">
                    <span className="mb-1.5 block text-sm text-[var(--mm-text2)]">
                      Preferred backup time
                    </span>
                    <input
                      type="time"
                      className="mm-input w-full max-w-xs"
                      value={configurationBackupPreferredTime}
                      disabled={!editable || save.isPending}
                      onChange={(e) =>
                        setConfigurationBackupPreferredTime(
                          e.target.value || "02:00",
                        )
                      }
                    />
                  </label>
                  <p className="text-xs text-[var(--mm-text3)]">
                    <span className="font-medium text-[var(--mm-text2)]">
                      Last automatic run:
                    </span>{" "}
                    {formatDate(settingsData.configuration_backup_last_run_at)}
                  </p>
                  <p className="text-xs text-[var(--mm-text3)]">
                    <span className="font-medium text-[var(--mm-text2)]">
                      Target time:
                    </span>{" "}
                    {configurationBackupPreferredTime}
                  </p>
                </div>
                <div className={quietActionRowClass}>
                  <button
                    type="button"
                    className={mmActionButtonClass({
                      variant: "secondary",
                      disabled:
                        !editable || !backupScheduleDirty || save.isPending,
                    })}
                    disabled={
                      !editable || !backupScheduleDirty || save.isPending
                    }
                    onClick={() => onSaveBackupSchedule()}
                  >
                    {save.isPending ? "Saving..." : "Save backup schedule"}
                  </button>
                  {save.isError && lastSuiteSaveTarget === "backup" ? (
                    <p
                      className="mm-status-text--failed text-sm"
                      role="alert"
                      data-testid="suite-settings-backup-save-error"
                    >
                      {save.error instanceof Error
                        ? save.error.message
                        : "Could not save."}
                    </p>
                  ) : null}
                </div>
              </QuietFieldGroup>

              <QuietFieldGroup
                title="Export or restore now"
                detail="Download a full settings file, or restore a Weir configuration JSON from disk."
              >
                <div className="flex flex-wrap items-center gap-2">
                  <button
                    type="button"
                    className={mmActionButtonClass({
                      variant: "secondary",
                      disabled: backupBusy || save.isPending,
                    })}
                    disabled={backupBusy || save.isPending}
                    onClick={() => onDownloadConfiguration()}
                  >
                    Download configuration now
                  </button>
                  <button
                    type="button"
                    className={mmActionButtonClass({
                      variant: "tertiary",
                      disabled: backupBusy || save.isPending,
                    })}
                    disabled={backupBusy || save.isPending}
                    onClick={() => restoreInputRef.current?.click()}
                  >
                    Restore from file...
                  </button>
                  <input
                    ref={restoreInputRef}
                    type="file"
                    accept="application/json,.json"
                    className="hidden"
                    aria-label="Choose configuration JSON file to restore"
                    onChange={(e) => onRestoreFileChange(e)}
                  />
                </div>
              </QuietFieldGroup>
            </div>
          </SettingsQuietSection>

          {/* A list of what is on disk: display content, so it loses its box. */}
          <SettingsQuietSection
            headingId="suite-settings-backup-snapshots-heading"
            heading="Recent automatic snapshots"
            aside={<span className="mm-quiet-badge">Keeps latest 5</span>}
          >
            {backupsQ.data ? (
              <p
                className="mm-quiet-table__sub font-mono break-all"
                data-testid="suite-configuration-backup-directory"
              >
                {backupsQ.data.directory}
              </p>
            ) : null}
            <div className="mt-3">
              {backupsQ.isLoading ? (
                <p className="mm-quiet-note">Loading snapshot list...</p>
              ) : backupsQ.isError ? (
                <p
                  className="text-sm text-[var(--mm-status-failed-text)]"
                  role="alert"
                >
                  {(backupsQ.error as Error).message}
                </p>
              ) : (backupsQ.data?.items.length ?? 0) === 0 ? (
                <p className="mm-quiet-note">No automatic snapshots yet.</p>
              ) : (
                <div className="mm-quiet-table-wrap">
                  <table className="mm-quiet-table">
                    <thead>
                      <tr>
                        <th scope="col">Taken</th>
                        <th scope="col">Size</th>
                        <th scope="col">
                          <span className="sr-only">Download</span>
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {backupsQ.data!.items.map((row) => (
                        <tr key={row.id}>
                          <th scope="row" className="mm-quiet-table__name">
                            {formatDate(row.created_at)}
                          </th>
                          <td data-label="Size">
                            {formatBackupBytes(row.size_bytes)}
                          </td>
                          <td data-label="">
                            <button
                              type="button"
                              className="mm-quiet-link"
                              disabled={backupBusy || save.isPending}
                              onClick={() =>
                                onDownloadStoredBackup(row.id, row.file_name)
                              }
                            >
                              Download snapshot →
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </SettingsQuietSection>

          {backupMsg ? (
            <p className="mm-status-text--healthy text-sm" role="status">
              {backupMsg}
            </p>
          ) : null}
          {backupErr ? (
            <p className="mm-status-text--failed text-sm" role="alert">
              {backupErr}
            </p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
