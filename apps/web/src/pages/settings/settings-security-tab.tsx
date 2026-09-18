import { useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  useChangePasswordMutation,
  useChangeUsernameMutation,
  useCurrentSessionQuery,
  useActiveSessionsQuery,
  useRevokeOtherSessionsMutation,
  useRevokeSessionMutation,
} from "../../lib/auth/queries";
import { useSuiteSecurityOverviewQuery } from "../../lib/suite/queries";
import { mmActionButtonClass } from "../../lib/ui/mm-control-roles";
import { useAppDateFormatter } from "../../lib/ui/mm-format-date";
import {
  mmModuleTabBlurbBandClass,
  mmModuleTabBlurbTextClass,
} from "../../lib/ui/mm-module-tab-blurb";
import {
  formatChangePasswordMutationError,
  formatSessionTimeout,
  SettingsFactTable,
  SettingsQuietSection,
  SUITE_PASSWORD_FIELD_CLASS,
  type SettingsFact,
} from "./settings-shared";

function securityFlag(value: boolean, good: boolean): string {
  return value === good ? "On" : "Needs attention";
}

export function SettingsSecurityTab() {
  const formatDate = useAppDateFormatter();
  const navigate = useNavigate();
  const changePassword = useChangePasswordMutation();
  const changeUsername = useChangeUsernameMutation();
  const [newUsername, setNewUsername] = useState("");
  const [usernamePassword, setUsernamePassword] = useState("");
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

  const currentSignInFacts: SettingsFact[] = [
    {
      label: "This browser",
      value: currentSession
        ? currentSession.trusted_device
          ? "Trusted"
          : "Standard"
        : currentSessionQ.isError
          ? "Unavailable"
          : "Loading...",
      detail: currentSession
        ? currentSession.trusted_device
          ? "Long-lived sign-in for this device"
          : "Normal sign-in lifetime"
        : currentSessionQ.isError
          ? "Could not read the current sign-in session."
          : "Checking the current sign-in session.",
    },
    {
      label: "Idle timeout",
      value: currentSession
        ? formatSessionTimeout(currentSession.idle_timeout_minutes)
        : securityOverview
          ? securityOverview.standard_session_idle_timeout_plain
          : "Loading...",
      detail: currentSession?.trusted_device
        ? "Trusted-device idle timeout"
        : "Standard idle timeout",
    },
    {
      label: "Max sign-in age",
      value: currentSession
        ? `${currentSession.absolute_timeout_days} days`
        : securityOverview
          ? securityOverview.standard_session_absolute_timeout_plain
          : "Loading...",
      detail: currentSession?.trusted_device
        ? "Trusted-device maximum session age"
        : "Standard maximum session age",
    },
    {
      label: "Trusted devices",
      value: securityOverview
        ? securityOverview.trusted_session_absolute_timeout_plain
        : "Loading...",
      detail: securityOverview
        ? `Idle timeout ${securityOverview.trusted_session_idle_timeout_plain}`
        : "Loading trusted-device policy.",
    },
  ];

  const postureFacts: SettingsFact[] = securityOverview
    ? [
        {
          label: "Session signing",
          value: securityFlag(
            securityOverview.session_signing_configured,
            true,
          ),
          toneClass: securityOverview.session_signing_configured
            ? "mm-status-text--healthy"
            : "mm-status-text--failed",
        },
        {
          label: "HTTPS-only sign-in cookie",
          value: securityOverview.sign_in_cookie_https_plain,
          toneClass:
            securityOverview.sign_in_cookie_https_mode === "never"
              ? "mm-status-text--warning"
              : "mm-status-text--healthy",
        },
        {
          label: "Same-site cookie policy",
          value: securityOverview.sign_in_cookie_same_site,
        },
        {
          label: "Standard session",
          value: `Idle ${securityOverview.standard_session_idle_timeout_plain}; max ${securityOverview.standard_session_absolute_timeout_plain}`,
        },
        {
          label: "Trusted-device session",
          value: `Idle ${securityOverview.trusted_session_idle_timeout_plain}; max ${securityOverview.trusted_session_absolute_timeout_plain}`,
        },
        {
          label: "Strict transport hardening",
          value: securityOverview.extra_https_hardening_enabled
            ? "On"
            : "Off — review HTTPS deployment",
          toneClass: securityOverview.extra_https_hardening_enabled
            ? "mm-status-text--healthy"
            : "mm-status-text--warning",
        },
        {
          label: "Sign-in rate limit",
          value: `${securityOverview.sign_in_attempt_limit} attempts / ${securityOverview.sign_in_attempt_window_plain}`,
        },
        {
          label: "First-time setup rate limit",
          value: `${securityOverview.first_time_setup_attempt_limit} attempts / ${securityOverview.first_time_setup_attempt_window_plain}`,
        },
        {
          label: "Allowed browser origins",
          value: `${securityOverview.allowed_browser_origins_count} configured origin${
            securityOverview.allowed_browser_origins_count === 1 ? "" : "s"
          }`,
        },
      ]
    : [];

  return (
    <div
      className="mm-quiet-stack w-full"
      data-testid="suite-settings-security"
    >
      <div className={mmModuleTabBlurbBandClass}>
        <p className={mmModuleTabBlurbTextClass}>
          Change your Weir password here. Sign-in cookie, HTTPS, and rate-limit
          settings follow the server configuration at startup - they are not
          edited in this UI.
        </p>
      </div>
      <SettingsQuietSection
        headingId="suite-security-current-sign-in-heading"
        heading="Current sign-in"
      >
        <SettingsFactTable
          caption="How this browser is signed in"
          facts={currentSignInFacts}
        />
      </SettingsQuietSection>

      <SettingsQuietSection
        headingId="suite-security-posture-heading"
        heading="Security posture"
        aside={
          securityOverview?.restart_required_note ? (
            <span className="mm-quiet-badge">Startup configuration</span>
          ) : null
        }
      >
        <p className="mm-quiet-note">
          These values describe the protections currently active in the running
          server. They are read-only here and take effect after a restart.
        </p>
        {securityOverview ? (
          <div className="mm-quiet-table-wrap mt-4">
            <table className="mm-quiet-table">
              <thead>
                <tr>
                  <th scope="col">Protection</th>
                  <th scope="col">Setting</th>
                </tr>
              </thead>
              <tbody>
                {postureFacts.map((fact) => (
                  <tr key={fact.label}>
                    <th scope="row" className="mm-quiet-table__name">
                      {fact.label}
                    </th>
                    <td data-label="Setting" className={fact.toneClass}>
                      {fact.value}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : securityOverviewQ.isError ? (
          <p
            className="mt-4 text-sm text-[var(--mm-status-failed-text)]"
            role="alert"
          >
            Could not load the server security overview. Check the server logs
            and try again.
          </p>
        ) : (
          <p className="mm-quiet-note mt-4">
            Loading server security overview…
          </p>
        )}
        {securityOverview?.restart_required_note ? (
          <p className="mm-quiet-note mt-4">
            {securityOverview.restart_required_note}
          </p>
        ) : null}
      </SettingsQuietSection>

      <SettingsQuietSection
        headingId="suite-security-sessions-heading"
        heading="Active sessions"
        aside={
          <button
            type="button"
            className="mm-quiet-link"
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
        }
      >
        <p className="mm-quiet-note">
          Review signed-in browsers and sign out anything you no longer
          recognize. Session tokens are never shown.
        </p>
        {sessionStatus ? (
          <p className="mm-quiet-note mt-3" role="status">
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
          <p className="mm-quiet-note mt-4">Loading active sessions…</p>
        ) : (sessionsQ.data ?? []).length === 0 ? (
          <p className="mm-quiet-note mt-4">No active sessions were found.</p>
        ) : (
          <div className="mm-quiet-table-wrap mt-4">
            <table className="mm-quiet-table" data-testid="active-sessions">
              <thead>
                <tr>
                  <th scope="col">Browser</th>
                  <th scope="col">Last seen</th>
                  <th scope="col">Expires</th>
                  <th scope="col">
                    <span className="sr-only">Sign out</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {(sessionsQ.data ?? []).map((session) => (
                  <tr key={session.session_id}>
                    <th scope="row" className="mm-quiet-table__name">
                      <span>{session.client_label || "Browser session"}</span>
                      {session.current ? (
                        <span className="mm-quiet-badge">This browser</span>
                      ) : null}
                      {session.trusted_device ? (
                        <span className="mm-quiet-badge">Trusted</span>
                      ) : null}
                    </th>
                    <td data-label="Last seen">
                      {formatDate(session.last_seen_at)}
                    </td>
                    <td data-label="Expires">
                      {formatDate(session.absolute_expires_at)}
                    </td>
                    <td data-label="">
                      {/* Signing a session out is immediate and destructive, so it
                          keeps a real button instead of becoming a quiet text link. */}
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
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </SettingsQuietSection>

      <SettingsQuietSection
        headingId="suite-security-change-username-heading"
        heading="Change username"
      >
        <p className="mm-quiet-note">
          Weir has one account. Signing in ignores capitalisation, so{" "}
          <code>admin</code> and <code>Admin</code> are the same name.
        </p>
        <div className="mt-4 max-w-xl space-y-3">
          <label className="block">
            <span className="text-[length:var(--mm-type-eyebrow)] font-semibold uppercase tracking-[var(--mm-tracking-eyebrow)] text-[var(--mm-text3)]">
              New username
            </span>
            <div className="mt-1 flex flex-wrap gap-2">
              <input
                type="text"
                className={SUITE_PASSWORD_FIELD_CLASS}
                placeholder="Enter a new username"
                value={newUsername}
                disabled={changeUsername.isPending}
                onChange={(e) => setNewUsername(e.target.value)}
                autoComplete="username"
              />
            </div>
          </label>
          <label className="block">
            <span className="text-[length:var(--mm-type-eyebrow)] font-semibold uppercase tracking-[var(--mm-tracking-eyebrow)] text-[var(--mm-text3)]">
              Current password
            </span>
            <div className="mt-1 flex flex-wrap gap-2">
              <input
                type="password"
                className={SUITE_PASSWORD_FIELD_CLASS}
                placeholder="Confirm it is you"
                value={usernamePassword}
                disabled={changeUsername.isPending}
                onChange={(e) => setUsernamePassword(e.target.value)}
                autoComplete="current-password"
              />
            </div>
          </label>
          {changeUsername.isError ? (
            <p className="mm-status-text--failed text-sm" role="alert">
              {changeUsername.error instanceof Error
                ? changeUsername.error.message
                : "Could not change the username."}
            </p>
          ) : null}
          {changeUsername.isSuccess ? (
            <p className="text-sm text-[var(--mm-text2)]" role="status">
              {changeUsername.data.message}
            </p>
          ) : null}
          <button
            type="button"
            className={mmActionButtonClass({
              variant: "secondary",
              disabled:
                changeUsername.isPending ||
                newUsername.trim() === "" ||
                usernamePassword === "",
            })}
            disabled={
              changeUsername.isPending ||
              newUsername.trim() === "" ||
              usernamePassword === ""
            }
            onClick={() => {
              changeUsername.mutate(
                {
                  currentPassword: usernamePassword,
                  newUsername: newUsername.trim(),
                },
                {
                  onSuccess: () => {
                    setNewUsername("");
                    setUsernamePassword("");
                  },
                },
              );
            }}
          >
            {changeUsername.isPending ? "Saving…" : "Change username"}
          </button>
        </div>
      </SettingsQuietSection>
      <SettingsQuietSection
        headingId="suite-security-change-password-heading"
        heading="Change password"
      >
        <p className="mm-quiet-note">
          Update your sign-in password. After saving, Weir requires a fresh
          sign-in.
        </p>
        <div className="mt-4 max-w-xl space-y-3">
          <label className="block">
            <span className="text-[length:var(--mm-type-eyebrow)] font-semibold uppercase tracking-[var(--mm-tracking-eyebrow)] text-[var(--mm-text3)]">
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
            <span className="text-[length:var(--mm-type-eyebrow)] font-semibold uppercase tracking-[var(--mm-tracking-eyebrow)] text-[var(--mm-text3)]">
              New password (min. 8 characters)
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
            <span className="text-[length:var(--mm-type-eyebrow)] font-semibold uppercase tracking-[var(--mm-tracking-eyebrow)] text-[var(--mm-text3)]">
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
            <p className="mm-status-text--failed text-sm" role="alert">
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
      </SettingsQuietSection>
    </div>
  );
}
