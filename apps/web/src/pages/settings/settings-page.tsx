import { useQueryClient } from "@tanstack/react-query";
import type { ChangeEvent } from "react";
import { useEffect, useState } from "react";
import { useBlocker, useSearchParams } from "react-router-dom";
import { PageLoading } from "../../components/shared/page-loading";
import {
  isHttpErrorFromApi,
  isLikelyNetworkFailure,
} from "../../lib/api/error-guards";
import { useMeQuery } from "../../lib/auth/queries";
import { CURATED_TIMEZONE_ID_SET } from "../../lib/suite/timezone-options";
import {
  suiteConfigurationBackupsQueryKey,
  useSuiteConfigurationBackupsQuery,
  useSuiteOperationalHistoryResetMutation,
  useSuiteSettingsQuery,
  useSuiteSettingsSaveMutation,
  useSuiteUpdateStatusQuery,
} from "../../lib/suite/queries";
import type { SuiteSettingsPutBody } from "../../lib/suite/types";
import {
  fetchConfigurationBundle,
  fetchStoredConfigurationBackupBlob,
  putConfigurationBundle,
  type ConfigurationBundle,
} from "../../lib/suite/suite-settings-api";
import {
  readStoredDisplayDensity,
  type DisplayDensity,
} from "../../lib/ui/display-density";
import { SHOW_SUPPORT_CARD } from "../../lib/support";
import { SettingsGeneralTab } from "./settings-general-tab";
import { SettingsBackupTab } from "./settings-backup-tab";
import { SettingsUpgradeTab } from "./settings-upgrade-tab";
import { SettingsSecurityTab } from "./settings-security-tab";
import { SettingsLogsTab } from "./settings-logs-tab";
import { SettingsSupportTab } from "./settings-support-tab";
import { SettingsNotificationsTab } from "./settings-notifications-tab";
import { SettingsMediaManagersTab } from "./settings-media-managers-tab";

function canEditSuiteGlobal(role: string | undefined): boolean {
  return role === "operator" || role === "admin";
}

type TabId =
  | "general"
  | "backup"
  | "upgrade"
  | "security"
  | "logs"
  | "notifications"
  | "media-managers"
  | "support";

function tabButtonClass(active: boolean): string {
  return [
    "mm-settings-nav__button shrink-0 rounded-xl border px-3 py-2.5 text-left text-sm font-medium transition-colors",
    active
      ? "border-[var(--mm-accent)] bg-[var(--mm-accent)]/15 text-[var(--mm-text)]"
      : "border-[var(--mm-border)] bg-transparent text-[var(--mm-text2)] hover:bg-[var(--mm-card-bg)]",
  ].join(" ");
}

function normalizeSettingsTab(
  candidate: string | null | undefined,
  supportEnabled: boolean,
): TabId {
  switch ((candidate || "").trim().toLowerCase()) {
    case "backup":
      return "backup";
    case "upgrade":
      return "upgrade";
    case "security":
      return "security";
    case "logs":
      return "logs";
    case "notifications":
      return "notifications";
    case "media-managers":
      return "media-managers";
    case "support":
      return supportEnabled ? "support" : "general";
    default:
      return "general";
  }
}

/** Settings: General (timezone, display density, configuration export), Security, Logs (retention + recent events). */
export function SettingsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const queryClient = useQueryClient();
  const me = useMeQuery();
  const settingsQ = useSuiteSettingsQuery();
  const save = useSuiteSettingsSaveMutation();
  const resetHistory = useSuiteOperationalHistoryResetMutation();

  const showSupportTab = SHOW_SUPPORT_CARD;
  const [tab, setTab] = useState<TabId>(() =>
    normalizeSettingsTab(searchParams.get("tab"), showSupportTab),
  );

  function setSettingsTab(nextTab: TabId): void {
    setTab(nextTab);
    const nextParams = new URLSearchParams(searchParams);
    if (nextTab === "general") {
      nextParams.delete("tab");
    } else {
      nextParams.set("tab", nextTab);
    }
    setSearchParams(nextParams);
  }
  const [appTimezone, setAppTimezone] = useState<string | null>(null);
  const [logRetentionDaysDraft, setLogRetentionDaysDraft] = useState<
    string | null
  >(null);
  const [displayDensity, setDisplayDensity] = useState<DisplayDensity>(() =>
    readStoredDisplayDensity(),
  );
  const [backupBusy, setBackupBusy] = useState(false);
  const [backupMsg, setBackupMsg] = useState<string | null>(null);
  const [backupErr, setBackupErr] = useState<string | null>(null);
  const [resetHistoryMsg, setResetHistoryMsg] = useState<string | null>(null);
  const [resetHistoryConfirm, setResetHistoryConfirm] = useState("");
  const [configurationBackupEnabled, setConfigurationBackupEnabled] =
    useState(false);
  const [
    configurationBackupIntervalHours,
    setConfigurationBackupIntervalHours,
  ] = useState(24);
  const [
    configurationBackupPreferredTime,
    setConfigurationBackupPreferredTime,
  ] = useState("02:00");
  const [lastSuiteSaveTarget, setLastSuiteSaveTarget] = useState<
    "timezone" | "logs" | "backup" | null
  >(null);

  useEffect(() => {
    if (!settingsQ.data) {
      return;
    }
    const fromServer = settingsQ.data.app_timezone || "";
    setAppTimezone(CURATED_TIMEZONE_ID_SET.has(fromServer) ? fromServer : null);
    setLogRetentionDaysDraft(null);
    setConfigurationBackupEnabled(
      Boolean(settingsQ.data.configuration_backup_enabled),
    );
    setConfigurationBackupIntervalHours(
      Number.isFinite(
        Number(settingsQ.data.configuration_backup_interval_hours),
      )
        ? Number(settingsQ.data.configuration_backup_interval_hours)
        : 24,
    );
    setConfigurationBackupPreferredTime(
      (settingsQ.data.configuration_backup_preferred_time || "02:00").trim() ||
        "02:00",
    );
  }, [settingsQ.data]);

  const editable = canEditSuiteGlobal(me.data?.role);
  const backupsQ = useSuiteConfigurationBackupsQuery(
    editable && tab === "backup" && Boolean(settingsQ.data),
  );
  const updateStatusQ = useSuiteUpdateStatusQuery(
    tab === "upgrade" && Boolean(settingsQ.data),
  );

  const serverCuratedTimezone =
    settingsQ.data &&
    CURATED_TIMEZONE_ID_SET.has(settingsQ.data.app_timezone || "")
      ? settingsQ.data.app_timezone
      : null;

  const timezoneDirty =
    settingsQ.data !== undefined && appTimezone !== serverCuratedTimezone;

  const logsDirty =
    settingsQ.data !== undefined &&
    logRetentionDaysDraft !== null &&
    logRetentionDaysDraft !== String(settingsQ.data.log_retention_days);
  const backupScheduleDirty =
    settingsQ.data !== undefined &&
    (configurationBackupEnabled !==
      Boolean(settingsQ.data.configuration_backup_enabled) ||
      configurationBackupIntervalHours !==
        Number(settingsQ.data.configuration_backup_interval_hours || 24) ||
      configurationBackupPreferredTime !==
        ((
          settingsQ.data.configuration_backup_preferred_time || "02:00"
        ).trim() || "02:00"));
  const isDirty = timezoneDirty || logsDirty || backupScheduleDirty;
  const blocker = useBlocker(
    ({ currentLocation, nextLocation }) =>
      isDirty && currentLocation.pathname !== nextLocation.pathname,
  );
  useEffect(() => {
    if (blocker.state !== "blocked") return;
    if (window.confirm("You have unsaved changes. Leave without saving?")) {
      blocker.proceed();
    } else {
      blocker.reset();
    }
  }, [blocker]);
  useEffect(() => {
    if (!isDirty) return;
    const handler = (e: BeforeUnloadEvent) => {
      e.preventDefault();
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [isDirty]);

  useEffect(() => {
    setTab(normalizeSettingsTab(searchParams.get("tab"), showSupportTab));
  }, [searchParams, showSupportTab]);
  useEffect(() => {
    if (tab === "support" && !showSupportTab) {
      setTab("general");
      const nextParams = new URLSearchParams(searchParams);
      nextParams.delete("tab");
      setSearchParams(nextParams, { replace: true });
    }
  }, [searchParams, setSearchParams, showSupportTab, tab]);

  const loadingAny = settingsQ.isPending || me.isPending;

  async function handleDownloadConfiguration() {
    setBackupErr(null);
    setBackupMsg(null);
    setBackupBusy(true);
    try {
      const bundle = await fetchConfigurationBundle();
      const blob = new Blob([JSON.stringify(bundle, null, 2)], {
        type: "application/json",
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `mediamop-configuration-${new Date().toISOString().slice(0, 10)}.json`;
      a.click();
      URL.revokeObjectURL(url);
      setBackupMsg("Download started.");
    } catch (e) {
      setBackupErr(e instanceof Error ? e.message : "Could not export.");
    } finally {
      setBackupBusy(false);
    }
  }

  async function handleRestoreFileChange(event: ChangeEvent<HTMLInputElement>) {
    const input = event.target;
    const file = input.files?.[0];
    input.value = "";
    if (!file) {
      return;
    }
    setBackupErr(null);
    setBackupMsg(null);
    try {
      const text = await file.text();
      const parsed = JSON.parse(text) as unknown;
      if (typeof parsed !== "object" || parsed === null) {
        setBackupErr("This file is not valid JSON.");
        return;
      }
      const bundle = parsed as ConfigurationBundle;
      if (bundle.format_version !== 1) {
        setBackupErr(
          "This file is not a supported MediaMop configuration export.",
        );
        return;
      }
      if (
        !window.confirm(
          "Replace suite and module settings on this server from this file? This cannot be undone.",
        )
      ) {
        return;
      }
      setBackupBusy(true);
      await putConfigurationBundle(bundle);
      await queryClient.invalidateQueries();
      const refreshed = await settingsQ.refetch();
      if (refreshed.data) {
        const tz = refreshed.data.app_timezone || "";
        setAppTimezone(CURATED_TIMEZONE_ID_SET.has(tz) ? tz : null);
        setLogRetentionDaysDraft(null);
      }
      setBackupMsg("Configuration restored.");
    } catch (e) {
      setBackupErr(e instanceof Error ? e.message : "Could not restore.");
    } finally {
      setBackupBusy(false);
    }
  }

  if (loadingAny) {
    return <PageLoading label="Loading settings" />;
  }

  if (settingsQ.isError) {
    const err = settingsQ.error;
    return (
      <div className="mm-page" data-testid="suite-settings-page">
        <header className="mm-page__intro">
          <p className="mm-page__eyebrow">System</p>
          <h1 className="mm-page__title">Settings</h1>
          <p className="mm-page__lead">
            {isLikelyNetworkFailure(err)
              ? "Could not reach the MediaMop API. Check that the backend is running."
              : isHttpErrorFromApi(err)
                ? "The server refused this request. Sign in again, then try back here."
                : "Something went wrong loading settings."}
          </p>
        </header>
      </div>
    );
  }

  if (!settingsQ.data) {
    return null;
  }

  const normalizedLogRetentionDraft =
    logRetentionDaysDraft !== null
      ? logRetentionDaysDraft
      : String(settingsQ.data.log_retention_days);
  const finalizeLogRetentionDays = (): number => {
    const raw = normalizedLogRetentionDraft.trim();
    if (raw === "") {
      return 30;
    }
    const n = Number(raw);
    if (!Number.isFinite(n)) {
      return settingsQ.data.log_retention_days;
    }
    return Math.min(Math.max(Math.trunc(n), 1), 3650);
  };

  const buildSuitePutBody = (): SuiteSettingsPutBody => {
    const d = settingsQ.data;
    const name = (d.product_display_name || "MediaMop").trim() || "MediaMop";
    const tz = (appTimezone ?? d.app_timezone ?? "UTC").trim() || "UTC";
    const retention = Math.min(
      3650,
      Math.max(1, Math.trunc(Number(finalizeLogRetentionDays()))),
    );
    const body: SuiteSettingsPutBody = {
      product_display_name: name,
      signed_in_home_notice: d.signed_in_home_notice,
      setup_wizard_state: d.setup_wizard_state,
      app_timezone: tz,
      log_retention_days: Number.isFinite(retention)
        ? retention
        : d.log_retention_days,
      application_logs_enabled: true,
      configuration_backup_enabled: Boolean(configurationBackupEnabled),
      configuration_backup_interval_hours: Math.min(
        720,
        Math.max(1, Math.trunc(Number(configurationBackupIntervalHours))),
      ),
      configuration_backup_preferred_time:
        configurationBackupPreferredTime.trim() || "02:00",
    };
    return body;
  };

  async function handleSaveTimezone() {
    if (!settingsQ.data) {
      return;
    }
    setLastSuiteSaveTarget("timezone");
    save.reset();
    try {
      await save.mutateAsync(buildSuitePutBody());
      setLastSuiteSaveTarget(null);
    } catch {
      /* surfaced via save.isError */
    }
  }

  async function handleSaveLogs() {
    if (!settingsQ.data) {
      return;
    }
    setLastSuiteSaveTarget("logs");
    save.reset();
    try {
      await save.mutateAsync(buildSuitePutBody());
      setLastSuiteSaveTarget(null);
    } catch {
      /* surfaced via save.isError */
    }
  }

  async function handleSaveBackupSchedule() {
    if (!settingsQ.data) {
      return;
    }
    setBackupErr(null);
    setBackupMsg(null);
    setLastSuiteSaveTarget("backup");
    save.reset();
    try {
      await save.mutateAsync(buildSuitePutBody());
      setLastSuiteSaveTarget(null);
      setBackupMsg("Backup schedule saved.");
      await queryClient.invalidateQueries({
        queryKey: suiteConfigurationBackupsQueryKey,
      });
    } catch (e) {
      setBackupErr(
        e instanceof Error ? e.message : "Could not save backup schedule.",
      );
    }
  }

  async function handleDownloadStoredBackup(id: number, fileLabel: string) {
    setBackupErr(null);
    setBackupMsg(null);
    setBackupBusy(true);
    try {
      const blob = await fetchStoredConfigurationBackupBlob(id);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = fileLabel.replace(/[^\w.-]+/g, "_").slice(0, 120);
      a.click();
      URL.revokeObjectURL(url);
      setBackupMsg("Download started.");
    } catch (e) {
      setBackupErr(
        e instanceof Error ? e.message : "Could not download snapshot.",
      );
    } finally {
      setBackupBusy(false);
    }
  }

  async function handleResetOperationalHistory() {
    setResetHistoryMsg(null);
    try {
      const result = await resetHistory.mutateAsync(resetHistoryConfirm);
      setResetHistoryConfirm("");
      setResetHistoryMsg(
        `History reset. Removed ${result.total_deleted} old history ${result.total_deleted === 1 ? "item" : "items"}.`,
      );
    } catch {
      /* surfaced below */
    }
  }

  return (
    <div className="mm-page" data-testid="suite-settings-page">
      <header className="mm-page__intro mm-page__intro--suite-settings-rule">
        <p className="mm-page__eyebrow">System</p>
        <h1 className="mm-page__title">Settings</h1>
        <p className="mm-page__lead">
          MediaMop-wide choices that are not part of Refiner or Pruner.
          Integration details stay on their module pages.
        </p>
      </header>

      <div className="mm-page__body max-w-none">
        <div className="mm-settings-workspace">
          <nav className="mm-settings-nav" aria-label="Settings sections">
            <div className="mm-settings-nav__tabs" role="tablist">
              <div className="mm-settings-nav__group">
                <p className="mm-settings-nav__label">Workspace</p>
                <button
                  type="button"
                  role="tab"
                  id="settings-tab-general"
                  aria-controls="settings-panel"
                  aria-label="General"
                  aria-selected={tab === "general"}
                  className={tabButtonClass(tab === "general")}
                  onClick={() => setSettingsTab("general")}
                >
                  <span>
                    <strong>General</strong>
                    <small>Locale, display and history</small>
                  </span>
                </button>
              </div>
              <div className="mm-settings-nav__group">
                <p className="mm-settings-nav__label">Security</p>
                <button
                  type="button"
                  role="tab"
                  id="settings-tab-security"
                  aria-controls="settings-panel"
                  aria-label="Security"
                  aria-selected={tab === "security"}
                  className={tabButtonClass(tab === "security")}
                  onClick={() => setSettingsTab("security")}
                >
                  <span>
                    <strong>Security</strong>
                    <small>Accounts and active sessions</small>
                  </span>
                </button>
              </div>
              <div className="mm-settings-nav__group">
                <p className="mm-settings-nav__label">Operations</p>
                <button
                  type="button"
                  role="tab"
                  id="settings-tab-backup"
                  aria-controls="settings-panel"
                  aria-label="Backup and restore"
                  aria-selected={tab === "backup"}
                  className={tabButtonClass(tab === "backup")}
                  onClick={() => setSettingsTab("backup")}
                >
                  <span>
                    <strong>Backup and restore</strong>
                    <small>Protect and recover configuration</small>
                  </span>
                </button>
                <button
                  type="button"
                  role="tab"
                  id="settings-tab-upgrade"
                  aria-controls="settings-panel"
                  aria-label="Upgrade"
                  aria-selected={tab === "upgrade"}
                  className={tabButtonClass(tab === "upgrade")}
                  onClick={() => setSettingsTab("upgrade")}
                >
                  <span>
                    <strong>Upgrade</strong>
                    <small>Version and update status</small>
                  </span>
                </button>
                <button
                  type="button"
                  role="tab"
                  id="settings-tab-logs"
                  aria-controls="settings-panel"
                  aria-label="Logs"
                  aria-selected={tab === "logs"}
                  className={tabButtonClass(tab === "logs")}
                  onClick={() => setSettingsTab("logs")}
                >
                  <span>
                    <strong>Logs</strong>
                    <small>Diagnostics and runtime events</small>
                  </span>
                </button>
              </div>
              <div className="mm-settings-nav__group">
                <p className="mm-settings-nav__label">Integrations</p>
                <button
                  type="button"
                  role="tab"
                  id="settings-tab-notifications"
                  aria-controls="settings-panel"
                  aria-label="Notifications"
                  aria-selected={tab === "notifications"}
                  className={tabButtonClass(tab === "notifications")}
                  onClick={() => setSettingsTab("notifications")}
                >
                  <span>
                    <strong>Notifications</strong>
                    <small>Delivery channels and alerts</small>
                  </span>
                </button>
                <button
                  type="button"
                  role="tab"
                  id="settings-tab-media-managers"
                  aria-controls="settings-panel"
                  aria-label="Media managers"
                  aria-selected={tab === "media-managers"}
                  className={tabButtonClass(tab === "media-managers")}
                  onClick={() => setSettingsTab("media-managers")}
                >
                  <span>
                    <strong>Media managers</strong>
                    <small>Library automation connections</small>
                  </span>
                </button>
                {showSupportTab ? (
                  <button
                    type="button"
                    role="tab"
                    id="settings-tab-support"
                    aria-controls="settings-panel"
                    aria-label="Support"
                    aria-selected={tab === "support"}
                    className={tabButtonClass(tab === "support")}
                    onClick={() => setSettingsTab("support")}
                  >
                    <span>
                      <strong>Support</strong>
                      <small>Help fund and maintain MediaMop</small>
                    </span>
                  </button>
                ) : null}
              </div>
            </div>
          </nav>

          <main
            id="settings-panel"
            className="mm-settings-workspace__content"
            role="tabpanel"
            aria-labelledby={`settings-tab-${tab}`}
          >
            {tab === "general" ? (
              <SettingsGeneralTab
                editable={editable}
                settingsData={settingsQ.data}
                save={save}
                appTimezone={appTimezone}
                setAppTimezone={setAppTimezone}
                timezoneDirty={timezoneDirty}
                setLogRetentionDaysDraft={setLogRetentionDaysDraft}
                normalizedLogRetentionDraft={normalizedLogRetentionDraft}
                finalizeLogRetentionDays={finalizeLogRetentionDays}
                logsDirty={logsDirty}
                lastSuiteSaveTarget={lastSuiteSaveTarget}
                displayDensity={displayDensity}
                setDisplayDensity={setDisplayDensity}
                resetHistoryConfirm={resetHistoryConfirm}
                setResetHistoryConfirm={setResetHistoryConfirm}
                resetHistory={resetHistory}
                resetHistoryMsg={resetHistoryMsg}
                onSaveTimezone={() => void handleSaveTimezone()}
                onSaveLogs={() => void handleSaveLogs()}
                onResetOperationalHistory={() =>
                  void handleResetOperationalHistory()
                }
              />
            ) : tab === "backup" ? (
              <SettingsBackupTab
                editable={editable}
                settingsData={settingsQ.data}
                save={save}
                backupScheduleDirty={backupScheduleDirty}
                lastSuiteSaveTarget={lastSuiteSaveTarget}
                configurationBackupEnabled={configurationBackupEnabled}
                setConfigurationBackupEnabled={setConfigurationBackupEnabled}
                configurationBackupIntervalHours={
                  configurationBackupIntervalHours
                }
                setConfigurationBackupIntervalHours={
                  setConfigurationBackupIntervalHours
                }
                configurationBackupPreferredTime={
                  configurationBackupPreferredTime
                }
                setConfigurationBackupPreferredTime={
                  setConfigurationBackupPreferredTime
                }
                backupsQ={backupsQ}
                backupBusy={backupBusy}
                backupMsg={backupMsg}
                backupErr={backupErr}
                onSaveBackupSchedule={() => void handleSaveBackupSchedule()}
                onDownloadConfiguration={() =>
                  void handleDownloadConfiguration()
                }
                onRestoreFileChange={(e) => void handleRestoreFileChange(e)}
                onDownloadStoredBackup={(id, fileLabel) =>
                  void handleDownloadStoredBackup(id, fileLabel)
                }
              />
            ) : tab === "upgrade" ? (
              <SettingsUpgradeTab updateStatusQ={updateStatusQ} />
            ) : tab === "security" ? (
              <SettingsSecurityTab />
            ) : tab === "media-managers" ? (
              <SettingsMediaManagersTab />
            ) : tab === "notifications" ? (
              <SettingsNotificationsTab />
            ) : tab === "support" ? (
              <SettingsSupportTab />
            ) : (
              <SettingsLogsTab />
            )}
          </main>
        </div>
      </div>
    </div>
  );
}
