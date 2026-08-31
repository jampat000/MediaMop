import { useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  useChangePasswordMutation,
  useCurrentSessionQuery,
  useActiveSessionsQuery,
  useRevokeOtherSessionsMutation,
  useRevokeSessionMutation,
} from "../../lib/auth/queries";
import { useSuiteSecurityOverviewQuery } from "../../lib/suite/queries";
import { mmActionButtonClass } from "../../lib/ui/mm-control-roles";
import {
  mmModuleTabBlurbBandClass,
  mmModuleTabBlurbTextClass,
} from "../../lib/ui/mm-module-tab-blurb";
import {
  formatChangePasswordMutationError,
  formatSessionTimeout,
  SettingsSummaryCard,
  SUITE_PASSWORD_FIELD_CLASS,
} from "./settings-shared";

function formatSessionDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "Unknown time";
  }
  return date.toLocaleString([], {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

function securityFlag(value: boolean, good: boolean): string {
  return value === good ? "On" : "Needs attention";
}

export function SettingsSecurityTab() {
  const navigate = useNavigate();
  const changePassword = useChangePasswordMutation();
  const currentSessionQ = useCurrentSessionQuery();
  const securityOverviewQ = useSuiteSecurityOverviewQuery();
  const sessionsQ = useActiveSessionsQuery(currentSessionQ.data !== null);
  const revokeOthers = useRevokeOtherSessionsMutation();
  const revokeSession = useRevokeSessionMutation();

  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showCurrentPassword, setShowCurrentPassword] = useState(false);
  const [showNewPassword, setShowNewPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [changePasswordStatus, setChangePasswordStatus] = useState<
    string | null
  >(null);
  const [sessionStatus, setSessionStatus] = useState<string | null>(null);

  const currentSession = currentSessionQ.data;
  const securityOverview = securityOverviewQ.data;
  const changePasswordBusy = changePassword.isPending;

  return (
    <div
      className="mm-bubble-stack w-full"
      data-testid="suite-settings-security"
    >
      <div className={mmModuleTabBlurbBandClass}>
        <p className={mmModuleTabBlurbTextClass}>
          Change your MediaMop password here. Sign-in cookie, HTTPS, and
          rate-limit settings follow the server configuration at startup - they
          are not edited in this UI.
        </p>
      </div>
      <section
        className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4"
        aria-label="Current sign-in"
      >
        <SettingsSummaryCard
          label="This browser"
          value={
            currentSession
              ? currentSession.trusted_device
                ? "Trusted"
                : "Standard"
              : currentSessionQ.isError
                ? "Unavailable"
                : "Loading..."
          }
          detail={
            currentSession
              ? currentSession.trusted_device
                ? "Long-lived sign-in for this device"
                : "Normal sign-in lifetime"
              : currentSessionQ.isError
                ? "Could not read the current sign-in session."
                : "Checking the current sign-in session."
          }
        />
        <SettingsSummaryCard
          label="Idle timeout"
          value={
            currentSession
              ? formatSessionTimeout(currentSession.idle_timeout_minutes)
              : securityOverview
                ? securityOverview.standard_session_idle_timeout_plain
                : "Loading..."
          }
          detail={
            currentSession?.trusted_device
              ? "Trusted-device idle timeout"
              : "Standard idle timeout"
          }
        />
        <SettingsSummaryCard
          label="Max sign-in age"
          value={
            currentSession
              ? `${currentSession.absolute_timeout_days} days`
              : securityOverview
                ? securityOverview.standard_session_absolute_timeout_plain
                : "Loading..."
          }
          detail={
            currentSession?.trusted_device
              ? "Trusted-device maximum session age"
              : "Standard maximum session age"
          }
        />
        <SettingsSummaryCard
          label="Trusted devices"
          value={
            securityOverview
              ? securityOverview.trusted_session_absolute_timeout_plain
              : "Loading..."
          }
          detail={
            securityOverview
              ? `Idle timeout ${securityOverview.trusted_session_idle_timeout_plain}`
              : "Loading trusted-device policy."
          }
        />
      </section>
      <section
        className="mm-card w-full"
        aria-labelledby="suite-security-posture-heading"
      >
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 id="suite-security-posture-heading" className="mm-card__title">
              Security posture
            </h2>
            <p className="mm-card__body text-sm text-[var(--mm-text2)]">
              These values describe the protections currently active in the
              running server. They are read-only here and take effect after a
              restart.
            </p>
          </div>
          {securityOverview?.restart_required_note ? (
            <span className="mm-status-badge mm-status-badge--info">
              Startup configuration
            </span>
          ) : null}
        </div>
        {securityOverview ? (
          <dl className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            <div className="mm-security-fact">
              <dt>Session signing</dt>
              <dd
                className={
                  securityOverview.session_signing_configured
                    ? "mm-status-text--healthy"
                    : "mm-status-text--failed"
                }
              >
                {securityFlag(
                  securityOverview.session_signing_configured,
                  true,
                )}
              </dd>
            </div>
            <div className="mm-security-fact">
              <dt>HTTPS-only sign-in cookie</dt>
              <dd
                className={
                  securityOverview.sign_in_cookie_https_only
                    ? "mm-status-text--healthy"
                    : "mm-status-text--warning"
                }
              >
                {securityOverview.sign_in_cookie_https_only
                  ? "On"
                  : "Off — use HTTPS in production"}
              </dd>
            </div>
            <div className="mm-security-fact">
              <dt>Same-site cookie policy</dt>
              <dd>{securityOverview.sign_in_cookie_same_site}</dd>
            </div>
            <div className="mm-security-fact">
              <dt>Standard session</dt>
              <dd>
                Idle {securityOverview.standard_session_idle_timeout_plain}; max{" "}
                {securityOverview.standard_session_absolute_timeout_plain}
              </dd>
            </div>
            <div className="mm-security-fact">
              <dt>Trusted-device session</dt>
              <dd>
                Idle {securityOverview.trusted_session_idle_timeout_plain}; max{" "}
                {securityOverview.trusted_session_absolute_timeout_plain}
              </dd>
            </div>
            <div className="mm-security-fact">
              <dt>Strict transport hardening</dt>
              <dd
                className={
                  securityOverview.extra_https_hardening_enabled
                    ? "mm-status-text--healthy"
                    : "mm-status-text--warning"
                }
              >
                {securityOverview.extra_https_hardening_enabled
                  ? "On"
                  : "Off — review HTTPS deployment"}
              </dd>
            </div>
            <div className="mm-security-fact">
              <dt>Sign-in rate limit</dt>
              <dd>
                {securityOverview.sign_in_attempt_limit} attempts /{" "}
                {securityOverview.sign_in_attempt_window_plain}
              </dd>
            </div>
            <div className="mm-security-fact">
              <dt>First-time setup rate limit</dt>
              <dd>
                {securityOverview.first_time_setup_attempt_limit} attempts /{" "}
                {securityOverview.first_time_setup_attempt_window_plain}
              </dd>
            </div>
            <div className="mm-security-fact">
              <dt>Allowed browser origins</dt>
              <dd>
                {securityOverview.allowed_browser_origins_count} configured
                origin
                {securityOverview.allowed_browser_origins_count === 1
                  ? ""
                  : "s"}
              </dd>
            </div>
          </dl>
        ) : securityOverviewQ.isError ? (
          <p
            className="mt-4 text-sm text-[var(--mm-status-failed-text)]"
            role="alert"
          >
            Could not load the server security overview. Check the server logs
            and try again.
          </p>
        ) : (
          <p className="mt-4 text-sm text-[var(--mm-text2)]">
            Loading server security overview…
          </p>
        )}
        {securityOverview?.restart_required_note ? (
          <p className="mt-4 rounded-md border border-[var(--mm-border)] bg-[var(--mm-surface-2)]/50 p-3 text-sm text-[var(--mm-text2)]">
            {securityOverview.restart_required_note}
          </p>
        ) : null}
      </section>
      <section
        className="mm-card w-full"
        aria-labelledby="suite-security-sessions-heading"
      >
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 id="suite-security-sessions-heading" className="mm-card__title">
              Active sessions
            </h2>
            <p className="mm-card__body text-sm text-[var(--mm-text2)]">
              Review signed-in browsers and sign out anything you no longer
              recognize. Session tokens are never shown.
            </p>
          </div>
          <button
            type="button"
            className={mmActionButtonClass({
              variant: "tertiary",
              disabled: revokeOthers.isPending || sessionsQ.isPending,
            })}
            disabled={
              revokeOthers.isPending ||
              sessionsQ.isPending ||
              (sessionsQ.data ?? []).filter((item) => !item.current).length ===
                0
            }
            onClick={async () => {
              setSessionStatus(null);
              try {
                const result = await revokeOthers.mutateAsync();
                setSessionStatus(result.message);
              } catch {
                setSessionStatus(
                  "Could not sign out the other sessions. Refresh and try again.",
                );
              }
            }}
          >
            {revokeOthers.isPending
              ? "Signing out…"
              : "Sign out other sessions"}
          </button>
        </div>
        {sessionStatus ? (
          <p className="mt-3 text-sm text-[var(--mm-text2)]" role="status">
            {sessionStatus}
          </p>
        ) : null}
        {sessionsQ.isError ? (
          <p
            className="mt-4 text-sm text-[var(--mm-status-failed-text)]"
            role="alert"
          >
            Could not load active sessions. Refresh the page to try again.
          </p>
        ) : sessionsQ.isPending ? (
          <p className="mt-4 text-sm text-[var(--mm-text2)]">
            Loading active sessions…
          </p>
        ) : (sessionsQ.data ?? []).length === 0 ? (
          <p className="mt-4 text-sm text-[var(--mm-text2)]">
            No active sessions were found.
          </p>
        ) : (
          <div className="mt-4 grid gap-2" data-testid="active-sessions">
            {(sessionsQ.data ?? []).map((session) => (
              <article key={session.session_id} className="mm-session-row">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <h3 className="text-sm font-semibold text-[var(--mm-text1)]">
                      {session.client_label || "Browser session"}
                    </h3>
                    {session.current ? (
                      <span className="mm-status-badge mm-status-badge--ok">
                        This browser
                      </span>
                    ) : null}
                    {session.trusted_device ? (
                      <span className="mm-status-badge mm-status-badge--info">
                        Trusted
                      </span>
                    ) : null}
                  </div>
                  <p className="mt-1 text-xs text-[var(--mm-text2)]">
                    Last seen {formatSessionDate(session.last_seen_at)} ·
                    Expires {formatSessionDate(session.absolute_expires_at)}
                  </p>
                </div>
                <button
                  type="button"
                  className={mmActionButtonClass({
                    variant: "tertiary",
                    disabled: session.current || revokeSession.isPending,
                  })}
                  disabled={session.current || revokeSession.isPending}
                  onClick={async () => {
                    setSessionStatus(null);
                    try {
                      const result = await revokeSession.mutateAsync(
                        session.session_id,
                      );
                      setSessionStatus(result.message);
                    } catch {
                      setSessionStatus(
                        "Could not sign out that session. It may already be inactive.",
                      );
                    }
                  }}
                >
                  {revokeSession.isPending ? "Signing out…" : "Sign out"}
                </button>
              </article>
            ))}
          </div>
        )}
      </section>
      <section
        className="mm-card w-full"
        aria-labelledby="suite-security-change-password-heading"
      >
        <h2
          id="suite-security-change-password-heading"
          className="mm-card__title"
        >
          Change password
        </h2>
        <p className="mm-card__body text-sm text-[var(--mm-text2)]">
          Update your sign-in password. After saving, MediaMop requires a fresh
          sign-in.
        </p>
        <div className="mm-card__body space-y-3">
          <label className="block">
            <span className="text-xs font-semibold uppercase tracking-wide text-[var(--mm-text3)]">
              Current password
            </span>
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
                className={mmActionButtonClass({
                  variant: "tertiary",
                  disabled: changePasswordBusy,
                })}
                disabled={changePasswordBusy}
                onClick={() => setShowCurrentPassword((prev) => !prev)}
              >
                {showCurrentPassword ? "Hide" : "Show"}
              </button>
            </div>
          </label>
          <label className="block">
            <span className="text-xs font-semibold uppercase tracking-wide text-[var(--mm-text3)]">
              New password
            </span>
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
                className={mmActionButtonClass({
                  variant: "tertiary",
                  disabled: changePasswordBusy,
                })}
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
                className={mmActionButtonClass({
                  variant: "tertiary",
                  disabled: changePasswordBusy,
                })}
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
                setChangePasswordStatus(
                  "Password changed. Sign in again with your new password.",
                );
                void navigate("/login", { replace: true });
              } catch {
                setShowCurrentPassword(false);
                setShowNewPassword(false);
                setShowConfirmPassword(false);
                /* surfaced above */
              }
            }}
          >
            {changePassword.isPending ? "Saving..." : "Change password"}
          </button>
        </div>
      </section>
    </div>
  );
}
