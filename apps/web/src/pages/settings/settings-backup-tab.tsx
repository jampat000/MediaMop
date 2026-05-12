import type { ChangeEvent } from "react";
import { useRef } from "react";
import type { SuiteSettingsOut } from "../../lib/suite/types";
import type { useSuiteConfigurationBackupsQuery, useSuiteSettingsSaveMutation } from "../../lib/suite/queries";
import { mmActionButtonClass } from "../../lib/ui/mm-control-roles";
import {
  mmModuleTabBlurbBandClass,
  mmModuleTabBlurbTextClass,
} from "../../lib/ui/mm-module-tab-blurb";
import {
  CONFIGURATION_BACKUP_INTERVAL_HOURS,
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

  return (
    <div
      data-testid="suite-settings-backup-tab"
      className="mm-bubble-stack"
    >
      <div className={mmModuleTabBlurbBandClass}>
        <p className={mmModuleTabBlurbTextClass}>
          Export, restore, and automatically snapshot MediaMop
          configuration.
        </p>
      </div>

      {editable ? (
        <section
          className="grid grid-cols-1 gap-5 xl:grid-cols-3"
          data-testid="suite-settings-backup-restore"
          aria-labelledby="suite-settings-backup-heading"
        >
          <div className="xl:col-span-3">
            <h3
              id="suite-settings-backup-heading"
              className="text-base font-semibold text-[var(--mm-text1)]"
            >
              Backup and restore
            </h3>
            <p className="mt-1 text-sm text-[var(--mm-text2)]">
              Keep a clean copy of MediaMop settings and restore them if
              something goes wrong.
            </p>
          </div>

          <div className="contents">
            <section className={SUITE_SETTINGS_DASH_CARD_CLASS}>
              <div className="mm-card-action-body">
                <div>
                  <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--mm-gold)]">
                    Automatic protection
                  </p>
                  <h4 className="mt-1 text-sm font-semibold text-[var(--mm-text1)]">
                    Scheduled snapshots
                  </h4>
                  <p className="mt-1 text-xs leading-relaxed text-[var(--mm-text3)]">
                    MediaMop keeps the latest five configuration snapshots
                    using the same restore-safe JSON format.
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
                  <span className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-[var(--mm-text3)]">
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
                  <span className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-[var(--mm-text3)]">
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
                  {settingsData.configuration_backup_last_run_at
                    ? new Date(
                        settingsData.configuration_backup_last_run_at,
                      ).toLocaleString()
                    : "—"}
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
                  disabled={
                    !editable || !backupScheduleDirty || save.isPending
                  }
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
                  <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--mm-gold)]">
                    Manual control
                  </p>
                  <h4 className="mt-1 text-sm font-semibold text-[var(--mm-text1)]">
                    Export or restore now
                  </h4>
                  <p className="mt-1 text-xs leading-relaxed text-[var(--mm-text3)]">
                    Download a full settings file, or restore a MediaMop
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

          <section className={SUITE_SETTINGS_DASH_CARD_CLASS}>
            <div className="mm-card-action-body">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--mm-gold)]">
                    Snapshot history
                  </p>
                  <h4 className="mt-1 text-sm font-semibold text-[var(--mm-text1)]">
                    Recent automatic snapshots
                  </h4>
                </div>
                <span className="rounded-full border border-[var(--mm-border)] bg-[var(--mm-card-bg)] px-2.5 py-1 text-xs text-[var(--mm-text2)]">
                  Keeps latest 5
                </span>
              </div>
              {backupsQ.data ? (
                <p
                  className="mt-1.5 break-all font-mono text-xs leading-snug text-[var(--mm-text2)]"
                  data-testid="suite-configuration-backup-directory"
                >
                  {backupsQ.data.directory}
                </p>
              ) : null}
              <div className="mt-3">
                {backupsQ.isLoading ? (
                  <p className="text-sm text-[var(--mm-text3)]">
                    Loading snapshot list...
                  </p>
                ) : backupsQ.isError ? (
                  <p
                    className="rounded-md border border-red-500/40 bg-red-950/25 px-3 py-2 text-sm text-red-200"
                    role="alert"
                  >
                    {(backupsQ.error as Error).message}
                  </p>
                ) : (backupsQ.data?.items.length ?? 0) === 0 ? (
                  <p className="text-sm text-[var(--mm-text3)]">
                    No automatic snapshots yet.
                  </p>
                ) : (
                  <ul className="divide-y divide-[var(--mm-border)] overflow-hidden rounded-md border border-[var(--mm-border)] text-sm">
                    {backupsQ.data!.items.map((row) => (
                      <li
                        key={row.id}
                        className="flex flex-col gap-2 px-3 py-3 sm:flex-row sm:items-center sm:justify-between sm:gap-4"
                      >
                        <div className="min-w-0 text-[var(--mm-text2)]">
                          <div className="font-medium text-[var(--mm-text)]">
                            {new Date(row.created_at).toLocaleString()}
                          </div>
                          <div className="text-xs text-[var(--mm-text3)]">
                            {formatBackupBytes(row.size_bytes)}
                          </div>
                        </div>
                        <button
                          type="button"
                          className={mmActionButtonClass({
                            variant: "tertiary",
                            disabled: backupBusy || save.isPending,
                          })}
                          disabled={backupBusy || save.isPending}
                          onClick={() =>
                            onDownloadStoredBackup(row.id, row.file_name)
                          }
                        >
                          Download snapshot
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
          </section>

          {backupMsg ? (
            <p className="rounded-md border border-emerald-500/30 bg-emerald-950/20 px-3 py-2 text-sm text-emerald-200 xl:col-span-3">
              {backupMsg}
            </p>
          ) : null}
          {backupErr ? (
            <p
              className="rounded-md border border-red-500/40 bg-red-950/25 px-3 py-2 text-sm text-red-200 xl:col-span-3"
              role="alert"
            >
              {backupErr}
            </p>
          ) : null}
        </section>
      ) : null}
    </div>
  );
}
