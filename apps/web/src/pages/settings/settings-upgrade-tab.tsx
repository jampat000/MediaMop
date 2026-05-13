import { useState, useEffect } from "react";
import type { useSuiteUpdateStatusQuery } from "../../lib/suite/queries";
import {
  useUpdateSettingsQuery,
  useUpdateSettingsMutation,
} from "../../lib/suite/queries";
import type { UpdateMode } from "../../lib/suite/types";
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

const UPDATE_MODES: {
  value: UpdateMode;
  label: string;
  description: string;
}[] = [
  {
    value: "Auto",
    label: "Auto",
    description:
      "Download and install updates automatically. You will be prompted to restart.",
  },
  {
    value: "DownloadOnly",
    label: "Download only",
    description:
      "Download updates silently in the background, then notify you when ready to install.",
  },
  {
    value: "NotifyOnly",
    label: "Notify only",
    description:
      "Alert you when an update is available without downloading anything.",
  },
];

export function SettingsUpgradeTab({ updateStatusQ }: SettingsUpgradeTabProps) {
  const updateSettingsQ = useUpdateSettingsQuery(
    updateStatusQ.data?.install_type === "windows",
  );
  const saveMode = useUpdateSettingsMutation();
  const [modeDraft, setModeDraft] = useState<UpdateMode | null>(null);
  const [saveMsg, setSaveMsg] = useState<string | null>(null);

  useEffect(() => {
    if (updateSettingsQ.data) {
      setModeDraft(updateSettingsQ.data.mode);
    }
  }, [updateSettingsQ.data]);

  const serverMode = updateSettingsQ.data?.mode ?? null;
  const modeDirty = modeDraft !== null && modeDraft !== serverMode;

  async function handleSaveMode() {
    if (!modeDraft || !updateSettingsQ.data) return;
    setSaveMsg(null);
    saveMode.reset();
    try {
      await saveMode.mutateAsync({
        mode: modeDraft,
        check_on_startup: updateSettingsQ.data.check_on_startup,
        check_interval_minutes: updateSettingsQ.data.check_interval_minutes,
      });
      setSaveMsg("Update mode saved.");
    } catch {
      /* surfaced via saveMode.isError */
    }
  }

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

            {updateStatusQ.data.install_type === "windows" ? (
              <div className={SUITE_SETTINGS_PREMIUM_PANEL_CLASS}>
                <h4 className="text-sm font-semibold text-[var(--mm-text1)]">
                  Update mode
                </h4>
                <p className="text-sm text-[var(--mm-text2)]">
                  Choose how the MediaMop tray app handles available updates.
                </p>
                {updateSettingsQ.isPending ? (
                  <p className="text-sm text-[var(--mm-text3)]">
                    Loading update preferences...
                  </p>
                ) : updateSettingsQ.isError ? (
                  <p className="text-sm text-[var(--mm-text3)]">
                    Could not load update preferences.
                  </p>
                ) : (
                  <fieldset className="mt-1 space-y-3">
                    <legend className="sr-only">Update mode</legend>
                    {UPDATE_MODES.map((opt) => (
                      <label
                        key={opt.value}
                        className="flex cursor-pointer items-start gap-3"
                      >
                        <input
                          type="radio"
                          name="update-mode"
                          value={opt.value}
                          checked={modeDraft === opt.value}
                          onChange={() => {
                            setModeDraft(opt.value);
                            setSaveMsg(null);
                            saveMode.reset();
                          }}
                          className="mt-0.5 accent-[var(--mm-accent)]"
                        />
                        <span>
                          <span className="block text-sm font-medium text-[var(--mm-text1)]">
                            {opt.label}
                          </span>
                          <span className="block text-sm text-[var(--mm-text2)]">
                            {opt.description}
                          </span>
                        </span>
                      </label>
                    ))}
                  </fieldset>
                )}

                {saveMode.isError && (
                  <p
                    className="rounded-md border border-red-500/40 bg-red-950/25 px-3 py-2 text-sm text-red-200"
                    role="alert"
                  >
                    {saveMode.error instanceof Error
                      ? saveMode.error.message
                      : "Could not save update mode."}
                  </p>
                )}
                {saveMsg && !saveMode.isError && (
                  <p className="text-sm text-emerald-400">{saveMsg}</p>
                )}

                <div className="flex gap-2 pt-1">
                  <button
                    type="button"
                    className={mmActionButtonClass({
                      variant: "primary",
                      disabled:
                        !modeDirty ||
                        saveMode.isPending ||
                        updateSettingsQ.isPending,
                    })}
                    disabled={
                      !modeDirty ||
                      saveMode.isPending ||
                      updateSettingsQ.isPending
                    }
                    onClick={() => void handleSaveMode()}
                  >
                    {saveMode.isPending ? "Saving..." : "Save"}
                  </button>
                  {modeDirty && (
                    <button
                      type="button"
                      className={mmActionButtonClass({
                        variant: "secondary",
                        disabled: saveMode.isPending,
                      })}
                      disabled={saveMode.isPending}
                      onClick={() => {
                        setModeDraft(serverMode);
                        setSaveMsg(null);
                        saveMode.reset();
                      }}
                    >
                      Discard
                    </button>
                  )}
                </div>
              </div>
            ) : updateStatusQ.data.install_type === "docker" &&
              updateStatusQ.data.docker_update_command ? (
              <div className={SUITE_SETTINGS_PREMIUM_PANEL_CLASS}>
                <h4 className="text-sm font-semibold text-[var(--mm-text1)]">
                  What happens next
                </h4>
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
              </div>
            ) : null}

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
