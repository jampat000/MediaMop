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
  activityRecentSettingsKey,
  useActivityRecentForSettingsQuery,
} from "../../lib/activity/queries";
import { useSuiteSettingsQuery, useSuiteSettingsSaveMutation } from "../../lib/suite/queries";
import type { SuiteSettingsPutBody } from "../../lib/suite/types";
import {
  fetchConfigurationBundle,
  putConfigurationBundle,
  type ConfigurationBundle,
} from "../../lib/suite/suite-settings-api";
import {
  persistDisplayDensity,
  readStoredDisplayDensity,
  type DisplayDensity,
} from "../../lib/ui/display-density";

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

/** Settings: General (timezone, display density, configuration export), Security, Logs (retention + recent events). */
export function SettingsPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const me = useMeQuery();
  const changePassword = useChangePasswordMutation();
  const settingsQ = useSuiteSettingsQuery();
  const save = useSuiteSettingsSaveMutation();

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
  const [lastSuiteSaveTarget, setLastSuiteSaveTarget] = useState<"timezone" | "logs" | null>(null);
  const restoreInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!settingsQ.data) {
      return;
    }
    const fromServer = settingsQ.data.app_timezone || "";
    setAppTimezone(CURATED_TIMEZONE_ID_SET.has(fromServer) ? fromServer : null);
    setLogRetentionDaysDraft(null);
  }, [settingsQ.data]);

  const editable = canEditSuiteGlobal(me.data?.role);

  const serverCuratedTimezone =
    settingsQ.data && CURATED_TIMEZONE_ID_SET.has(settingsQ.data.app_timezone || "") ? settingsQ.data.app_timezone : null;

  const activityRecentQ = useActivityRecentForSettingsQuery(tab === "logs" && Boolean(settingsQ.data));

  const timezoneDirty = settingsQ.data !== undefined && appTimezone !== serverCuratedTimezone;

  const logsDirty =
    settingsQ.data !== undefined &&
    logRetentionDaysDraft !== null &&
    logRetentionDaysDraft !== String(settingsQ.data.log_retention_days);

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
      await queryClient.invalidateQueries({ queryKey: activityRecentSettingsKey });
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
      app_timezone: tz,
      log_retention_days: Number.isFinite(retention) ? retention : d.log_retention_days,
      application_logs_enabled: true,
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
      await queryClient.invalidateQueries({ queryKey: activityRecentSettingsKey });
      await activityRecentQ.refetch();
    } catch {
      /* surfaced via save.isError */
    }
  }

  const changePasswordBusy = changePassword.isPending;

  return (
    <div className="mm-page" data-testid="suite-settings-page">
      <header className="mm-page__intro mm-page__intro--suite-settings-rule">
        <p className="mm-page__eyebrow">System</p>
        <h1 className="mm-page__title">Settings</h1>
        <p className="mm-page__lead">
          MediaMop-wide choices that are not part of Fetcher, Refiner, Pruner, or Subber. Integration details stay on
          their module pages.
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
          <div data-testid="suite-settings-global" className="space-y-5">
            {!editable ? (
              <p className="text-sm text-[var(--mm-text3)]">
                Operators and admins can edit General options; everyone can open the Logs tab to read recent events.
              </p>
            ) : null}

            <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
              <div className={`${mmModuleTabBlurbBandClass} lg:col-span-2`}>
                <p className={mmModuleTabBlurbTextClass}>
                  Suite-wide choices saved in the app database. Integration details for Fetcher, Refiner, Pruner,
                  Subber, and Broker stay on those module pages.
                </p>
              </div>
              <section
                className={SUITE_SETTINGS_DASH_CARD_CLASS}
                aria-labelledby="suite-settings-timezone-heading"
              >
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

            {editable ? (
              <section
                className={SUITE_SETTINGS_DASH_CARD_CLASS}
                data-testid="suite-settings-configuration-export"
                aria-labelledby="suite-settings-configuration-heading"
              >
                <div>
                  <h3 id="suite-settings-configuration-heading" className="text-base font-semibold text-[var(--mm-text1)]">
                    Configuration export and restore
                  </h3>
                  <p className="mt-1 text-sm text-[var(--mm-text2)]">
                    Download or upload the full suite configuration (Fetcher, Refiner, Pruner, Subber, Broker, and
                    suite-level settings) as one JSON file. Treat exports as sensitive — they can include API keys and
                    tokens. Restoring replaces matching stored settings for this install, including the Pruner instance
                    list and per-library rules.
                  </p>
                </div>

                <div className="flex flex-col gap-4 rounded-lg border border-[var(--mm-border)] bg-[var(--mm-card-bg)]/50 p-4 shadow-sm">
                  <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center">
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
                  <p className="text-xs text-[var(--mm-text3)]">
                    You will be asked to confirm before a restore runs. Keep copies of exports wherever you already store
                    backups for this host.
                  </p>
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
          </div>
        ) : tab === "security" ? (
          <div className="w-full space-y-5" data-testid="suite-settings-security">
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
          <div data-testid="suite-settings-logs" className="w-full space-y-5">
            <div className={mmModuleTabBlurbBandClass}>
              <p className={mmModuleTabBlurbTextClass}>
                Timeline events stored in the database and how long they are kept. Open the Activity views on module
                pages for deeper history.
              </p>
            </div>

            <section
              className={`${SUITE_SETTINGS_DASH_CARD_CLASS} w-full max-w-none`}
              aria-labelledby="suite-settings-logs-heading"
            >
              <div>
                <h3 id="suite-settings-logs-heading" className="text-base font-semibold text-[var(--mm-text1)]">
                  Logs
                </h3>
                <p className="mt-1 text-sm text-[var(--mm-text2)]">
                  Control how long Activity rows are kept. Use Save logs settings when you change retention.
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
                  aria-describedby="suite-log-retention-hint"
                />
                <p id="suite-log-retention-hint" className="mt-1 text-xs text-[var(--mm-text3)]">
                  Between 1 and 3650 days. Older rows are removed automatically.
                </p>
              </label>

              {save.isError && lastSuiteSaveTarget === "logs" ? (
                <p className="text-sm text-red-300" role="alert" data-testid="suite-settings-logs-save-error">
                  {save.error instanceof Error ? save.error.message : "Could not save."}
                </p>
              ) : null}

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
                {save.isPending ? "Saving…" : "Save logs settings"}
              </button>

              <div className="border-t border-[var(--mm-border)] pt-5">
                <h4 className="text-sm font-semibold text-[var(--mm-text1)]">Most recent events (20)</h4>
                <p className="mt-1 text-xs text-[var(--mm-text3)]">Newest first — same data as the Activity feed API.</p>
                <div className="mt-3 max-h-[28rem] overflow-auto rounded-md border border-[var(--mm-border)]">
                  {activityRecentQ.isPending ? (
                    <p className="p-4 text-sm text-[var(--mm-text3)]">Loading…</p>
                  ) : activityRecentQ.isError ? (
                    <p className="p-4 text-sm text-red-400" role="alert">
                      {(activityRecentQ.error as Error).message}
                    </p>
                  ) : (activityRecentQ.data?.items.length ?? 0) === 0 ? (
                    <p className="p-4 text-sm text-[var(--mm-text3)]">No events recorded yet.</p>
                  ) : (
                    <table className="w-full min-w-[40rem] border-collapse text-left text-sm">
                      <thead className="sticky top-0 z-[1] bg-[var(--mm-card-bg)]">
                        <tr className="border-b border-[var(--mm-border)] text-xs uppercase tracking-wide text-[var(--mm-text3)]">
                          <th className="px-3 py-2 font-medium">When</th>
                          <th className="px-3 py-2 font-medium">Module</th>
                          <th className="px-3 py-2 font-medium">Title</th>
                          <th className="px-3 py-2 font-medium">Detail</th>
                        </tr>
                      </thead>
                      <tbody>
                        {activityRecentQ.data!.items.map((ev) => (
                          <tr key={ev.id} className="border-b border-[var(--mm-border)]/70">
                            <td className="whitespace-nowrap px-3 py-2 text-[var(--mm-text2)]">
                              {new Date(ev.created_at).toLocaleString()}
                            </td>
                            <td className="px-3 py-2 font-mono text-xs text-[var(--mm-text3)]">{ev.module}</td>
                            <td className="px-3 py-2 text-[var(--mm-text)]">{ev.title}</td>
                            <td className="max-w-md truncate px-3 py-2 text-xs text-[var(--mm-text2)]">
                              {ev.detail ?? "—"}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
              </div>
            </section>
          </div>
        )}
      </div>
    </div>
  );
}

