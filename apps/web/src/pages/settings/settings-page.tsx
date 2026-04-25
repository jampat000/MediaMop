import { useQueryClient } from "@tanstack/react-query";
import type { ChangeEvent } from "react";
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { PageLoading } from "../../components/shared/page-loading";
import { isHttpErrorFromApi, isLikelyNetworkFailure } from "../../lib/api/error-guards";
import { useChangePasswordMutation } from "../../lib/auth/queries";
import { useMeQuery } from "../../lib/auth/queries";
import {
  CURATED_TIMEZONE_ID_SET,
  curatedTimezoneOptionsSorted,
} from "../../lib/suite/timezone-options";
import { MmListboxPicker } from "../../components/ui/mm-listbox-picker";
import { mmActionButtonClass, mmEditableTextFieldClass } from "../../lib/ui/mm-control-roles";
import { mmModuleTabBlurbBandClass, mmModuleTabBlurbTextClass } from "../../lib/ui/mm-module-tab-blurb";
import {
  suiteConfigurationBackupsQueryKey,
  useSuiteConfigurationBackupsQuery,
  useSuiteLogsQuery,
  useSuiteMetricsQuery,
  useSuiteSettingsQuery,
  useSuiteSettingsSaveMutation,
  useSuiteUpdateNowMutation,
  useSuiteUpdateStatusQuery,
} from "../../lib/suite/queries";
import type { SuiteLogEntry, SuiteSettingsPutBody } from "../../lib/suite/types";
import {
  fetchConfigurationBundle,
  fetchStoredConfigurationBackupBlob,
  putConfigurationBundle,
  type ConfigurationBundle,
} from "../../lib/suite/suite-settings-api";
import {
  persistDisplayDensity,
  readStoredDisplayDensity,
  type DisplayDensity,
} from "../../lib/ui/display-density";
import { useAppDateFormatter } from "../../lib/ui/mm-format-date";

function canEditSuiteGlobal(role: string | undefined): boolean {
  return role === "operator" || role === "admin";
}

type TabId = "general" | "security" | "logs";

const SUITE_PASSWORD_FIELD_CLASS =
  "mm-input w-full min-w-0 flex-1 text-sm tracking-normal text-[var(--mm-text)]";

function formatChangePasswordMutationError(err: unknown): string {
  if (err instanceof Error) {
    return err.message;
  }
  if (typeof err === "string") {
    return err;
  }
  return "Could not change password.";
}

function tabButtonClass(active: boolean): string {
  return [
    "shrink-0 whitespace-nowrap rounded-md border px-3 py-1.5 text-sm font-medium transition-colors",
    active
      ? "border-[var(--mm-accent)] bg-[var(--mm-accent)]/15 text-[var(--mm-text)]"
      : "border-[var(--mm-border)] bg-transparent text-[var(--mm-text2)] hover:bg-[var(--mm-card-bg)]",
  ].join(" ");
}

const SUITE_SETTINGS_DASH_CARD_CLASS =
  "mm-card mm-dash-card flex min-h-0 min-w-0 flex-col gap-5";
const SUITE_SETTINGS_PREMIUM_PANEL_CLASS =
  "flex min-h-0 min-w-0 flex-col gap-4 rounded-xl border border-[var(--mm-border)] bg-[var(--mm-card-bg)]/80 p-4 shadow-[var(--mm-shadow-card-inner)]";
const SUITE_SETTINGS_PREMIUM_TILE_CLASS =
  "rounded-xl border border-[var(--mm-border)] bg-[var(--mm-card-bg)]/80 px-4 py-3 shadow-[var(--mm-shadow-card-inner)]";
const CONFIGURATION_BACKUP_INTERVAL_HOURS = [6, 12, 24, 48, 72, 168] as const;

type LogLevelFilter = "" | "INFO" | "WARNING" | "ERROR";

function formatBackupBytes(n: number): string {
  if (n < 1024) {
    return `${n} B`;
  }
  if (n < 1024 * 1024) {
    return `${(n / 1024).toFixed(1)} KB`;
  }
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

function logCardTone(level: string): string {
  switch (level.toUpperCase()) {
    case "ERROR":
    case "CRITICAL":
      return "border-red-500/35 bg-red-950/20";
    case "WARNING":
      return "border-amber-400/35 bg-amber-950/20";
    default:
      return "border-[var(--mm-border)] bg-[var(--mm-card-bg)]/50";
  }
}

function logLevelBadgeTone(level: string): string {
  switch (level.toUpperCase()) {
    case "ERROR":
    case "CRITICAL":
      return "border-red-500/40 bg-red-500/10 text-red-100";
    case "WARNING":
      return "border-amber-400/40 bg-amber-400/10 text-amber-100";
    default:
      return "border-[var(--mm-border)] bg-black/10 text-[var(--mm-text2)]";
  }
}

function renderLogTechnicalDetails(entry: SuiteLogEntry) {
  if (!entry.traceback && !entry.source && !entry.logger && !entry.correlation_id && !entry.job_id) {
    return null;
  }
  return (
    <details className="rounded-md border border-[var(--mm-border)] bg-black/10 px-3 py-2">
      <summary className="cursor-pointer text-sm font-medium text-[var(--mm-text2)]">Technical details</summary>
      <div className="mt-3 space-y-2 text-sm text-[var(--mm-text2)]">
        {entry.source ? (
          <p>
            <span className="font-medium text-[var(--mm-text1)]">Source:</span> {entry.source}
          </p>
        ) : null}
        {entry.logger ? (
          <p>
            <span className="font-medium text-[var(--mm-text1)]">Logger:</span> {entry.logger}
          </p>
        ) : null}
        {entry.correlation_id ? (
          <p>
            <span className="font-medium text-[var(--mm-text1)]">Request ID:</span> {entry.correlation_id}
          </p>
        ) : null}
        {entry.job_id ? (
          <p>
            <span className="font-medium text-[var(--mm-text1)]">Job ID:</span> {entry.job_id}
          </p>
        ) : null}
        {entry.traceback ? (
          <pre className="overflow-auto rounded-md border border-[var(--mm-border)] bg-black/20 p-3 text-xs leading-5 text-[var(--mm-text2)] whitespace-pre-wrap">
            {entry.traceback}
          </pre>
        ) : null}
      </div>
    </details>
  );
}

function SettingsSummaryCard({ label, value }: { label: string; value: string }) {
  return (
    <section className="rounded-lg border border-[var(--mm-border)] bg-[var(--mm-card-bg)] px-4 py-3">
      <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--mm-text3)]">{label}</p>
      <p className="mt-1 text-lg font-semibold text-[var(--mm-text1)]">{value}</p>
    </section>
  );
}

function formatRuntimeUptime(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds <= 0) return "Just started";
  const totalSeconds = Math.max(0, Math.floor(seconds));
  const days = Math.floor(totalSeconds / 86400);
  const hours = Math.floor((totalSeconds % 86400) / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  if (days > 0) return `${days}d ${hours}h`;
  if (hours > 0) return `${hours}h ${minutes}m`;
  return `${minutes}m`;
}

function formatAverageMs(value: number): string {
  if (!Number.isFinite(value) || value <= 0) return "0 ms";
  return `${value >= 100 ? value.toFixed(0) : value.toFixed(1)} ms`;
}

function requestIssueSummary(statusCounts: Record<string, number> | undefined): { value: string; detail: string } {
  const counts = statusCounts ?? {};
  const success = counts["2xx"] ?? 0;
  const redirects = counts["3xx"] ?? 0;
  const rejectedOrMissing = counts["4xx"] ?? 0;
  const serverFailures = counts["5xx"] ?? 0;
  const detail = `Successful ${success} - Redirected ${redirects} - Rejected or not found ${rejectedOrMissing} - Server failures ${serverFailures}`;
  if (serverFailures > 0) {
    return { value: `${serverFailures} server ${serverFailures === 1 ? "failure" : "failures"}`, detail };
  }
  if (rejectedOrMissing > 0) {
    return { value: `${rejectedOrMissing} request ${rejectedOrMissing === 1 ? "issue" : "issues"}`, detail };
  }
  return { value: "No request issues", detail };
}

/** Settings: General (timezone, display density, configuration export), Security, Logs (retention + recent events). */
export function SettingsPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const formatDateTime = useAppDateFormatter();
  const me = useMeQuery();
  const changePassword = useChangePasswordMutation();
  const settingsQ = useSuiteSettingsQuery();
  const save = useSuiteSettingsSaveMutation();
  const updateNow = useSuiteUpdateNowMutation();

  const [tab, setTab] = useState<TabId>("general");
  const [appTimezone, setAppTimezone] = useState<string | null>(null);
  const [logRetentionDaysDraft, setLogRetentionDaysDraft] = useState<string | null>(null);
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showCurrentPassword, setShowCurrentPassword] = useState(false);
  const [showNewPassword, setShowNewPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [changePasswordStatus, setChangePasswordStatus] = useState<string | null>(null);
  const [displayDensity, setDisplayDensity] = useState<DisplayDensity>(() => readStoredDisplayDensity());
  const [backupBusy, setBackupBusy] = useState(false);
  const [backupMsg, setBackupMsg] = useState<string | null>(null);
  const [backupErr, setBackupErr] = useState<string | null>(null);
  const [upgradeMsg, setUpgradeMsg] = useState<string | null>(null);
  const [configurationBackupEnabled, setConfigurationBackupEnabled] = useState(false);
  const [configurationBackupIntervalHours, setConfigurationBackupIntervalHours] = useState(24);
  const [configurationBackupPreferredTime, setConfigurationBackupPreferredTime] = useState("02:00");
  const [lastSuiteSaveTarget, setLastSuiteSaveTarget] = useState<"timezone" | "logs" | "backup" | null>(null);
  const [logSearch, setLogSearch] = useState("");
  const [logLevel, setLogLevel] = useState<LogLevelFilter>("");
  const [tracebacksOnly, setTracebacksOnly] = useState(false);
  const restoreInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!settingsQ.data) {
      return;
    }
    const fromServer = settingsQ.data.app_timezone || "";
    setAppTimezone(CURATED_TIMEZONE_ID_SET.has(fromServer) ? fromServer : null);
    setLogRetentionDaysDraft(null);
    setConfigurationBackupEnabled(Boolean(settingsQ.data.configuration_backup_enabled));
    setConfigurationBackupIntervalHours(
      Number.isFinite(Number(settingsQ.data.configuration_backup_interval_hours))
        ? Number(settingsQ.data.configuration_backup_interval_hours)
        : 24,
    );
    setConfigurationBackupPreferredTime(
      (settingsQ.data.configuration_backup_preferred_time || "02:00").trim() || "02:00",
    );
  }, [settingsQ.data]);

  const editable = canEditSuiteGlobal(me.data?.role);
  const backupsQ = useSuiteConfigurationBackupsQuery(editable && tab === "general" && Boolean(settingsQ.data));
  const updateStatusQ = useSuiteUpdateStatusQuery(tab === "general" && Boolean(settingsQ.data));
  const logsQ = useSuiteLogsQuery(
    {
      level: logLevel || undefined,
      search: logSearch.trim() || undefined,
      has_exception: tracebacksOnly ? true : undefined,
      limit: 100,
    },
    tab === "logs" && Boolean(settingsQ.data),
  );
  const metricsQ = useSuiteMetricsQuery(tab === "logs" && Boolean(settingsQ.data));

  const serverCuratedTimezone =
    settingsQ.data && CURATED_TIMEZONE_ID_SET.has(settingsQ.data.app_timezone || "") ? settingsQ.data.app_timezone : null;

  const timezoneDirty = settingsQ.data !== undefined && appTimezone !== serverCuratedTimezone;

  const logsDirty =
    settingsQ.data !== undefined &&
    logRetentionDaysDraft !== null &&
    logRetentionDaysDraft !== String(settingsQ.data.log_retention_days);
  const backupScheduleDirty =
    settingsQ.data !== undefined &&
    (configurationBackupEnabled !== Boolean(settingsQ.data.configuration_backup_enabled) ||
      configurationBackupIntervalHours !== Number(settingsQ.data.configuration_backup_interval_hours || 24) ||
      configurationBackupPreferredTime !== ((settingsQ.data.configuration_backup_preferred_time || "02:00").trim() || "02:00"));

  const loadingAny = settingsQ.isPending || me.isPending;

  async function handleDownloadConfiguration() {
    setBackupErr(null);
    setBackupMsg(null);
    setBackupBusy(true);
    try {
      const bundle = await fetchConfigurationBundle();
      const blob = new Blob([JSON.stringify(bundle, null, 2)], { type: "application/json" });
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
        setBackupErr("This file is not a supported MediaMop configuration export.");
        return;
      }
      if (!window.confirm("Replace suite and module settings on this server from this file? This cannot be undone.")) {
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

  const timezoneOptions = curatedTimezoneOptionsSorted();
  const normalizedLogRetentionDraft =
    logRetentionDaysDraft !== null ? logRetentionDaysDraft : String(settingsQ.data.log_retention_days);
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
    const retention = Math.min(3650, Math.max(1, Math.trunc(Number(finalizeLogRetentionDays()))));
    const body: SuiteSettingsPutBody = {
      product_display_name: name,
      signed_in_home_notice: d.signed_in_home_notice,
      setup_wizard_state: d.setup_wizard_state,
      app_timezone: tz,
      log_retention_days: Number.isFinite(retention) ? retention : d.log_retention_days,
      application_logs_enabled: true,
      configuration_backup_enabled: Boolean(configurationBackupEnabled),
      configuration_backup_interval_hours: Math.min(
        720,
        Math.max(1, Math.trunc(Number(configurationBackupIntervalHours))),
      ),
      configuration_backup_preferred_time: configurationBackupPreferredTime.trim() || "02:00",
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
      await queryClient.invalidateQueries({ queryKey: suiteConfigurationBackupsQueryKey });
    } catch (e) {
      setBackupErr(e instanceof Error ? e.message : "Could not save backup schedule.");
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
      a.download = fileLabel.replace(/[^\w.\-]+/g, "_").slice(0, 120);
      a.click();
      URL.revokeObjectURL(url);
      setBackupMsg("Download started.");
    } catch (e) {
      setBackupErr(e instanceof Error ? e.message : "Could not download snapshot.");
    } finally {
      setBackupBusy(false);
    }
  }

  async function handleUpgradeNow() {
    setUpgradeMsg(null);
    try {
      const result = await updateNow.mutateAsync();
      setUpgradeMsg(result.message);
      if (result.status === "started") {
        window.setTimeout(() => {
          window.location.reload();
        }, 30_000);
      }
    } catch {
      /* surfaced below */
    }
  }

  const changePasswordBusy = changePassword.isPending;
  const runtimeMetrics = metricsQ.data;
  const runtimeRequestIssues = requestIssueSummary(runtimeMetrics?.status_counts);

  return (
    <div className="mm-page" data-testid="suite-settings-page">
      <header className="mm-page__intro mm-page__intro--suite-settings-rule">
        <p className="mm-page__eyebrow">System</p>
        <h1 className="mm-page__title">Settings</h1>
        <p className="mm-page__lead">
          MediaMop-wide choices that are not part of Refiner, Pruner, or Subber. Integration details stay on their module
          pages.
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
            onClick={() => setTab("general")}
          >
            General
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={tab === "security"}
            className={tabButtonClass(tab === "security")}
            onClick={() => setTab("security")}
          >
            Security
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={tab === "logs"}
            className={tabButtonClass(tab === "logs")}
            onClick={() => setTab("logs")}
          >
            Logs
          </button>
        </div>

        {tab === "general" ? (
          <div data-testid="suite-settings-global" className="mm-bubble-stack">
            {!editable ? (
              <p className="text-sm text-[var(--mm-text3)]">
                Operators and admins can edit General options; everyone can open the Logs tab to read recent events.
              </p>
            ) : null}

            <div className="grid grid-cols-1 gap-5">
              <div className={mmModuleTabBlurbBandClass}>
                <p className={mmModuleTabBlurbTextClass}>
                  Suite-wide choices saved in the app database. Integration details for Refiner, Pruner, and Subber stay
                  on those module pages.
                </p>
              </div>
              <div className="grid grid-cols-1 gap-5 xl:grid-cols-2">
              <section className={SUITE_SETTINGS_DASH_CARD_CLASS} aria-labelledby="suite-settings-wizard-heading">
                <div className="mm-card-action-body">
                  <div>
                    <h3 id="suite-settings-wizard-heading" className="text-base font-semibold text-[var(--mm-text1)]">
                      Setup wizard
                    </h3>
                    <p className="mt-1 text-sm text-[var(--mm-text2)]">
                      Reopen the first-run wizard to adjust the basic suite setup flow at any time.
                    </p>
                  </div>
                  <div className="space-y-2 text-sm text-[var(--mm-text2)]">
                    <p>
                      Current state:{" "}
                      <span className="font-medium capitalize text-[var(--mm-text1)]">
                        {settingsQ.data.setup_wizard_state || "pending"}
                      </span>
                    </p>
                    <p>Use this when you want the guided setup again without exposing it in the sidebar.</p>
                  </div>
                </div>
                <div className="mm-card-action-footer">
                  <button
                    type="button"
                    className={mmActionButtonClass({ variant: "secondary", disabled: false })}
                    data-testid="suite-settings-open-setup-wizard"
                    onClick={() => navigate("/app/setup-wizard")}
                  >
                    Open setup wizard
                  </button>
                </div>
              </section>
              <section
                className={SUITE_SETTINGS_DASH_CARD_CLASS}
                aria-labelledby="suite-settings-timezone-heading"
              >
                <div className="mm-card-action-body">
                <div>
                  <h3 id="suite-settings-timezone-heading" className="text-base font-semibold text-[var(--mm-text1)]">
                    Timezone
                  </h3>
                  <p className="mt-1 text-sm text-[var(--mm-text2)]">
                    Main-country timezones for suite-level time displays. Use Save timezone when you change the
                    selection.
                  </p>
                </div>
                <MmListboxPicker
                  ariaLabelledBy="suite-settings-timezone-heading"
                  ariaDescribedBy="suite-timezone-hint"
                  placeholder="Select timezone"
                  disabled={!editable || save.isPending}
                  options={timezoneOptions.map((tz) => ({ value: tz.id, label: tz.label }))}
                  value={appTimezone ?? ""}
                  onChange={(v) => setAppTimezone(v)}
                />
                <p id="suite-timezone-hint" className="text-xs text-[var(--mm-text3)]">
                  If you do not see your zone, pick the closest match — this only affects how times are labeled in the
                  suite.
                </p>
                {save.isError && lastSuiteSaveTarget === "timezone" ? (
                  <p className="text-sm text-red-300" role="alert" data-testid="suite-settings-timezone-save-error">
                    {save.error instanceof Error ? save.error.message : "Could not save."}
                  </p>
                ) : null}
                </div>
                <div className="mm-card-action-footer">
                <button
                  type="button"
                  className={mmActionButtonClass({
                    variant: "primary",
                    disabled: !editable || !timezoneDirty || save.isPending,
                  })}
                  disabled={!editable || !timezoneDirty || save.isPending}
                  data-testid="suite-settings-save-timezone"
                  onClick={() => void handleSaveTimezone()}
                >
                  {save.isPending ? "Saving…" : "Save timezone"}
                </button>
                </div>
              </section>

            </div>

            <div className="grid grid-cols-1 gap-5 xl:grid-cols-2">
            <section className={SUITE_SETTINGS_DASH_CARD_CLASS} aria-labelledby="suite-settings-log-retention-heading">
              <div className="mm-card-action-body">
              <div>
                <h3 id="suite-settings-log-retention-heading" className="text-base font-semibold text-[var(--mm-text1)]">
                  Log retention
                </h3>
                <p className="mt-1 text-sm text-[var(--mm-text2)]">
                  Decide how long MediaMop keeps persisted system log entries on disk.
                </p>
              </div>
              <label className="block max-w-md">
                <span className="text-xs font-semibold uppercase tracking-wide text-[var(--mm-text3)]">
                  Log retention (days)
                </span>
                <input
                  type="number"
                  min={1}
                  max={3650}
                  className={`${mmEditableTextFieldClass} mt-1`}
                  value={normalizedLogRetentionDraft}
                  disabled={!editable || save.isPending}
                  onFocus={() => setLogRetentionDaysDraft(String(settingsQ.data.log_retention_days))}
                  onChange={(e) => setLogRetentionDaysDraft(e.target.value)}
                  onBlur={() => setLogRetentionDaysDraft(String(finalizeLogRetentionDays()))}
                  aria-describedby="suite-general-log-retention-hint"
                />
                <p id="suite-general-log-retention-hint" className="mt-1 text-xs text-[var(--mm-text3)]">
                  Between 1 and 3650 days. Older system log entries are removed automatically.
                </p>
              </label>
              {save.isError && lastSuiteSaveTarget === "logs" ? (
                <p className="text-sm text-red-300" role="alert" data-testid="suite-settings-logs-save-error">
                  {save.error instanceof Error ? save.error.message : "Could not save."}
                </p>
              ) : null}
              </div>
              <div className="mm-card-action-footer">
              <button
                type="button"
                className={mmActionButtonClass({
                  variant: "primary",
                  disabled: !editable || !logsDirty || save.isPending,
                })}
                disabled={!editable || !logsDirty || save.isPending}
                data-testid="suite-settings-save-logs"
                onClick={() => void handleSaveLogs()}
              >
                {save.isPending ? "Saving…" : "Save log retention"}
              </button>
              </div>
            </section>
            <section className={SUITE_SETTINGS_DASH_CARD_CLASS} aria-labelledby="suite-settings-density-heading">
              <fieldset className="min-w-0 border-0 p-0">
                <legend id="suite-settings-density-heading" className="text-base font-semibold text-[var(--mm-text1)]">
                  Display density (this browser)
                </legend>
                <p className="mt-1 text-sm text-[var(--mm-text2)]">
                  Adjust type size and how wide the main column can grow on large monitors. Your choice saves in this
                  browser only and applies as soon as you select it. Choose Default to clear the stored preference.
                </p>
                <div
                  className="mt-3 flex flex-col gap-2"
                  data-testid="suite-settings-display-density"
                  role="radiogroup"
                  aria-label="Display density"
                >
                  {(
                    [
                      { id: "default" as const, label: "Default", hint: "Balanced" },
                      { id: "compact" as const, label: "Compact", hint: "Smaller text, narrower cap" },
                      { id: "comfortable" as const, label: "Comfortable", hint: "Larger text (+10%), wider cap" },
                    ] as const
                  ).map(({ id, label, hint }) => (
                    <label
                      key={id}
                      className={[
                        "flex min-w-0 cursor-pointer items-center gap-2.5 rounded-md border px-3 py-2 text-sm transition-colors",
                        displayDensity === id
                          ? "border-[var(--mm-accent)] bg-[var(--mm-accent)]/12 text-[var(--mm-text)]"
                          : "border-[var(--mm-border)] bg-transparent text-[var(--mm-text2)] hover:bg-[var(--mm-card-bg)]",
                      ].join(" ")}
                    >
                      <input
                        type="radio"
                        name="mm-display-density"
                        className="h-4 w-4 shrink-0 accent-[var(--mm-accent)]"
                        checked={displayDensity === id}
                        onChange={() => {
                          setDisplayDensity(id);
                          persistDisplayDensity(id);
                        }}
                      />
                      <span className="min-w-0 font-medium">{label}</span>
                      <span className="text-xs text-[var(--mm-text3)]">({hint})</span>
                    </label>
                  ))}
                </div>
              </fieldset>
            </section>
            </div>

            <div className={`grid grid-cols-1 gap-5 ${editable ? "xl:grid-cols-2" : ""}`}>
            {editable ? (
              <section
                className={SUITE_SETTINGS_DASH_CARD_CLASS}
                data-testid="suite-settings-backup-restore"
                aria-labelledby="suite-settings-backup-heading"
              >
                <div>
                  <h3 id="suite-settings-backup-heading" className="text-base font-semibold text-[var(--mm-text1)]">
                    Backup and restore
                  </h3>
                  <p className="mt-1 text-sm text-[var(--mm-text2)]">
                    Keep a clean copy of MediaMop settings and restore them if something goes wrong.
                  </p>
                </div>

                <div className="grid gap-5 lg:grid-cols-2">
                  <div className={SUITE_SETTINGS_PREMIUM_PANEL_CLASS}>
                    <div>
                      <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--mm-gold)]">
                        Automatic protection
                      </p>
                      <h4 className="mt-1 text-sm font-semibold text-[var(--mm-text1)]">Scheduled snapshots</h4>
                      <p className="mt-1 text-xs leading-relaxed text-[var(--mm-text3)]">
                        MediaMop keeps the latest five configuration snapshots using the same restore-safe JSON format.
                      </p>
                    </div>
                    <label className="flex cursor-pointer items-start gap-2.5 text-sm text-[var(--mm-text2)]">
                      <input
                        type="checkbox"
                        className="mt-0.5 h-4 w-4 shrink-0 accent-[var(--mm-accent)]"
                        checked={configurationBackupEnabled}
                        disabled={!editable || save.isPending}
                        onChange={(e) => setConfigurationBackupEnabled(e.target.checked)}
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
                        onChange={(e) => setConfigurationBackupIntervalHours(Number(e.target.value))}
                      >
                        {CONFIGURATION_BACKUP_INTERVAL_HOURS.map((h) => (
                          <option key={h} value={h}>
                            {h === 168 ? "Every 7 days (168 h)" : `Every ${h} hours`}
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
                        onChange={(e) => setConfigurationBackupPreferredTime(e.target.value || "02:00")}
                      />
                    </label>
                    <p className="text-xs text-[var(--mm-text3)]">
                      <span className="font-medium text-[var(--mm-text2)]">Last automatic run:</span>{" "}
                      {settingsQ.data.configuration_backup_last_run_at
                        ? new Date(settingsQ.data.configuration_backup_last_run_at).toLocaleString()
                        : "—"}
                    </p>
                    <p className="text-xs text-[var(--mm-text3)]">
                      <span className="font-medium text-[var(--mm-text2)]">Target time:</span> {configurationBackupPreferredTime}
                    </p>
                    <div className="mt-auto flex flex-col gap-2 border-t border-[var(--mm-border)] pt-3">
                      <button
                        type="button"
                        className={mmActionButtonClass({
                          variant: "secondary",
                          disabled: !editable || !backupScheduleDirty || save.isPending,
                        })}
                        disabled={!editable || !backupScheduleDirty || save.isPending}
                        onClick={() => void handleSaveBackupSchedule()}
                      >
                        {save.isPending ? "Saving…" : "Save backup schedule"}
                      </button>
                      {save.isError && lastSuiteSaveTarget === "backup" ? (
                        <p
                          className="rounded-md border border-red-500/40 bg-red-950/25 px-3 py-2 text-sm text-red-200"
                          role="alert"
                          data-testid="suite-settings-backup-save-error"
                        >
                          {save.error instanceof Error ? save.error.message : "Could not save."}
                        </p>
                      ) : null}
                    </div>
                  </div>

                  <div className={SUITE_SETTINGS_PREMIUM_PANEL_CLASS}>
                    <div>
                      <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--mm-gold)]">
                        Manual control
                      </p>
                      <h4 className="mt-1 text-sm font-semibold text-[var(--mm-text1)]">Export or restore now</h4>
                      <p className="mt-1 text-xs leading-relaxed text-[var(--mm-text3)]">
                        Download a full settings file, or restore a MediaMop configuration JSON from disk.
                      </p>
                    </div>
                    <div className="mt-auto flex flex-col gap-2 border-t border-[var(--mm-border)] pt-3">
                      <button
                        type="button"
                        className={mmActionButtonClass({ variant: "secondary", disabled: backupBusy || save.isPending })}
                        disabled={backupBusy || save.isPending}
                        onClick={() => void handleDownloadConfiguration()}
                      >
                        Download configuration now
                      </button>
                      <button
                        type="button"
                        className={mmActionButtonClass({ variant: "tertiary", disabled: backupBusy || save.isPending })}
                        disabled={backupBusy || save.isPending}
                        onClick={() => restoreInputRef.current?.click()}
                      >
                        Restore from file…
                      </button>
                      <input
                        ref={restoreInputRef}
                        type="file"
                        accept="application/json,.json"
                        className="hidden"
                        aria-label="Choose configuration JSON file to restore"
                        onChange={(e) => void handleRestoreFileChange(e)}
                      />
                    </div>
                  </div>
                </div>

                <div className={SUITE_SETTINGS_PREMIUM_PANEL_CLASS}>
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--mm-gold)]">
                        Snapshot history
                      </p>
                      <h4 className="mt-1 text-sm font-semibold text-[var(--mm-text1)]">Recent automatic snapshots</h4>
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
                      <p className="text-sm text-[var(--mm-text3)]">Loading snapshot list…</p>
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
                              <div className="text-xs text-[var(--mm-text3)]">{formatBackupBytes(row.size_bytes)}</div>
                            </div>
                            <button
                              type="button"
                              className={mmActionButtonClass({
                                variant: "tertiary",
                                disabled: backupBusy || save.isPending,
                              })}
                              disabled={backupBusy || save.isPending}
                              onClick={() => void handleDownloadStoredBackup(row.id, row.file_name)}
                            >
                              Download snapshot
                            </button>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                </div>

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
              </section>
            ) : null}

            <section
              className={SUITE_SETTINGS_DASH_CARD_CLASS}
              data-testid="suite-settings-upgrade"
              aria-labelledby="suite-settings-upgrade-heading"
            >
              <div>
                <h3 id="suite-settings-upgrade-heading" className="text-base font-semibold text-[var(--mm-text1)]">
                  Upgrade
                </h3>
                <p className="mt-1 text-sm text-[var(--mm-text2)]">
                  Check the running MediaMop version and install the latest release for this install type.
                </p>
              </div>

              {updateStatusQ.isPending ? (
                <p className="text-sm text-[var(--mm-text3)]">Checking for updates…</p>
              ) : updateStatusQ.isError || !updateStatusQ.data ? (
                <p className="rounded-md border border-red-500/40 bg-red-950/25 px-3 py-2 text-sm text-red-200" role="alert">
                  {updateStatusQ.error instanceof Error
                    ? updateStatusQ.error.message
                    : "Could not check for updates right now."}
                </p>
              ) : (
                <>
                  <div
                    className={`rounded-xl border p-4 ${
                      updateStatusQ.data.status === "update_available"
                        ? "border-amber-400/25 bg-amber-400/[0.06]"
                        : "border-emerald-500/20 bg-emerald-500/[0.05]"
                    }`}
                  >
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--mm-gold)]">
                          Release status
                        </p>
                        <h4 className="mt-1 text-base font-semibold text-[var(--mm-text1)]">
                          {updateStatusQ.data.summary}
                        </h4>
                      </div>
                      <span className="rounded-full border border-[var(--mm-border)] bg-[var(--mm-card-bg)] px-2.5 py-1 text-xs font-medium capitalize text-[var(--mm-text2)]">
                        {updateStatusQ.data.status.replaceAll("_", " ")}
                      </span>
                    </div>
                  </div>

                  <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                    <div className={SUITE_SETTINGS_PREMIUM_TILE_CLASS}>
                      <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--mm-text3)]">Installed</div>
                      <div className="mt-1 text-base font-semibold text-[var(--mm-text1)]">
                        {updateStatusQ.data.current_version}
                      </div>
                    </div>
                    <div className={SUITE_SETTINGS_PREMIUM_TILE_CLASS}>
                      <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--mm-text3)]">Latest</div>
                      <div className="mt-1 text-base font-semibold text-[var(--mm-text1)]">
                        {updateStatusQ.data.latest_version || "Unknown"}
                      </div>
                    </div>
                    <div className={SUITE_SETTINGS_PREMIUM_TILE_CLASS}>
                      <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--mm-text3)]">Install type</div>
                      <div className="mt-1 text-base font-semibold capitalize text-[var(--mm-text1)]">
                        {updateStatusQ.data.install_type}
                      </div>
                    </div>
                    <div className={SUITE_SETTINGS_PREMIUM_TILE_CLASS}>
                      <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--mm-text3)]">Status</div>
                      <div className="mt-1 text-base font-semibold capitalize text-[var(--mm-text1)]">
                        {updateStatusQ.data.status.replaceAll("_", " ")}
                      </div>
                    </div>
                  </div>

                  <div className={SUITE_SETTINGS_PREMIUM_PANEL_CLASS}>
                    <h4 className="text-sm font-semibold text-[var(--mm-text1)]">What happens next</h4>
                    {updateStatusQ.data.install_type === "windows" && updateStatusQ.data.status === "update_available" ? (
                      <p className="text-sm leading-6 text-[var(--mm-text2)]">
                        Upgrade now downloads the installer, closes MediaMop, installs the update, reopens the app, and
                        refreshes this page after the server comes back.
                      </p>
                    ) : updateStatusQ.data.install_type === "windows" ? (
                      <p className="text-sm leading-6 text-[var(--mm-text2)]">
                        This Windows install does not need an update right now.
                      </p>
                    ) : null}
                    {updateStatusQ.data.install_type === "docker" && updateStatusQ.data.docker_update_command ? (
                      <p className="rounded-lg border border-[var(--mm-border)] bg-[var(--mm-card-bg)] px-3 py-2 font-mono text-xs text-[var(--mm-text3)]">
                        {updateStatusQ.data.docker_update_command}
                      </p>
                    ) : null}
                  </div>

                  <div className="mt-auto flex flex-wrap gap-2 border-t border-[var(--mm-border)] pt-4">
                    <button
                      type="button"
                      className={mmActionButtonClass({ variant: "secondary", disabled: updateStatusQ.isFetching })}
                      disabled={updateStatusQ.isFetching}
                      onClick={() => void updateStatusQ.refetch()}
                    >
                      {updateStatusQ.isFetching ? "Checking…" : "Check again"}
                    </button>
                    {updateStatusQ.data.install_type === "windows" &&
                    updateStatusQ.data.status === "update_available" &&
                    updateStatusQ.data.windows_installer_url ? (
                      <button
                        type="button"
                        className={mmActionButtonClass({ variant: "primary", disabled: updateNow.isPending })}
                        disabled={updateNow.isPending}
                        onClick={() => void handleUpgradeNow()}
                      >
                        {updateNow.isPending ? "Starting upgrade…" : "Upgrade now"}
                      </button>
                    ) : null}
                    {updateStatusQ.data.windows_installer_url ? (
                      <a
                        className={mmActionButtonClass({ variant: "tertiary", disabled: false })}
                        href={updateStatusQ.data.windows_installer_url}
                        target="_blank"
                        rel="noreferrer"
                      >
                        Download installer
                      </a>
                    ) : null}
                    {updateStatusQ.data.release_url ? (
                      <a
                        className={mmActionButtonClass({ variant: "tertiary", disabled: false })}
                        href={updateStatusQ.data.release_url}
                        target="_blank"
                        rel="noreferrer"
                      >
                        Release notes
                      </a>
                    ) : null}
                  </div>
                  {upgradeMsg ? (
                    <p className="rounded-md border border-emerald-500/30 bg-emerald-950/20 px-3 py-2 text-sm text-emerald-200">
                      {upgradeMsg}
                    </p>
                  ) : null}
                  {updateNow.isError ? (
                    <p className="rounded-md border border-red-500/40 bg-red-950/25 px-3 py-2 text-sm text-red-200" role="alert">
                      {updateNow.error instanceof Error ? updateNow.error.message : "Could not start the upgrade."}
                    </p>
                  ) : null}
                </>
              )}
            </section>
            </div>
          </div>
          </div>
        ) : tab === "security" ? (
          <div className="mm-bubble-stack w-full" data-testid="suite-settings-security">
            <div className={mmModuleTabBlurbBandClass}>
              <p className={mmModuleTabBlurbTextClass}>
                Change your MediaMop password here. Sign-in cookie, HTTPS, and rate-limit settings follow the server
                configuration at startup — they are not edited in this UI.
              </p>
            </div>
            <section className="mm-card w-full" aria-labelledby="suite-security-change-password-heading">
              <h2 id="suite-security-change-password-heading" className="mm-card__title">
                Change password
              </h2>
              <p className="mm-card__body text-sm text-[var(--mm-text2)]">
                Update your sign-in password. After saving, MediaMop requires a fresh sign-in.
              </p>
              <div className="mm-card__body space-y-3">
                <label className="block">
                  <span className="text-xs font-semibold uppercase tracking-wide text-[var(--mm-text3)]">Current password</span>
                  <div className="mt-1 flex flex-wrap gap-2">
                    <input
                      type={showCurrentPassword ? "text" : "password"}
                      className={SUITE_PASSWORD_FIELD_CLASS}
                      placeholder="Enter current password"
                      value={currentPassword}
                      disabled={changePasswordBusy}
                      onChange={(e) => {
                        const v = e.target.value;
                        setCurrentPassword(v);
                        if (v.trim() === "") {
                          setShowCurrentPassword(false);
                        }
                      }}
                      autoComplete="current-password"
                    />
                    <button
                      type="button"
                      className={mmActionButtonClass({ variant: "tertiary", disabled: changePasswordBusy })}
                      disabled={changePasswordBusy}
                      onClick={() => setShowCurrentPassword((prev) => !prev)}
                    >
                      {showCurrentPassword ? "Hide" : "Show"}
                    </button>
                  </div>
                </label>
                <label className="block">
                  <span className="text-xs font-semibold uppercase tracking-wide text-[var(--mm-text3)]">New password</span>
                  <div className="mt-1 flex flex-wrap gap-2">
                    <input
                      type={showNewPassword ? "text" : "password"}
                      className={SUITE_PASSWORD_FIELD_CLASS}
                      placeholder="Enter new password"
                      value={newPassword}
                      disabled={changePasswordBusy}
                      onChange={(e) => {
                        const v = e.target.value;
                        setNewPassword(v);
                        if (v.trim() === "") {
                          setShowNewPassword(false);
                        }
                      }}
                      autoComplete="new-password"
                    />
                    <button
                      type="button"
                      className={mmActionButtonClass({ variant: "tertiary", disabled: changePasswordBusy })}
                      disabled={changePasswordBusy}
                      onClick={() => setShowNewPassword((prev) => !prev)}
                    >
                      {showNewPassword ? "Hide" : "Show"}
                    </button>
                  </div>
                </label>
                <label className="block">
                  <span className="text-xs font-semibold uppercase tracking-wide text-[var(--mm-text3)]">
                    Confirm new password
                  </span>
                  <div className="mt-1 flex flex-wrap gap-2">
                    <input
                      type={showConfirmPassword ? "text" : "password"}
                      className={SUITE_PASSWORD_FIELD_CLASS}
                      placeholder="Re-enter new password"
                      value={confirmPassword}
                      disabled={changePasswordBusy}
                      onChange={(e) => {
                        const v = e.target.value;
                        setConfirmPassword(v);
                        if (v.trim() === "") {
                          setShowConfirmPassword(false);
                        }
                      }}
                      autoComplete="new-password"
                    />
                    <button
                      type="button"
                      className={mmActionButtonClass({ variant: "tertiary", disabled: changePasswordBusy })}
                      disabled={changePasswordBusy}
                      onClick={() => setShowConfirmPassword((prev) => !prev)}
                    >
                      {showConfirmPassword ? "Hide" : "Show"}
                    </button>
                  </div>
                </label>
                {changePassword.isError ? (
                  <p className="text-sm text-red-300" role="alert">
                    {formatChangePasswordMutationError(changePassword.error)}
                  </p>
                ) : null}
                {changePasswordStatus ? (
                  <p className="text-sm text-[var(--mm-text2)]" role="status">
                    {typeof changePasswordStatus === "string"
                      ? changePasswordStatus
                      : "Password change finished."}
                  </p>
                ) : null}
                <button
                  type="button"
                  className={mmActionButtonClass({
                    variant: "primary",
                    disabled:
                      changePasswordBusy ||
                      currentPassword.trim() === "" ||
                      newPassword.trim() === "" ||
                      confirmPassword.trim() === "",
                  })}
                  disabled={
                    changePasswordBusy ||
                    currentPassword.trim() === "" ||
                    newPassword.trim() === "" ||
                    confirmPassword.trim() === ""
                  }
                  onClick={async () => {
                    setChangePasswordStatus(null);
                    if (newPassword !== confirmPassword) {
                      setChangePasswordStatus("New passwords do not match.");
                      return;
                    }
                    try {
                      await changePassword.mutateAsync({
                        currentPassword,
                        newPassword,
                      });
                      setCurrentPassword("");
                      setNewPassword("");
                      setConfirmPassword("");
                      setShowCurrentPassword(false);
                      setShowNewPassword(false);
                      setShowConfirmPassword(false);
                      setChangePasswordStatus("Password changed. Sign in again with your new password.");
                      navigate("/login", { replace: true });
                    } catch {
                      setShowCurrentPassword(false);
                      setShowNewPassword(false);
                      setShowConfirmPassword(false);
                      /* surfaced above */
                    }
                  }}
                >
                  {changePassword.isPending ? "Saving…" : "Change password"}
                </button>
              </div>
            </section>
          </div>
        ) : (
          <div data-testid="suite-settings-logs" className="mm-bubble-stack w-full">
            <div className={mmModuleTabBlurbBandClass}>
              <p className={mmModuleTabBlurbTextClass}>
                System event logs from the MediaMop runtime. Use filters to narrow down warnings, failures, and
                tracebacks. Advanced server diagnostics are available here when troubleshooting.
              </p>
            </div>

            <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5" aria-label="Log summary">
              <SettingsSummaryCard label="Showing now" value={`${logsQ.data?.items.length ?? 0} events`} />
              <SettingsSummaryCard label="Matching events" value={`${logsQ.data?.total ?? 0} events`} />
              <SettingsSummaryCard label="Errors" value={String(logsQ.data?.counts.error ?? 0)} />
              <SettingsSummaryCard label="Warnings" value={String(logsQ.data?.counts.warning ?? 0)} />
              <SettingsSummaryCard label="Information" value={String(logsQ.data?.counts.information ?? 0)} />
            </section>

            <section className="mm-card mm-dash-card w-full" aria-labelledby="suite-settings-diagnostics-heading">
              <details>
                <summary
                  id="suite-settings-diagnostics-heading"
                  className="cursor-pointer text-base font-semibold text-[var(--mm-text1)]"
                >
                  Server diagnostics
                </summary>
                <p className="mt-2 text-sm text-[var(--mm-text2)]">
                  Advanced counters for troubleshooting. Request issues usually mean a browser or API request was rejected
                  or asked for something that was not found; they are not the same as application failures.
                </p>
                {metricsQ.isError ? (
                  <p className="mt-4 rounded-md border border-red-500/40 bg-red-950/25 px-3 py-2 text-sm text-red-200" role="alert">
                    {metricsQ.error instanceof Error ? metricsQ.error.message : "Could not load server diagnostics."}
                  </p>
                ) : (
                  <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-5">
                    <SettingsSummaryCard
                      label="Running for"
                      value={runtimeMetrics ? formatRuntimeUptime(runtimeMetrics.uptime_seconds) : "Loading..."}
                    />
                    <SettingsSummaryCard
                      label="Requests handled"
                      value={runtimeMetrics ? String(runtimeMetrics.total_requests) : "Loading..."}
                    />
                    <SettingsSummaryCard
                      label="Average response"
                      value={runtimeMetrics ? formatAverageMs(runtimeMetrics.average_response_ms) : "Loading..."}
                    />
                    <SettingsSummaryCard
                      label="Logged failures"
                      value={runtimeMetrics ? String(runtimeMetrics.error_log_count) : "Loading..."}
                    />
                    <SettingsSummaryCard
                      label="Request issues"
                      value={runtimeMetrics ? runtimeRequestIssues.value : "Loading..."}
                    />
                  </div>
                )}
                {runtimeMetrics ? (
                  <p className="mt-3 text-xs text-[var(--mm-text3)]">{runtimeRequestIssues.detail}</p>
                ) : null}
              </details>
            </section>

            <section className="mm-card mm-dash-card w-full" aria-labelledby="suite-settings-logs-filters-heading">
              <div className="mm-card__body space-y-4">
                <div>
                  <h3 id="suite-settings-logs-filters-heading" className="text-base font-semibold text-[var(--mm-text1)]">
                    Search logs
                  </h3>
                  <p className="mt-1 text-sm text-[var(--mm-text2)]">
                    Search message text, component names, tracebacks, request IDs, and job IDs. This view refreshes while
                    it is open.
                  </p>
                </div>

                <div className="grid gap-3 lg:grid-cols-[minmax(0,2fr)_220px_auto_auto]">
                  <label className="flex flex-col gap-1 text-xs font-semibold uppercase tracking-wide text-[var(--mm-text3)]">
                    Search
                    <input
                      type="text"
                      className={mmEditableTextFieldClass}
                      placeholder="Search message, detail, traceback, logger, or source"
                      value={logSearch}
                      onChange={(e) => setLogSearch(e.target.value)}
                    />
                  </label>
                  <label className="flex flex-col gap-1 text-xs font-semibold uppercase tracking-wide text-[var(--mm-text3)]">
                    Level
                    <select
                      className={mmEditableTextFieldClass}
                      value={logLevel}
                      onChange={(e) => setLogLevel(e.target.value as LogLevelFilter)}
                    >
                      <option value="">All levels</option>
                      <option value="INFO">Information</option>
                      <option value="WARNING">Warnings</option>
                      <option value="ERROR">Errors</option>
                    </select>
                  </label>
                  <div className="flex flex-col gap-1 text-xs font-semibold uppercase tracking-wide text-[var(--mm-text3)]">
                    <span>Tracebacks only</span>
                    <div className="flex gap-2">
                      <button
                        type="button"
                        className={mmActionButtonClass({ variant: tracebacksOnly ? "primary" : "tertiary" })}
                        onClick={() => setTracebacksOnly(true)}
                      >
                        On
                      </button>
                      <button
                        type="button"
                        className={mmActionButtonClass({ variant: !tracebacksOnly ? "primary" : "tertiary" })}
                        onClick={() => setTracebacksOnly(false)}
                      >
                        Off
                      </button>
                    </div>
                  </div>
                  <div className="flex flex-wrap items-end gap-2">
                    <button
                      type="button"
                      className={mmActionButtonClass({ variant: "secondary", disabled: logsQ.isFetching })}
                      disabled={logsQ.isFetching}
                      onClick={() => void logsQ.refetch()}
                    >
                      {logsQ.isFetching ? "Refreshing..." : "Refresh"}
                    </button>
                    <button
                      type="button"
                      className={mmActionButtonClass({
                        variant: "tertiary",
                        disabled: !logSearch.trim() && !logLevel && !tracebacksOnly,
                      })}
                      disabled={!logSearch.trim() && !logLevel && !tracebacksOnly}
                      onClick={() => {
                        setLogSearch("");
                        setLogLevel("");
                        setTracebacksOnly(false);
                      }}
                    >
                      Clear filters
                    </button>
                  </div>
                </div>

                {logSearch.trim() || logLevel || tracebacksOnly ? (
                  <div className="flex flex-wrap gap-2">
                    {logSearch.trim() ? (
                      <span className="rounded-full border border-[var(--mm-border)] bg-black/10 px-2.5 py-1 text-xs text-[var(--mm-text2)]">
                        Search: {logSearch.trim()}
                      </span>
                    ) : null}
                    {logLevel ? (
                      <span className="rounded-full border border-[var(--mm-border)] bg-black/10 px-2.5 py-1 text-xs text-[var(--mm-text2)]">
                        Level: {logLevel === "INFO" ? "Information" : logLevel}
                      </span>
                    ) : null}
                    {tracebacksOnly ? (
                      <span className="rounded-full border border-[var(--mm-border)] bg-black/10 px-2.5 py-1 text-xs text-[var(--mm-text2)]">
                        Tracebacks only
                      </span>
                    ) : null}
                  </div>
                ) : null}
              </div>
            </section>

            <section className="mm-card mm-dash-card w-full" aria-labelledby="suite-settings-logs-list-heading">
              <div className="mm-card__body space-y-4">
                <div>
                  <h3 id="suite-settings-logs-list-heading" className="text-base font-semibold text-[var(--mm-text1)]">
                    System events
                  </h3>
                  <p className="mt-1 text-sm text-[var(--mm-text2)]">
                    Recent runtime events, warnings, and failures captured by MediaMop.
                  </p>
                </div>

                {logsQ.isPending ? (
                  <div className="rounded-lg border border-[var(--mm-border)] bg-black/10 px-4 py-4 text-sm text-[var(--mm-text3)]">
                    Loading logs...
                  </div>
                ) : logsQ.isError ? (
                  <div className="rounded-lg border border-red-500/40 bg-red-950/25 px-4 py-4 text-sm text-red-200" role="alert">
                    {logsQ.error instanceof Error ? logsQ.error.message : "Could not load logs."}
                  </div>
                ) : (logsQ.data?.items.length ?? 0) === 0 ? (
                  <div className="rounded-lg border border-[var(--mm-border)] bg-black/10 px-4 py-4 text-sm text-[var(--mm-text2)]">
                    No system events matched the current filters.
                  </div>
                ) : (
                  <div className="space-y-3">
                    {logsQ.data?.items.map((entry) => {
                      const technicalDetails = renderLogTechnicalDetails(entry);
                      return (
                        <article
                          key={`${entry.timestamp}-${entry.level}-${entry.message}`}
                          className={`rounded-lg border px-4 py-4 ${logCardTone(entry.level)}`}
                        >
                          <div className="flex flex-wrap items-start justify-between gap-3">
                            <div className="space-y-2">
                              <div className="flex flex-wrap items-center gap-2">
                                <span className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--mm-gold)]">
                                  {entry.component}
                                </span>
                                <span
                                  className={`rounded-full border px-2.5 py-1 text-xs font-medium ${logLevelBadgeTone(entry.level)}`}
                                >
                                  {entry.level === "INFO" ? "Information" : entry.level}
                                </span>
                              </div>
                              <h4 className="text-sm font-semibold text-[var(--mm-text1)]">{entry.message}</h4>
                              {entry.detail ? <p className="text-sm leading-6 text-[var(--mm-text2)]">{entry.detail}</p> : null}
                            </div>
                            <time className="text-sm text-[var(--mm-text3)]">{formatDateTime(entry.timestamp)}</time>
                          </div>
                          {technicalDetails ? <div className="mt-3">{technicalDetails}</div> : null}
                        </article>
                      );
                    })}
                  </div>
                )}
              </div>
            </section>
          </div>
        )}
      </div>
    </div>
  );
}


