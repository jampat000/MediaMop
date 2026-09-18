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
  CONFIGURATION_BACKUP_INTERVAL_HOURS,
  SettingsQuietSection,
  SUITE_SETTINGS_DASH_CARD_CLASS,
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
          <div>
            <h3
              id="suite-settings-backup-heading"
              className="mm-quiet-section__title"
            >
              Backup and restore
            </h3>
            <p className="mm-quiet-note mt-1">
              Keep a clean copy of Weir settings and restore them if something
              goes wrong.
            </p>
          </div>

          {/* Two distinct actions, each with its own scope and its own button.
              The boundary is what says which button belongs to which. */}
          <div className="grid grid-cols-1 items-start gap-5 xl:grid-cols-2">
            <section className={SUITE_SETTINGS_DASH_CARD_CLASS}>
              <div className="mm-card-action-body">
                <div>
                  <p className="text-[11px] font-semibold tracking-[0.14em] text-[var(--mm-gold)] uppercase">
                    Automatic protection
                  </p>
                  <h4 className="mt-1 text-sm font-semibold text-[var(--mm-text1)]">
                    Scheduled snapshots
                  </h4>
                  <p className="mt-1 text-xs leading-relaxed text-[var(--mm-text3)]">
                    Weir keeps the latest five configuration snapshots using the
                    same restore-safe JSON format.
                  </p>
                </div>
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
                  <span className="mb-1.5 block text-xs font-medium tracking-wide text-[var(--mm-text3)] uppercase">
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
                  <span className="mb-1.5 block text-xs font-medium tracking-wide text-[var(--mm-text3)] uppercase">
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
              <div className="mm-card-action-footer">
                <button
                  type="button"
                  className={mmActionButtonClass({
                    variant: "secondary",
                    disabled:
                      !editable || !backupScheduleDirty || save.isPending,
                  })}
                  disabled={!editable || !backupScheduleDirty || save.isPending}
                  onClick={() => onSaveBackupSchedule()}
                >
                  {save.isPending ? "Saving..." : "Save backup schedule"}
                </button>
                {save.isError && lastSuiteSaveTarget === "backup" ? (
                  <p
                    className="rounded-md border border-red-500/40 bg-red-950/25 px-3 py-2 text-sm text-red-200"
                    role="alert"
                    data-testid="suite-settings-backup-save-error"
                  >
                    {save.error instanceof Error
                      ? save.error.message
                      : "Could not save."}
                  </p>
                ) : null}
              </div>
            </section>

            <section className={SUITE_SETTINGS_DASH_CARD_CLASS}>
              <div className="mm-card-action-body">
                <div>
                  <p className="text-[11px] font-semibold tracking-[0.14em] text-[var(--mm-gold)] uppercase">
                    Manual control
                  </p>
                  <h4 className="mt-1 text-sm font-semibold text-[var(--mm-text1)]">
                    Export or restore now
                  </h4>
                  <p className="mt-1 text-xs leading-relaxed text-[var(--mm-text3)]">
                    Download a full settings file, or restore a Weir
                    configuration JSON from disk.
                  </p>
                </div>
              </div>
              <div className="mm-card-action-footer">
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
            </section>
          </div>

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
            <p className="rounded-md border border-emerald-500/30 bg-emerald-950/20 px-3 py-2 text-sm text-emerald-200">
              {backupMsg}
            </p>
          ) : null}
          {backupErr ? (
            <p
              className="rounded-md border border-red-500/40 bg-red-950/25 px-3 py-2 text-sm text-red-200"
              role="alert"
            >
              {backupErr}
            </p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
