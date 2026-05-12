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
  suiteUpdateDiagnosticsQueryKey,
  suiteUpdateStatusQueryKey,
  useSuiteConfigurationBackupsQuery,
  useSuiteOperationalHistoryResetMutation,
  useSuiteSettingsQuery,
  useSuiteSettingsSaveMutation,
  useSuiteUpdateDiagnosticsQuery,
  useSuiteUpdateNowMutation,
  useSuiteUpdateStatusQuery,
} from "../../lib/suite/queries";
import type {
  SuiteSettingsPutBody,
  SuiteUpdateStatusOut,
  SuiteUpgradeProgressOut,
} from "../../lib/suite/types";
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
import {
  type UpgradeMonitor,
  type UpgradeNotice,
  type UpgradeHistoryItem,
  isUpgradeProgressActive,
} from "./settings-shared";
import { SettingsGeneralTab } from "./settings-general-tab";
import { SettingsBackupTab } from "./settings-backup-tab";
import { SettingsUpgradeTab } from "./settings-upgrade-tab";
import { SettingsSecurityTab } from "./settings-security-tab";
import { SettingsLogsTab } from "./settings-logs-tab";
import { SettingsSupportTab } from "./settings-support-tab";
import { SettingsNotificationsTab } from "./settings-notifications-tab";

function canEditSuiteGlobal(role: string | undefined): boolean {
  return role === "operator" || role === "admin";
}

type TabId = "general" | "backup" | "upgrade" | "security" | "logs" | "notifications" | "support";

function tabButtonClass(active: boolean): string {
  return [
    "shrink-0 whitespace-nowrap rounded-md border px-3 py-1.5 text-sm font-medium transition-colors",
    active
      ? "border-[var(--mm-accent)] bg-[var(--mm-accent)]/15 text-[var(--mm-text)]"
      : "border-[var(--mm-border)] bg-transparent text-[var(--mm-text2)] hover:bg-[var(--mm-card-bg)]",
  ].join(" ");
}

const UPGRADE_VERIFICATION_TIMEOUT_MS = 8 * 60_000;
const UPGRADE_HISTORY_STORAGE_KEY = "mediamop.upgrade.history.v1";
const UPGRADE_HISTORY_LIMIT = 20;

function parseUpgradeTime(raw: string | null | undefined): number | null {
  if (!raw) {
    return null;
  }
  const parsed = Date.parse(raw);
  return Number.isFinite(parsed) ? parsed : null;
}

function readUpgradeHistory(): UpgradeHistoryItem[] {
  if (typeof window === "undefined") {
    return [];
  }
  try {
    const raw = window.localStorage.getItem(UPGRADE_HISTORY_STORAGE_KEY);
    if (!raw) {
      return [];
    }
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) {
      return [];
    }
    return parsed.filter((row): row is UpgradeHistoryItem => {
      if (!row || typeof row !== "object") {
        return false;
      }
      const id = (row as { id?: unknown }).id;
      return typeof id === "string" && id.trim().length > 0;
    });
  } catch {
    return [];
  }
}

function persistUpgradeHistory(items: UpgradeHistoryItem[]): void {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.setItem(
    UPGRADE_HISTORY_STORAGE_KEY,
    JSON.stringify(items.slice(0, UPGRADE_HISTORY_LIMIT)),
  );
}

function buildUpgradeHistoryItem(
  progressSummary: { label: string; body: string },
  progress: SuiteUpgradeProgressOut,
): UpgradeHistoryItem {
  const updatedAt =
    progress.last_updated_at ||
    progress.last_completed_at ||
    progress.last_started_at ||
    "unknown";
  const attemptId = progress.attempt_id || null;
  const phase = progress.phase || "unknown";
  const dedupeStamp = `${attemptId ?? "no-attempt"}:${phase}:${updatedAt}`;
  return {
    id: dedupeStamp,
    recorded_at: updatedAt,
    status_label: progressSummary.label,
    phase,
    attempt_id: attemptId,
    target_version: progress.target_version || null,
    current_version_seen: progress.current_version_seen || null,
    message: progressSummary.body,
    installer_log_path: progress.installer_log_path || null,
    service_log_path: progress.service_log_path || null,
  };
}

function describeUpgradeProgress(
  status: SuiteUpdateStatusOut | undefined,
  progress: SuiteUpgradeProgressOut | null | undefined,
  monitor: UpgradeMonitor | null,
  disconnected: boolean,
): { label: string; body: string } | null {
  const progressIsActive = isUpgradeProgressActive(progress);
  const hideHistoricalCompletedSummary = Boolean(
    progress &&
    progress.phase === "completed" &&
    status &&
    progress.target_version &&
    status.current_version === progress.target_version &&
    status.status === "update_available" &&
    !monitor?.active,
  );
  if (monitor?.timedOutReason) {
    return {
      label: "Failed",
      body: monitor.timedOutReason,
    };
  }
  if (disconnected && monitor?.active) {
    return {
      label: "Reconnecting",
      body: "MediaMop is reconnecting and verifying the installed version.",
    };
  }
  if (!progress) {
    if (!monitor?.active) {
      return null;
    }
    return {
      label: "Waiting",
      body: "Upgrade request accepted. MediaMop is checking release metadata.",
    };
  }
  if (
    !monitor?.active &&
    progress.phase !== "failed" &&
    !progressIsActive &&
    progress.phase !== "completed"
  ) {
    return null;
  }
  if (hideHistoricalCompletedSummary) {
    return null;
  }
  switch (progress.phase) {
    case "checking":
      return {
        label: "Checking release",
        body:
          progress.message ||
          "Upgrade request accepted. MediaMop is checking release metadata.",
      };
    case "downloading":
      return {
        label: "Downloading",
        body:
          progress.message ||
          "Upgrade request accepted. MediaMop is downloading the installer.",
      };
    case "verifying_download":
      return {
        label: "Verifying installer",
        body: progress.message || "Installer is being verified.",
      };
    case "installer_started":
      return {
        label: "Starting installer",
        body: progress.message || "Installer is starting.",
      };
    case "installer_running":
      return {
        label: "Installer running",
        body:
          progress.message ||
          "Installer is running. MediaMop may temporarily disconnect.",
      };
    case "restarting":
    case "verifying_install":
      return {
        label: "Verifying installed version",
        body:
          progress.message ||
          "MediaMop is reconnecting and verifying the installed version.",
      };
    case "completed":
      if (
        status &&
        progress.target_version &&
        status.current_version === progress.target_version
      ) {
        return {
          label: "Completed",
          body:
            progress.message ||
            `Upgrade completed. Running version: ${status.current_version}.`,
        };
      }
      return {
        label: "Verifying installed version",
        body: "Upgrade reported completed, but the running version has not been confirmed yet.",
      };
    case "failed":
      return {
        label: "Failed",
        body: progress.last_error
          ? `Upgrade failed: ${progress.last_error}`
          : progress.message || "Upgrade failed.",
      };
    default:
      return {
        label: "Upgrade status",
        body: progress.message || "Updater status is available.",
      };
  }
}

export function verifiedUpgradeRefreshKey(
  status: SuiteUpdateStatusOut | undefined,
  progress: SuiteUpgradeProgressOut | null | undefined,
  monitor: UpgradeMonitor | null,
): string | null {
  if (!status || status.install_type !== "windows" || !monitor?.active) {
    return null;
  }
  const targetVersion = (
    progress?.target_version ||
    monitor.targetVersion ||
    ""
  ).trim();
  if (!targetVersion || status.current_version !== targetVersion) {
    return null;
  }
  if (progress && progress.phase !== "completed") {
    return null;
  }
  return [
    progress?.attempt_id || monitor.attemptId || "unknown-attempt",
    targetVersion,
  ].join(":");
}

function completedUpgradeRefreshKey(
  status: SuiteUpdateStatusOut | undefined,
  progress: SuiteUpgradeProgressOut | null | undefined,
): string | null {
  if (!status || status.install_type !== "windows" || !progress) {
    return null;
  }
  const targetVersion = progress.target_version?.trim();
  if (
    !targetVersion ||
    progress.phase !== "completed" ||
    status.current_version !== targetVersion
  ) {
    return null;
  }
  return [progress.attempt_id || "unknown-attempt", targetVersion].join(":");
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
  const updateNow = useSuiteUpdateNowMutation();
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
    setSearchParams(nextParams, { replace: true });
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
  const [upgradeNotice, setUpgradeNotice] = useState<UpgradeNotice | null>(
    null,
  );
  const [upgradeMonitor, setUpgradeMonitor] = useState<UpgradeMonitor | null>(
    null,
  );
  const [upgradePollActive, setUpgradePollActive] = useState(false);
  const [showUpgradeHistory, setShowUpgradeHistory] = useState(false);
  const [upgradeHistory, setUpgradeHistory] = useState<UpgradeHistoryItem[]>(
    () => readUpgradeHistory(),
  );
  const [showUpgradeDiagnostics, setShowUpgradeDiagnostics] = useState(false);
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
  const upgradePollingMs =
    tab === "upgrade" && (upgradeMonitor?.active || upgradePollActive)
      ? Math.min(10_000, 1500 * ((upgradeMonitor?.disconnects ?? 0) + 1))
      : false;
  const updateStatusQ = useSuiteUpdateStatusQuery(
    tab === "upgrade" && Boolean(settingsQ.data),
    upgradePollingMs,
  );
  const updateDiagnosticsQ = useSuiteUpdateDiagnosticsQuery(
    tab === "upgrade" &&
      showUpgradeDiagnostics &&
      Boolean(settingsQ.data) &&
      updateStatusQ.data?.install_type === "windows",
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

  const upgradeBootstrapRequired =
    updateStatusQ.data?.install_type === "windows" &&
    !updateStatusQ.data.in_app_upgrade_supported &&
    (updateStatusQ.data.in_app_upgrade_summary || "")
      .toLowerCase()
      .includes("does not have the mediamop updater service yet");
  const activeUpgradeProgress = updateStatusQ.data?.upgrade;
  const upgradeConnectionLost =
    Boolean(upgradeMonitor?.active) && updateStatusQ.isError;
  const upgradeProgressSummary = describeUpgradeProgress(
    updateStatusQ.data,
    activeUpgradeProgress,
    upgradeMonitor,
    upgradeConnectionLost,
  );
  const upgradeInProgress =
    !upgradeMonitor?.timedOutReason &&
    (Boolean(upgradeMonitor?.active) ||
      isUpgradeProgressActive(activeUpgradeProgress));
  const completedUpgradeRefreshPromptKey = completedUpgradeRefreshKey(
    updateStatusQ.data,
    activeUpgradeProgress,
  );
  const hasStableUpdateStatus = Boolean(updateStatusQ.data);
  const upgradeRefreshBusy = upgradeInProgress || updateStatusQ.isFetching;
  const upgradeRefreshLabel = upgradeInProgress
    ? "Checking progress..."
    : !hasStableUpdateStatus && updateStatusQ.isFetching
      ? "Checking..."
      : "Check again";
  const diagnosticsUpgrade =
    updateDiagnosticsQ.data?.upgrade ?? activeUpgradeProgress ?? null;
  const installerLogTail = updateDiagnosticsQ.data?.installer_log_tail ?? [];
  const serviceLogTail = updateDiagnosticsQ.data?.service_log_tail ?? [];
  const diagnosticsHasLogTail =
    installerLogTail.length > 0 || serviceLogTail.length > 0;

  useEffect(() => {
    if (isUpgradeProgressActive(activeUpgradeProgress)) {
      setUpgradePollActive(true);
      return;
    }
    if (!upgradeMonitor?.active) {
      setUpgradePollActive(false);
    }
  }, [activeUpgradeProgress, upgradeMonitor?.active]);

  useEffect(() => {
    if (!activeUpgradeProgress || !upgradeProgressSummary) {
      return;
    }
    const item = buildUpgradeHistoryItem(
      upgradeProgressSummary,
      activeUpgradeProgress,
    );
    setUpgradeHistory((current) => {
      if (current.some((existing) => existing.id === item.id)) {
        return current;
      }
      const next = [item, ...current].slice(0, UPGRADE_HISTORY_LIMIT);
      persistUpgradeHistory(next);
      return next;
    });
  }, [activeUpgradeProgress, upgradeProgressSummary]);

  useEffect(() => {
    if (!updateStatusQ.data?.upgrade) {
      return;
    }
    const progress = updateStatusQ.data.upgrade;
    if (!isUpgradeProgressActive(progress)) {
      return;
    }
    setUpgradeMonitor((current) => {
      if (
        current?.active &&
        current.attemptId === (progress.attempt_id ?? null) &&
        current.targetVersion === (progress.target_version || "").trim()
      ) {
        return current;
      }
      return {
        attemptId: progress.attempt_id ?? null,
        targetVersion: (progress.target_version || "").trim(),
        disconnects: 0,
        active: true,
        startedAtMs:
          parseUpgradeTime(progress.last_started_at) ??
          parseUpgradeTime(progress.last_updated_at) ??
          Date.now(),
        timedOutReason: null,
      };
    });
  }, [updateStatusQ.data]);

  useEffect(() => {
    if (!upgradeMonitor?.active || updateStatusQ.errorUpdatedAt === 0) {
      return;
    }
    setUpgradeMonitor((current) => {
      if (!current?.active) {
        return current;
      }
      return {
        ...current,
        disconnects: Math.min(current.disconnects + 1, 6),
      };
    });
  }, [upgradeMonitor?.active, updateStatusQ.errorUpdatedAt]);

  useEffect(() => {
    if (!upgradeMonitor || !updateStatusQ.data) {
      return;
    }
    const progress = updateStatusQ.data.upgrade;
    setUpgradeMonitor((current) => {
      if (!current?.active) {
        return current;
      }
      if (current.disconnects === 0) {
        return current;
      }
      return { ...current, disconnects: 0 };
    });
    if (progress?.phase === "failed") {
      setUpgradePollActive(false);
      setUpgradeMonitor((current) =>
        current ? { ...current, active: false, timedOutReason: null } : current,
      );
      setUpgradeNotice({
        tone: "error",
        text: progress.last_error
          ? `Upgrade failed: ${progress.last_error}`
          : progress.message || "Upgrade failed.",
      });
      return;
    }
    const refreshAttemptKey = verifiedUpgradeRefreshKey(
      updateStatusQ.data,
      progress,
      upgradeMonitor,
    );
    if (refreshAttemptKey) {
      setUpgradePollActive(false);
      setUpgradeMonitor((current) =>
        current ? { ...current, active: false, timedOutReason: null } : current,
      );
      setUpgradeNotice({
        tone: "success",
        text:
          progress?.message ||
          `Upgrade completed. Running version: ${updateStatusQ.data.current_version}.`,
      });
    }
  }, [upgradeMonitor, updateStatusQ.data]);

  useEffect(() => {
    if (!upgradeMonitor?.active) {
      return;
    }
    const targetVersion = upgradeMonitor.targetVersion.trim();
    if (!targetVersion || !updateStatusQ.data) {
      return;
    }
    if (updateStatusQ.data.current_version === targetVersion) {
      return;
    }
    const elapsed = Date.now() - upgradeMonitor.startedAtMs;
    if (elapsed < UPGRADE_VERIFICATION_TIMEOUT_MS) {
      return;
    }
    const currentVersionSeen =
      activeUpgradeProgress?.current_version_seen ||
      updateStatusQ.data.current_version ||
      "unknown";
    const reason =
      `Upgrade failed: MediaMop did not verify version ${targetVersion} within ${Math.floor(UPGRADE_VERIFICATION_TIMEOUT_MS / 60_000)} minutes. ` +
      `The running app still reports ${currentVersionSeen}.`;
    setUpgradePollActive(false);
    setUpgradeMonitor((current) =>
      current
        ? {
            ...current,
            active: false,
            timedOutReason: reason,
          }
        : current,
    );
    setUpgradeNotice({
      tone: "error",
      text: reason,
    });
  }, [
    activeUpgradeProgress?.current_version_seen,
    activeUpgradeProgress?.phase,
    updateStatusQ.data,
    upgradeMonitor,
  ]);

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

  async function handleUpgradeNow() {
    setUpgradeNotice(null);
    try {
      const result = await updateNow.mutateAsync();
      if (result.status === "started") {
        setUpgradePollActive(true);
        setUpgradeMonitor({
          attemptId: result.attempt_id ?? null,
          targetVersion: (
            result.target_version ||
            updateStatusQ.data?.latest_version ||
            ""
          ).trim(),
          disconnects: 0,
          active: true,
          startedAtMs: Date.now(),
          timedOutReason: null,
        });
        await queryClient.invalidateQueries({
          queryKey: suiteUpdateStatusQueryKey,
        });
        await queryClient.invalidateQueries({
          queryKey: suiteUpdateDiagnosticsQueryKey,
        });
      } else {
        setUpgradeNotice({
          tone: "info",
          text: result.message,
        });
        void queryClient.invalidateQueries({
          queryKey: suiteUpdateStatusQueryKey,
        });
        void queryClient.invalidateQueries({
          queryKey: suiteUpdateDiagnosticsQueryKey,
        });
      }
    } catch {
      /* surfaced below */
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
          MediaMop-wide choices that are not part of Refiner, Pruner, or Subber.
          Integration details stay on their module pages.
        </p>
      </header>

      <div className="mm-page__body max-w-none">
        <div
          className="mb-5 flex gap-2 overflow-x-auto sm:flex-wrap sm:overflow-visible"
          role="tablist"
          aria-label="Settings sections"
        >
          <button
            type="button"
            role="tab"
            aria-selected={tab === "general"}
            className={tabButtonClass(tab === "general")}
            onClick={() => setSettingsTab("general")}
          >
            General
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={tab === "security"}
            className={tabButtonClass(tab === "security")}
            onClick={() => setSettingsTab("security")}
          >
            Security
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={tab === "backup"}
            className={tabButtonClass(tab === "backup")}
            onClick={() => setSettingsTab("backup")}
          >
            Backup and restore
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={tab === "upgrade"}
            className={tabButtonClass(tab === "upgrade")}
            onClick={() => setSettingsTab("upgrade")}
          >
            Upgrade
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={tab === "logs"}
            className={tabButtonClass(tab === "logs")}
            onClick={() => setSettingsTab("logs")}
          >
            Logs
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={tab === "notifications"}
            className={tabButtonClass(tab === "notifications")}
            onClick={() => setSettingsTab("notifications")}
          >
            Notifications
          </button>
          {showSupportTab ? (
            <button
              type="button"
              role="tab"
              aria-selected={tab === "support"}
              className={tabButtonClass(tab === "support")}
              onClick={() => setSettingsTab("support")}
            >
              Support
            </button>
          ) : null}
        </div>

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
            configurationBackupIntervalHours={configurationBackupIntervalHours}
            setConfigurationBackupIntervalHours={
              setConfigurationBackupIntervalHours
            }
            configurationBackupPreferredTime={configurationBackupPreferredTime}
            setConfigurationBackupPreferredTime={
              setConfigurationBackupPreferredTime
            }
            backupsQ={backupsQ}
            backupBusy={backupBusy}
            backupMsg={backupMsg}
            backupErr={backupErr}
            onSaveBackupSchedule={() => void handleSaveBackupSchedule()}
            onDownloadConfiguration={() => void handleDownloadConfiguration()}
            onRestoreFileChange={(e) => void handleRestoreFileChange(e)}
            onDownloadStoredBackup={(id, fileLabel) =>
              void handleDownloadStoredBackup(id, fileLabel)
            }
          />
        ) : tab === "upgrade" ? (
          <SettingsUpgradeTab
            upgradeMonitor={upgradeMonitor}
            upgradeNotice={upgradeNotice}
            showUpgradeHistory={showUpgradeHistory}
            setShowUpgradeHistory={setShowUpgradeHistory}
            upgradeHistory={upgradeHistory}
            showUpgradeDiagnostics={showUpgradeDiagnostics}
            setShowUpgradeDiagnostics={setShowUpgradeDiagnostics}
            upgradeBootstrapRequired={upgradeBootstrapRequired}
            activeUpgradeProgress={activeUpgradeProgress}
            upgradeConnectionLost={upgradeConnectionLost}
            upgradeProgressSummary={upgradeProgressSummary}
            upgradeInProgress={upgradeInProgress}
            completedUpgradeRefreshPromptKey={completedUpgradeRefreshPromptKey}
            upgradeRefreshBusy={upgradeRefreshBusy}
            upgradeRefreshLabel={upgradeRefreshLabel}
            diagnosticsUpgrade={diagnosticsUpgrade}
            installerLogTail={installerLogTail}
            serviceLogTail={serviceLogTail}
            diagnosticsHasLogTail={diagnosticsHasLogTail}
            updateStatusQ={updateStatusQ}
            updateDiagnosticsQ={updateDiagnosticsQ}
            updateNow={updateNow}
            onUpgradeNow={() => void handleUpgradeNow()}
          />
        ) : tab === "security" ? (
          <SettingsSecurityTab />
        ) : tab === "notifications" ? (
          <SettingsNotificationsTab />
        ) : tab === "support" ? (
          <SettingsSupportTab />
        ) : (
          <SettingsLogsTab />
        )}
      </div>
    </div>
  );
}
