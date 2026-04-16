import { useEffect, useId, useState } from "react";
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
import {
  useSuiteSettingsQuery,
  useSuiteSettingsSaveMutation,
} from "../../lib/suite/queries";

function canEditSuiteGlobal(role: string | undefined): boolean {
  return role === "operator" || role === "admin";
}

type TabId = "global" | "security";

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
    "rounded-md border px-3 py-1.5 text-sm font-medium transition-colors",
    active
      ? "border-[var(--mm-accent)] bg-[var(--mm-accent)]/15 text-[var(--mm-text)]"
      : "border-[var(--mm-border)] bg-transparent text-[var(--mm-text2)] hover:bg-[var(--mm-card-bg)]",
  ].join(" ");
}

/** Central suite settings: Global (saved in-app) and Security (read-only startup snapshot). */
export function SettingsPage() {
  const navigate = useNavigate();
  const me = useMeQuery();
  const changePassword = useChangePasswordMutation();
  const settingsQ = useSuiteSettingsQuery();
  const save = useSuiteSettingsSaveMutation();

  const [tab, setTab] = useState<TabId>("global");
  const [appTimezone, setAppTimezone] = useState<string | null>(null);
  const [logRetentionDaysDraft, setLogRetentionDaysDraft] = useState<string | null>(null);
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showCurrentPassword, setShowCurrentPassword] = useState(false);
  const [showNewPassword, setShowNewPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [changePasswordStatus, setChangePasswordStatus] = useState<string | null>(null);
  const timezoneLabelId = useId();

  useEffect(() => {
    if (!settingsQ.data) {
      return;
    }
    const fromServer = settingsQ.data.app_timezone || "";
    setAppTimezone(CURATED_TIMEZONE_ID_SET.has(fromServer) ? fromServer : null);
    setLogRetentionDaysDraft(null);
  }, [settingsQ.data]);

  const serverCuratedTimezone =
    settingsQ.data && CURATED_TIMEZONE_ID_SET.has(settingsQ.data.app_timezone || "") ? settingsQ.data.app_timezone : null;

  const editable = canEditSuiteGlobal(me.data?.role);

  const dirty =
    settingsQ.data !== undefined &&
    (appTimezone !== serverCuratedTimezone ||
      (logRetentionDaysDraft !== null && logRetentionDaysDraft !== String(settingsQ.data.log_retention_days)));

  const loadingAny = settingsQ.isPending || me.isPending;

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

  const changePasswordBusy = changePassword.isPending;

  return (
    <div className="mm-page" data-testid="suite-settings-page">
      <header className="mm-page__intro">
        <p className="mm-page__eyebrow">System</p>
        <h1 className="mm-page__title">Settings</h1>
        <p className="mm-page__lead">
          MediaMop-wide choices that are not part of Fetcher, Refiner, Pruner, or Subber. Integration details stay on
          their module pages.
        </p>
      </header>

      <div className="mm-page__body max-w-none">
        <div className="mb-4 flex flex-wrap gap-2" role="tablist" aria-label="Settings sections">
          <button
            type="button"
            role="tab"
            aria-selected={tab === "global"}
            className={tabButtonClass(tab === "global")}
            onClick={() => setTab("global")}
          >
            Global
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
        </div>

        {tab === "global" ? (
          <section
            className="mm-card w-full"
            aria-labelledby="suite-global-heading"
            data-testid="suite-settings-global"
          >
            <h2 id="suite-global-heading" className="mm-card__title">
              Global
            </h2>
            <p className="mm-card__body">
              Suite-wide settings only. Saving applies right away. Module controls for Fetcher, Refiner, Pruner, and
              Subber stay on their module pages.
            </p>
            {!editable ? (
              <p className="mm-card__body text-sm text-[var(--mm-text3)]">Operators and admins can edit these fields.</p>
            ) : null}

            <div className="mm-card__body space-y-4">
              <label className="block">
                <span id={timezoneLabelId} className="text-xs font-semibold uppercase tracking-wide text-[var(--mm-text3)]">
                  Timezone
                </span>
                <MmListboxPicker
                  ariaLabelledBy={timezoneLabelId}
                  ariaDescribedBy="suite-timezone-hint"
                  placeholder="Select timezone"
                  disabled={!editable || save.isPending}
                  options={timezoneOptions.map((tz) => ({ value: tz.id, label: tz.label }))}
                  value={appTimezone ?? ""}
                  onChange={(v) => setAppTimezone(v)}
                />
                <p id="suite-timezone-hint" className="mt-1 text-xs text-[var(--mm-text3)]">
                  Main-country timezones for suite-level time displays.
                </p>
              </label>

              <label className="block">
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
                  Number of days to keep Activity timeline rows before automatic cleanup.
                </p>
              </label>

              {save.isError ? (
                <p className="text-sm text-red-300" role="alert" data-testid="suite-settings-save-error">
                  {save.error instanceof Error ? save.error.message : "Could not save."}
                </p>
              ) : null}

              {save.isSuccess && !dirty && !save.isPending ? (
                <p className="text-xs text-[var(--mm-text3)]" data-testid="suite-settings-saved-hint">
                  Saved.
                </p>
              ) : null}

              <button
                type="button"
                className={mmActionButtonClass({
                  variant: "primary",
                  disabled: !editable || !dirty || save.isPending,
                })}
                disabled={!editable || !dirty || save.isPending}
                data-testid="suite-settings-save"
                onClick={() => {
                  save.reset();
                  void save.mutateAsync({
                    product_display_name: settingsQ.data.product_display_name,
                    signed_in_home_notice: settingsQ.data.signed_in_home_notice,
                    application_logs_enabled: settingsQ.data.application_logs_enabled,
                    app_timezone: appTimezone ?? settingsQ.data.app_timezone,
                    log_retention_days: finalizeLogRetentionDays(),
                  });
                }}
              >
                {save.isPending ? "Saving…" : "Save global settings"}
              </button>
            </div>
          </section>
        ) : (
          <div className="w-full space-y-4" data-testid="suite-settings-security">
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
        )}
      </div>
    </div>
  );
}
