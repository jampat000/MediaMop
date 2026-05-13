import type { useSuiteUpdateStatusQuery } from "../../lib/suite/queries";
import { mmActionButtonClass } from "../../lib/ui/mm-control-roles";
import {
  mmModuleTabBlurbBandClass,
  mmModuleTabBlurbTextClass,
} from "../../lib/ui/mm-module-tab-blurb";
import {
  SUITE_SETTINGS_PREMIUM_PANEL_CLASS,
  SUITE_SETTINGS_PREMIUM_TILE_CLASS,
  SUITE_SETTINGS_DASH_CARD_CLASS,
} from "./settings-shared";

type SettingsUpgradeTabProps = {
  updateStatusQ: ReturnType<typeof useSuiteUpdateStatusQuery>;
};

export function SettingsUpgradeTab({ updateStatusQ }: SettingsUpgradeTabProps) {
  return (
    <div data-testid="suite-settings-upgrade-tab" className="mm-bubble-stack">
      <div className={mmModuleTabBlurbBandClass}>
        <p className={mmModuleTabBlurbTextClass}>
          Check the installed version and see the latest release. Windows
          desktop updates are handled automatically by the MediaMop tray app.
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
            Check the running MediaMop version and see the latest release for
            this install type.
          </p>
        </div>

        {updateStatusQ.isPending ? (
          <p className="text-sm text-[var(--mm-text3)]">
            Checking for updates...
          </p>
        ) : !updateStatusQ.data ? (
          <p
            className="rounded-md border border-red-500/40 bg-red-950/25 px-3 py-2 text-sm text-red-200"
            role="alert"
          >
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
              {updateStatusQ.data.install_type === "windows" ? (
                <p className="text-sm leading-6 text-[var(--mm-text2)]">
                  {updateStatusQ.data.in_app_upgrade_summary ||
                    (updateStatusQ.data.status === "update_available"
                      ? "A newer version is available. The MediaMop tray app will download and apply updates automatically based on your update preferences."
                      : "This Windows install does not need an update right now.")}
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

            <div className="mt-auto flex flex-wrap gap-2 border-t border-[var(--mm-border)] pt-4">
              <button
                type="button"
                className={mmActionButtonClass({
                  variant: "secondary",
                  disabled: updateStatusQ.isFetching,
                })}
                disabled={updateStatusQ.isFetching}
                onClick={() => void updateStatusQ.refetch()}
              >
                {updateStatusQ.isFetching ? "Checking..." : "Check again"}
              </button>
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
          </>
        )}
      </section>
    </div>
  );
}
