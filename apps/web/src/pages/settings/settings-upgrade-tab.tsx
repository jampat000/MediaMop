import { useState, useEffect } from "react";
import type { useSuiteUpdateStatusQuery } from "../../lib/suite/queries";
import {
  useApplyUpdateMutation,
  useUpdateSettingsQuery,
  useUpdateSettingsMutation,
  useUpdateStateQuery,
} from "../../lib/suite/queries";
import type { UpdateMode } from "../../lib/suite/types";
import { mmActionButtonClass } from "../../lib/ui/mm-control-roles";
import {
  mmModuleTabBlurbBandClass,
  mmModuleTabBlurbTextClass,
} from "../../lib/ui/mm-module-tab-blurb";
import { quietActionRowClass } from "../../components/shared/quiet-section";
import { mmStatusPillClass } from "../../lib/ui/mm-status-tone";
import {
  SettingsFactTable,
  SettingsQuietSection,
  type SettingsFact,
} from "./settings-shared";

/** "up to date" -> "Up to date": status pills across Weir are sentence case. */
function sentenceCase(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

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

const CHECK_INTERVALS = [
  { value: 15, label: "Every 15 minutes" },
  { value: 30, label: "Every 30 minutes" },
  { value: 60, label: "Every hour" },
  { value: 120, label: "Every 2 hours" },
  { value: 360, label: "Every 6 hours" },
  { value: 720, label: "Every 12 hours" },
  { value: 1440, label: "Every 24 hours" },
];

export function SettingsUpgradeTab({ updateStatusQ }: SettingsUpgradeTabProps) {
  const isWindows = updateStatusQ.data?.install_type === "windows";
  const updateStateQ = useUpdateStateQuery(isWindows);
  const applyUpdate = useApplyUpdateMutation();
  const updateSettingsQ = useUpdateSettingsQuery(isWindows);
  const saveMode = useUpdateSettingsMutation();
  const [modeDraft, setModeDraft] = useState<UpdateMode | null>(null);
  const [checkOnStartupDraft, setCheckOnStartupDraft] = useState(true);
  const [checkIntervalDraft, setCheckIntervalDraft] = useState(60);
  const [saveMsg, setSaveMsg] = useState<string | null>(null);

  useEffect(() => {
    if (updateSettingsQ.data) {
      setModeDraft(updateSettingsQ.data.mode);
      setCheckOnStartupDraft(updateSettingsQ.data.check_on_startup);
      setCheckIntervalDraft(updateSettingsQ.data.check_interval_minutes);
    }
  }, [updateSettingsQ.data]);

  const serverMode = updateSettingsQ.data?.mode ?? null;
  const serverCheckOnStartup = updateSettingsQ.data?.check_on_startup ?? true;
  const serverCheckInterval =
    updateSettingsQ.data?.check_interval_minutes ?? 60;
  const settingsDirty =
    modeDraft !== null &&
    (modeDraft !== serverMode ||
      checkOnStartupDraft !== serverCheckOnStartup ||
      checkIntervalDraft !== serverCheckInterval);

  async function handleSaveMode() {
    if (!modeDraft || !updateSettingsQ.data) return;
    setSaveMsg(null);
    saveMode.reset();
    try {
      await saveMode.mutateAsync({
        mode: modeDraft,
        check_on_startup: checkOnStartupDraft,
        check_interval_minutes: checkIntervalDraft,
      });
      setSaveMsg("Update settings saved.");
    } catch {
      /* surfaced via saveMode.isError */
    }
  }

  // Four coequal facts about this install — a version, a version, a kind, a state.
  // None of them is a magnitude, so none of them is a hero (rule 2).
  const installFacts: SettingsFact[] = updateStatusQ.data
    ? [
        { label: "Installed", value: updateStatusQ.data.current_version },
        {
          label: "Latest",
          value: updateStatusQ.data.latest_version || "Unknown",
        },
        { label: "Install type", value: updateStatusQ.data.install_type },
        {
          label: "Status",
          value: updateStatusQ.data.status.replaceAll("_", " "),
        },
      ]
    : [];

  return (
    <div data-testid="suite-settings-upgrade-tab" className="mm-quiet-stack">
      <div className={mmModuleTabBlurbBandClass}>
        <p className={mmModuleTabBlurbTextClass}>
          Check the installed version and see the latest release. Windows
          desktop updates are handled automatically by the Weir tray app.
        </p>
      </div>

      <div className="mm-quiet-stack" data-testid="suite-settings-upgrade">
        {updateStatusQ.isPending ? (
          <p className="mm-quiet-note">Checking for updates...</p>
        ) : !updateStatusQ.data ? (
          <p
            className="text-sm text-[var(--mm-status-failed-text)]"
            role="alert"
          >
            {updateStatusQ.error instanceof Error
              ? updateStatusQ.error.message
              : "Could not check for updates right now."}
          </p>
        ) : (
          <>
            {/* The one thing on this tab that wants attention. It stays a filled,
                colour-coded strip: the colour is functional, not decoration. */}
            <div
              className={`rounded-xl border border-[var(--mm-border)] p-4 ${
                updateStatusQ.data.status === "update_available"
                  ? "bg-[var(--mm-status-warning-bg)]"
                  : "bg-[var(--mm-status-healthy-bg)]"
              }`}
            >
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <p className="text-[11px] font-semibold tracking-[0.14em] text-[var(--mm-gold)] uppercase">
                    Release status
                  </p>
                  <h4 className="mt-1 text-base font-semibold text-[var(--mm-text1)]">
                    {updateStatusQ.data.summary}
                  </h4>
                </div>
                <span
                  className={mmStatusPillClass(
                    updateStatusQ.data.status === "update_available"
                      ? "warning"
                      : "healthy",
                  )}
                >
                  {sentenceCase(updateStatusQ.data.status.replaceAll("_", " "))}
                </span>
              </div>
            </div>

            {isWindows && updateStateQ.data?.downloaded && (
              <div className="flex items-start justify-between gap-4 rounded-xl border border-[var(--mm-border)] bg-[var(--mm-status-healthy-bg)] px-4 py-3">
                <div className="min-w-0">
                  <p className="mm-status-text--healthy text-sm font-semibold">
                    Update ready to install
                    {updateStateQ.data.pending_version
                      ? ` — v${updateStateQ.data.pending_version}`
                      : ""}
                  </p>
                  <p className="mt-0.5 text-xs text-[var(--mm-text3)]">
                    The update has been downloaded. Restart Weir to apply it.
                  </p>
                  {applyUpdate.isError && (
                    <p
                      className="mm-status-text--failed mt-1 text-xs"
                      role="alert"
                    >
                      {applyUpdate.error instanceof Error
                        ? applyUpdate.error.message
                        : "Could not signal restart."}
                    </p>
                  )}
                  {applyUpdate.isSuccess && (
                    <p className="mm-status-text--healthy mt-1 text-xs">
                      Restart signal sent — the tray will apply the update
                      shortly.
                    </p>
                  )}
                </div>
                <button
                  type="button"
                  className={mmActionButtonClass({
                    variant: "primary",
                    disabled: applyUpdate.isPending || applyUpdate.isSuccess,
                  })}
                  disabled={applyUpdate.isPending || applyUpdate.isSuccess}
                  onClick={() => void applyUpdate.mutateAsync()}
                >
                  {applyUpdate.isPending ? "Restarting..." : "Restart to apply"}
                </button>
              </div>
            )}

            <SettingsQuietSection
              headingId="suite-settings-upgrade-heading"
              heading="Upgrade"
              aside={
                <>
                  <button
                    type="button"
                    className="mm-quiet-link"
                    disabled={updateStatusQ.isFetching}
                    onClick={() => void updateStatusQ.refetch()}
                  >
                    {updateStatusQ.isFetching ? "Checking..." : "Check again →"}
                  </button>
                  {updateStatusQ.data.windows_installer_url ? (
                    <a
                      className="mm-quiet-link"
                      href={updateStatusQ.data.windows_installer_url}
                      target="_blank"
                      rel="noreferrer"
                    >
                      Download installer →
                    </a>
                  ) : null}
                  {updateStatusQ.data.release_url ? (
                    <a
                      className="mm-quiet-link"
                      href={updateStatusQ.data.release_url}
                      target="_blank"
                      rel="noreferrer"
                    >
                      Release notes →
                    </a>
                  ) : null}
                </>
              }
            >
              <p className="mm-quiet-note">
                Check the running Weir version and see the latest release for
                this install type.
              </p>
              <div className="mt-4">
                <SettingsFactTable
                  caption="This Weir install"
                  facts={installFacts}
                />
              </div>
            </SettingsQuietSection>

            {/* An input group with its own Save scope. Rule 3: the scope is the
                section's heading and hairline and the Save row under it, not a box —
                and the choices are radio rows, not bordered tiles inside that box. */}
            {updateStatusQ.data.install_type === "windows" ? (
              <SettingsQuietSection
                headingId="suite-settings-upgrade-mode-heading"
                heading="Update mode"
              >
                <p className="mm-quiet-note">
                  Choose how the Weir tray app handles available updates.
                </p>
                {updateSettingsQ.isPending ? (
                  <p className="mm-quiet-note mt-3">
                    Loading update preferences...
                  </p>
                ) : updateSettingsQ.isError ? (
                  <p className="mm-quiet-note mt-3">
                    Could not load update preferences.
                  </p>
                ) : (
                  <div className="mt-4 max-w-2xl space-y-5">
                    <fieldset className="divide-y divide-[var(--mm-border)]">
                      <legend className="sr-only">Update mode</legend>
                      {UPDATE_MODES.map((opt) => (
                        <label
                          key={opt.value}
                          className={[
                            "flex min-w-0 cursor-pointer items-start gap-2.5 py-2.5 text-sm first:pt-0",
                            modeDraft === opt.value
                              ? "text-[var(--mm-text)]"
                              : "text-[var(--mm-text2)]",
                          ].join(" ")}
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
                            className="mt-0.5 h-4 w-4 shrink-0 accent-[var(--mm-accent)]"
                          />
                          <span className="min-w-0">
                            <span className="block font-medium">
                              {opt.label}
                            </span>
                            <span className="block text-xs text-[var(--mm-text3)]">
                              {opt.description}
                            </span>
                          </span>
                        </label>
                      ))}
                    </fieldset>

                    <div className="space-y-3">
                      <label className="flex cursor-pointer items-center gap-2 text-sm text-[var(--mm-text2)]">
                        <input
                          type="checkbox"
                          className="h-4 w-4 shrink-0 accent-[var(--mm-accent)]"
                          checked={checkOnStartupDraft}
                          onChange={(e) => {
                            setCheckOnStartupDraft(e.target.checked);
                            setSaveMsg(null);
                            saveMode.reset();
                          }}
                        />
                        Check for updates on startup
                      </label>

                      <label className="block text-sm text-[var(--mm-text2)]">
                        <span className="mb-1.5 block text-sm text-[var(--mm-text2)]">
                          Check interval
                        </span>
                        <select
                          className="mm-input w-full max-w-xs"
                          value={checkIntervalDraft}
                          onChange={(e) => {
                            setCheckIntervalDraft(Number(e.target.value));
                            setSaveMsg(null);
                            saveMode.reset();
                          }}
                        >
                          {CHECK_INTERVALS.map((opt) => (
                            <option key={opt.value} value={opt.value}>
                              {opt.label}
                            </option>
                          ))}
                        </select>
                      </label>
                    </div>
                  </div>
                )}

                {saveMode.isError && (
                  <p className="mm-status-text--failed text-sm" role="alert">
                    {saveMode.error instanceof Error
                      ? saveMode.error.message
                      : "Could not save update settings."}
                  </p>
                )}
                {saveMsg && !saveMode.isError && (
                  <p className="mm-status-text--healthy mt-3 text-sm">
                    {saveMsg}
                  </p>
                )}

                <div className={`mt-5 ${quietActionRowClass}`}>
                  <button
                    type="button"
                    className={mmActionButtonClass({
                      variant: "primary",
                      disabled:
                        !settingsDirty ||
                        saveMode.isPending ||
                        updateSettingsQ.isPending,
                    })}
                    disabled={
                      !settingsDirty ||
                      saveMode.isPending ||
                      updateSettingsQ.isPending
                    }
                    onClick={() => void handleSaveMode()}
                  >
                    {saveMode.isPending ? "Saving..." : "Save"}
                  </button>
                  {settingsDirty && (
                    <button
                      type="button"
                      className={mmActionButtonClass({
                        variant: "secondary",
                        disabled: saveMode.isPending,
                      })}
                      disabled={saveMode.isPending}
                      onClick={() => {
                        setModeDraft(serverMode);
                        setCheckOnStartupDraft(serverCheckOnStartup);
                        setCheckIntervalDraft(serverCheckInterval);
                        setSaveMsg(null);
                        saveMode.reset();
                      }}
                    >
                      Discard
                    </button>
                  )}
                </div>
              </SettingsQuietSection>
            ) : updateStatusQ.data.install_type === "docker" &&
              updateStatusQ.data.docker_update_command ? (
              <SettingsQuietSection
                headingId="suite-settings-upgrade-docker-heading"
                heading="What happens next"
              >
                <p className="rounded-lg border border-[var(--mm-border)] px-3 py-2 font-mono text-xs text-[var(--mm-text3)]">
                  {updateStatusQ.data.docker_update_command}
                </p>
                <p className="mm-quiet-note mt-2">
                  Keep the same WEIR_HOME volume and WEIR_SESSION_SECRET value
                  across upgrades so browser sessions and setup state continue
                  cleanly.
                </p>
              </SettingsQuietSection>
            ) : null}
          </>
        )}
      </div>
    </div>
  );
}
