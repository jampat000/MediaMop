import { browserWindow } from "../../lib/browser-window";
import type { SuiteUpgradeProgressOut } from "../../lib/suite/types";
import type {
  useSuiteUpdateDiagnosticsQuery,
  useSuiteUpdateNowMutation,
  useSuiteUpdateStatusQuery,
} from "../../lib/suite/queries";
import { mmActionButtonClass } from "../../lib/ui/mm-control-roles";
import {
  mmModuleTabBlurbBandClass,
  mmModuleTabBlurbTextClass,
} from "../../lib/ui/mm-module-tab-blurb";
import { useAppDateFormatter } from "../../lib/ui/mm-format-date";
import { suiteUpdateDiagnosticsPath } from "../../lib/suite/suite-settings-api";
import {
  SUITE_SETTINGS_PREMIUM_PANEL_CLASS,
  SUITE_SETTINGS_PREMIUM_TILE_CLASS,
  SUITE_SETTINGS_DASH_CARD_CLASS,
  type UpgradeMonitor,
  type UpgradeNotice,
  type UpgradeHistoryItem,
  upgradeNoticeClass,
  upgradePhaseTone,
} from "./settings-shared";

type SettingsUpgradeTabProps = {
  upgradeMonitor: UpgradeMonitor | null;
  upgradeNotice: UpgradeNotice | null;
  showUpgradeHistory: boolean;
  setShowUpgradeHistory: (v: boolean) => void;
  upgradeHistory: UpgradeHistoryItem[];
  showUpgradeDiagnostics: boolean;
  setShowUpgradeDiagnostics: (v: boolean) => void;
  upgradeBootstrapRequired: boolean;
  activeUpgradeProgress: SuiteUpgradeProgressOut | null | undefined;
  upgradeConnectionLost: boolean;
  upgradeProgressSummary: { label: string; body: string } | null;
  upgradeInProgress: boolean;
  completedUpgradeRefreshPromptKey: string | null;
  upgradeRefreshBusy: boolean;
  upgradeRefreshLabel: string;
  diagnosticsUpgrade: SuiteUpgradeProgressOut | null;
  installerLogTail: string[];
  serviceLogTail: string[];
  diagnosticsHasLogTail: boolean;
  updateStatusQ: ReturnType<typeof useSuiteUpdateStatusQuery>;
  updateDiagnosticsQ: ReturnType<typeof useSuiteUpdateDiagnosticsQuery>;
  updateNow: ReturnType<typeof useSuiteUpdateNowMutation>;
  onUpgradeNow: () => void;
};

export function SettingsUpgradeTab({
  upgradeMonitor,
  upgradeNotice,
  showUpgradeHistory,
  setShowUpgradeHistory,
  upgradeHistory,
  showUpgradeDiagnostics,
  setShowUpgradeDiagnostics,
  upgradeBootstrapRequired,
  activeUpgradeProgress,
  upgradeConnectionLost,
  upgradeProgressSummary,
  upgradeInProgress,
  completedUpgradeRefreshPromptKey,
  upgradeRefreshBusy,
  upgradeRefreshLabel,
  diagnosticsUpgrade,
  installerLogTail,
  serviceLogTail,
  diagnosticsHasLogTail,
  updateStatusQ,
  updateDiagnosticsQ,
  updateNow,
  onUpgradeNow,
}: SettingsUpgradeTabProps) {
  const formatDateTime = useAppDateFormatter();

  return (
    <div data-testid="suite-settings-upgrade-tab" className="mm-bubble-stack">
      <div className={mmModuleTabBlurbBandClass}>
        <p className={mmModuleTabBlurbTextClass}>
          Check the installed version, see the latest release, and start a
          guided in-app upgrade when this install type supports it.
        </p>
      </div>

      <section
        className={SUITE_SETTINGS_DASH_CARD_CLASS}
        data-testid="suite-settings-upgrade"
        aria-labelledby="suite-settings-upgrade-heading"
      >
        <div>
          <h3
            id="suite-settings-upgrade-heading"
            className="text-base font-semibold text-[var(--mm-text1)]"
          >
            Upgrade
          </h3>
          <p className="mt-1 text-sm text-[var(--mm-text2)]">
            Check the running MediaMop version and install the latest release
            for this install type.
          </p>
        </div>

        {updateStatusQ.isPending ? (
          <p className="text-sm text-[var(--mm-text3)]">
            Checking for updates...
          </p>
        ) : !updateStatusQ.data ? (
          upgradeConnectionLost ? (
            <div
              className={`rounded-lg border px-3 py-3 ${upgradePhaseTone(
                undefined,
                null,
                upgradeMonitor,
              )}`}
            >
              <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--mm-gold)]">
                Reconnecting
              </p>
              <p className="mt-1 text-sm leading-6 text-[var(--mm-text2)]">
                MediaMop is reconnecting and verifying the installed version.
              </p>
            </div>
          ) : (
            <p
              className="rounded-md border border-red-500/40 bg-red-950/25 px-3 py-2 text-sm text-red-200"
              role="alert"
            >
              {updateStatusQ.error instanceof Error
                ? updateStatusQ.error.message
                : "Could not check for updates right now."}
            </p>
          )
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
                <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--mm-text3)]">
                  Installed
                </div>
                <div className="mt-1 text-base font-semibold text-[var(--mm-text1)]">
                  {updateStatusQ.data.current_version}
                </div>
              </div>
              <div className={SUITE_SETTINGS_PREMIUM_TILE_CLASS}>
                <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--mm-text3)]">
                  Latest
                </div>
                <div className="mt-1 text-base font-semibold text-[var(--mm-text1)]">
                  {updateStatusQ.data.latest_version || "Unknown"}
                </div>
              </div>
              <div className={SUITE_SETTINGS_PREMIUM_TILE_CLASS}>
                <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--mm-text3)]">
                  Install type
                </div>
                <div className="mt-1 text-base font-semibold capitalize text-[var(--mm-text1)]">
                  {updateStatusQ.data.install_type}
                </div>
              </div>
              <div className={SUITE_SETTINGS_PREMIUM_TILE_CLASS}>
                <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--mm-text3)]">
                  Status
                </div>
                <div className="mt-1 text-base font-semibold capitalize text-[var(--mm-text1)]">
                  {updateStatusQ.data.status.replaceAll("_", " ")}
                </div>
              </div>
            </div>

            <div className={SUITE_SETTINGS_PREMIUM_PANEL_CLASS}>
              <h4 className="text-sm font-semibold text-[var(--mm-text1)]">
                What happens next
              </h4>
              {upgradeBootstrapRequired ? (
                <div className="rounded-lg border border-amber-400/25 bg-amber-400/[0.06] px-3 py-2">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--mm-gold)]">
                    One-time setup required
                  </p>
                  <p className="mt-1 text-sm leading-6 text-[var(--mm-text2)]">
                    Run the latest MediaMop installer once on the MediaMop
                    computer as administrator so it can install the local
                    updater service. After that one admin install, future
                    upgrades can start remotely from this page.
                  </p>
                </div>
              ) : null}
              {updateStatusQ.data.install_type === "windows" &&
              updateStatusQ.data.status === "update_available" ? (
                updateStatusQ.data.in_app_upgrade_supported ? (
                  <p className="text-sm leading-6 text-[var(--mm-text2)]">
                    Upgrade now downloads the trusted installer, verifies it,
                    runs the installer, and waits for MediaMop to reconnect and
                    prove the running version changed.
                  </p>
                ) : (
                  <p className="text-sm leading-6 text-[var(--mm-text2)]">
                    {updateStatusQ.data.in_app_upgrade_summary ||
                      "This Windows install cannot run a remote in-app upgrade yet. Run the latest installer locally once as administrator first so it can install the local updater service."}
                  </p>
                )
              ) : updateStatusQ.data.install_type === "windows" ? (
                <p className="text-sm leading-6 text-[var(--mm-text2)]">
                  {updateStatusQ.data.in_app_upgrade_summary ||
                    "This Windows install does not need an update right now."}
                </p>
              ) : null}
              {updateStatusQ.data.install_type === "docker" &&
              updateStatusQ.data.docker_update_command ? (
                <div className="space-y-2">
                  <p className="rounded-lg border border-[var(--mm-border)] bg-[var(--mm-card-bg)] px-3 py-2 font-mono text-xs text-[var(--mm-text3)]">
                    {updateStatusQ.data.docker_update_command}
                  </p>
                  <p className="text-sm leading-6 text-[var(--mm-text2)]">
                    Keep the same MEDIAMOP_HOME volume and
                    MEDIAMOP_SESSION_SECRET value across upgrades so browser
                    sessions and setup state continue cleanly.
                  </p>
                </div>
              ) : null}
            </div>

            {upgradeProgressSummary ? (
              <div
                className={`rounded-lg border px-3 py-3 ${upgradePhaseTone(
                  updateStatusQ.data,
                  activeUpgradeProgress,
                  upgradeMonitor,
                )}`}
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--mm-gold)]">
                      {upgradeProgressSummary.label}
                    </p>
                    <p className="mt-1 text-sm leading-6 text-[var(--mm-text2)]">
                      {upgradeProgressSummary.body}
                    </p>
                  </div>
                  {activeUpgradeProgress?.target_version ? (
                    <span className="rounded-full border border-[var(--mm-border)] bg-[var(--mm-card-bg)] px-2.5 py-1 text-xs font-medium text-[var(--mm-text2)]">
                      Target {activeUpgradeProgress.target_version}
                    </span>
                  ) : null}
                </div>
                {activeUpgradeProgress?.attempt_id ||
                upgradeMonitor?.attemptId ||
                activeUpgradeProgress?.current_version_seen ||
                updateStatusQ.data.current_version ||
                activeUpgradeProgress?.installer_log_path ||
                activeUpgradeProgress?.service_log_path ||
                activeUpgradeProgress?.phase === "failed" ||
                Boolean(upgradeMonitor?.timedOutReason) ? (
                  <div className="mt-3 space-y-1 text-xs text-[var(--mm-text3)]">
                    {activeUpgradeProgress?.attempt_id ||
                    upgradeMonitor?.attemptId ? (
                      <p>
                        Attempt ID:{" "}
                        {activeUpgradeProgress?.attempt_id ||
                          upgradeMonitor?.attemptId}
                      </p>
                    ) : null}
                    <p>Status: {upgradeProgressSummary.label}</p>
                    {activeUpgradeProgress?.current_version_seen ||
                    updateStatusQ.data.current_version ? (
                      <p>
                        Current version seen:{" "}
                        {activeUpgradeProgress?.current_version_seen ||
                          updateStatusQ.data.current_version}
                      </p>
                    ) : null}
                    {activeUpgradeProgress?.installer_log_path ? (
                      <p>
                        Installer log:{" "}
                        {activeUpgradeProgress.installer_log_path}
                      </p>
                    ) : null}
                    {activeUpgradeProgress?.service_log_path ? (
                      <p>
                        Service log: {activeUpgradeProgress.service_log_path}
                      </p>
                    ) : null}
                    {(activeUpgradeProgress?.phase === "failed" ||
                      upgradeMonitor?.timedOutReason) && (
                      <a
                        className="text-[var(--mm-link)] underline-offset-2 hover:underline"
                        href={suiteUpdateDiagnosticsPath()}
                        target="_blank"
                        rel="noreferrer"
                      >
                        Open updater diagnostics
                      </a>
                    )}
                  </div>
                ) : null}
              </div>
            ) : null}

            {updateStatusQ.data.install_type === "windows" ? (
              <div className={SUITE_SETTINGS_PREMIUM_PANEL_CLASS}>
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <h4 className="text-sm font-semibold text-[var(--mm-text1)]">
                    Updater diagnostics
                  </h4>
                  <button
                    type="button"
                    className={mmActionButtonClass({
                      variant: "tertiary",
                      disabled: false,
                    })}
                    onClick={() =>
                      setShowUpgradeDiagnostics(!showUpgradeDiagnostics)
                    }
                  >
                    {showUpgradeDiagnostics
                      ? "Hide diagnostics"
                      : "Show diagnostics"}
                  </button>
                </div>
                {showUpgradeDiagnostics ? (
                  updateDiagnosticsQ.isPending ? (
                    <p className="text-sm text-[var(--mm-text3)]">
                      Loading diagnostics...
                    </p>
                  ) : updateDiagnosticsQ.isError ? (
                    <p
                      className="rounded-md border border-red-500/40 bg-red-950/25 px-3 py-2 text-sm text-red-200"
                      role="alert"
                    >
                      {updateDiagnosticsQ.error instanceof Error
                        ? updateDiagnosticsQ.error.message
                        : "Could not load updater diagnostics."}
                    </p>
                  ) : updateDiagnosticsQ.data ? (
                    <div className="space-y-2 text-xs text-[var(--mm-text3)]">
                      <p>
                        Running version:{" "}
                        {updateDiagnosticsQ.data.current_version}
                      </p>
                      <p>
                        Latest version:{" "}
                        {updateDiagnosticsQ.data.latest_version || "Unknown"}
                      </p>
                      <p>
                        Install root:{" "}
                        {updateDiagnosticsQ.data.install_root || "Unavailable"}
                      </p>
                      <p>
                        Runtime home:{" "}
                        {updateDiagnosticsQ.data.runtime_home || "Unavailable"}
                      </p>
                      <p>
                        Updater service reachable:{" "}
                        {updateDiagnosticsQ.data.updater_service_reachable
                          ? "Yes"
                          : "No"}
                      </p>
                      {diagnosticsUpgrade?.stale_reason ? (
                        <p>Stale reason: {diagnosticsUpgrade.stale_reason}</p>
                      ) : null}
                      {updateDiagnosticsQ.data.installer_log_path ? (
                        <p>
                          Installer log:{" "}
                          {updateDiagnosticsQ.data.installer_log_path}
                        </p>
                      ) : null}
                      {updateDiagnosticsQ.data.service_log_path ? (
                        <p>
                          Service log:{" "}
                          {updateDiagnosticsQ.data.service_log_path}
                        </p>
                      ) : null}
                      <a
                        className="text-[var(--mm-link)] underline-offset-2 hover:underline"
                        href={suiteUpdateDiagnosticsPath()}
                        target="_blank"
                        rel="noreferrer"
                      >
                        Open full updater diagnostics
                      </a>
                      {diagnosticsHasLogTail ? (
                        <details className="rounded-md border border-[var(--mm-border)] bg-black/10 px-3 py-2">
                          <summary className="cursor-pointer text-sm text-[var(--mm-text2)]">
                            Recent updater log tail
                          </summary>
                          <div className="mt-2 space-y-3">
                            {installerLogTail.length > 0 ? (
                              <div>
                                <p className="mb-1 text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--mm-gold)]">
                                  Installer
                                </p>
                                <pre className="max-h-36 overflow-auto whitespace-pre-wrap text-[11px] leading-5 text-[var(--mm-text3)]">
                                  {installerLogTail.join("\n")}
                                </pre>
                              </div>
                            ) : null}
                            {serviceLogTail.length > 0 ? (
                              <div>
                                <p className="mb-1 text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--mm-gold)]">
                                  Updater service
                                </p>
                                <pre className="max-h-36 overflow-auto whitespace-pre-wrap text-[11px] leading-5 text-[var(--mm-text3)]">
                                  {serviceLogTail.join("\n")}
                                </pre>
                              </div>
                            ) : null}
                          </div>
                        </details>
                      ) : null}
                    </div>
                  ) : (
                    <p className="text-sm text-[var(--mm-text3)]">
                      Diagnostics are unavailable right now.
                    </p>
                  )
                ) : (
                  <p className="text-sm text-[var(--mm-text2)]">
                    Includes updater reachability, current phase, log paths, and
                    recent log lines for support triage.
                  </p>
                )}
              </div>
            ) : null}

            <div className={SUITE_SETTINGS_PREMIUM_PANEL_CLASS}>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h4 className="text-sm font-semibold text-[var(--mm-text1)]">
                  Upgrade history
                </h4>
                <button
                  type="button"
                  className={mmActionButtonClass({
                    variant: "tertiary",
                    disabled: false,
                  })}
                  onClick={() => setShowUpgradeHistory(!showUpgradeHistory)}
                >
                  {showUpgradeHistory ? "Hide history" : "Show history"}
                </button>
              </div>
              {showUpgradeHistory ? (
                upgradeHistory.length === 0 ? (
                  <p className="text-sm text-[var(--mm-text3)]">
                    No recorded in-app upgrade attempts yet.
                  </p>
                ) : (
                  <ul className="space-y-2">
                    {upgradeHistory.map((entry) => (
                      <li
                        key={entry.id}
                        className="rounded-md border border-[var(--mm-border)] bg-black/10 px-3 py-2 text-xs text-[var(--mm-text3)]"
                      >
                        <p className="font-semibold text-[var(--mm-text2)]">
                          {entry.status_label} - {entry.phase}
                        </p>
                        <p className="mt-1">{entry.message}</p>
                        <p className="mt-1">
                          {formatDateTime(entry.recorded_at)}
                        </p>
                        {entry.target_version ? (
                          <p>Target: {entry.target_version}</p>
                        ) : null}
                        {entry.current_version_seen ? (
                          <p>
                            Current version seen: {entry.current_version_seen}
                          </p>
                        ) : null}
                        {entry.attempt_id ? (
                          <p>Attempt ID: {entry.attempt_id}</p>
                        ) : null}
                      </li>
                    ))}
                  </ul>
                )
              ) : (
                <p className="text-sm text-[var(--mm-text2)]">
                  Keeps recent in-app upgrade outcomes for quick operator
                  review.
                </p>
              )}
            </div>

            <div className="mt-auto flex flex-wrap gap-2 border-t border-[var(--mm-border)] pt-4">
              <button
                type="button"
                className={mmActionButtonClass({
                  variant: "secondary",
                  disabled: upgradeRefreshBusy,
                })}
                disabled={upgradeRefreshBusy}
                onClick={() => void updateStatusQ.refetch()}
              >
                {upgradeRefreshLabel}
              </button>
              {updateStatusQ.data.install_type === "windows" &&
              updateStatusQ.data.status === "update_available" &&
              updateStatusQ.data.in_app_upgrade_supported ? (
                <button
                  type="button"
                  className={mmActionButtonClass({
                    variant: "primary",
                    disabled: updateNow.isPending || upgradeInProgress,
                  })}
                  disabled={updateNow.isPending || upgradeInProgress}
                  onClick={() => onUpgradeNow()}
                >
                  {updateNow.isPending
                    ? "Starting upgrade..."
                    : upgradeInProgress
                      ? "Upgrade in progress..."
                      : "Upgrade now"}
                </button>
              ) : null}
              {updateStatusQ.data.windows_installer_url ? (
                <a
                  className={mmActionButtonClass({
                    variant: "tertiary",
                    disabled: false,
                  })}
                  href={updateStatusQ.data.windows_installer_url}
                  target="_blank"
                  rel="noreferrer"
                >
                  Download installer
                </a>
              ) : null}
              {updateStatusQ.data.release_url ? (
                <a
                  className={mmActionButtonClass({
                    variant: "tertiary",
                    disabled: false,
                  })}
                  href={updateStatusQ.data.release_url}
                  target="_blank"
                  rel="noreferrer"
                >
                  Release notes
                </a>
              ) : null}
            </div>
            {upgradeNotice ? (
              <p className={upgradeNoticeClass(upgradeNotice.tone)}>
                {upgradeNotice.text}
              </p>
            ) : null}
            {completedUpgradeRefreshPromptKey ? (
              <div className="rounded-md border border-emerald-500/30 bg-emerald-950/15 px-3 py-3 text-sm text-emerald-100">
                <p>Reload to continue in the updated session.</p>
                <div className="mt-3">
                  <button
                    type="button"
                    className={mmActionButtonClass({
                      variant: "secondary",
                      disabled: false,
                    })}
                    onClick={() => browserWindow.reloadCurrentPage()}
                  >
                    Reload now
                  </button>
                </div>
              </div>
            ) : null}
            {updateNow.isError ? (
              <p
                className="rounded-md border border-red-500/40 bg-red-950/25 px-3 py-2 text-sm text-red-200"
                role="alert"
              >
                {updateNow.error instanceof Error
                  ? updateNow.error.message
                  : "Could not start the upgrade."}
              </p>
            ) : null}
          </>
        )}
      </section>
    </div>
  );
}
