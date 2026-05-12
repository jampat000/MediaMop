import { useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  useChangePasswordMutation,
  useCurrentSessionQuery,
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

export function SettingsSecurityTab() {
  const navigate = useNavigate();
  const changePassword = useChangePasswordMutation();
  const currentSessionQ = useCurrentSessionQuery();
  const securityOverviewQ = useSuiteSecurityOverviewQuery();

  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showCurrentPassword, setShowCurrentPassword] = useState(false);
  const [showNewPassword, setShowNewPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [changePasswordStatus, setChangePasswordStatus] = useState<
    string | null
  >(null);

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
          rate-limit settings follow the server configuration at startup -
          they are not edited in this UI.
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
        aria-labelledby="suite-security-change-password-heading"
      >
        <h2
          id="suite-security-change-password-heading"
          className="mm-card__title"
        >
          Change password
        </h2>
        <p className="mm-card__body text-sm text-[var(--mm-text2)]">
          Update your sign-in password. After saving, MediaMop requires a
          fresh sign-in.
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
                navigate("/login", { replace: true });
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
