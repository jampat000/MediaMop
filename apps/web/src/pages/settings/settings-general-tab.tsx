import { useNavigate } from "react-router-dom";
import type { SuiteSettingsOut } from "../../lib/suite/types";
import type { useSuiteOperationalHistoryResetMutation, useSuiteSettingsSaveMutation } from "../../lib/suite/queries";
import { curatedTimezoneOptionsSorted } from "../../lib/suite/timezone-options";
import { MmListboxPicker } from "../../components/ui/mm-listbox-picker";
import { mmActionButtonClass, mmEditableTextFieldClass } from "../../lib/ui/mm-control-roles";
import {
  mmModuleTabBlurbBandClass,
  mmModuleTabBlurbTextClass,
} from "../../lib/ui/mm-module-tab-blurb";
import { persistDisplayDensity, type DisplayDensity } from "../../lib/ui/display-density";
import { SUITE_SETTINGS_DASH_CARD_CLASS } from "./settings-shared";

type SettingsGeneralTabProps = {
  editable: boolean;
  settingsData: SuiteSettingsOut;
  save: ReturnType<typeof useSuiteSettingsSaveMutation>;
  appTimezone: string | null;
  setAppTimezone: (v: string) => void;
  timezoneDirty: boolean;
  setLogRetentionDaysDraft: (v: string | null) => void;
  normalizedLogRetentionDraft: string;
  finalizeLogRetentionDays: () => number;
  logsDirty: boolean;
  lastSuiteSaveTarget: "timezone" | "logs" | "backup" | null;
  displayDensity: DisplayDensity;
  setDisplayDensity: (v: DisplayDensity) => void;
  resetHistoryConfirm: string;
  setResetHistoryConfirm: (v: string) => void;
  resetHistory: ReturnType<typeof useSuiteOperationalHistoryResetMutation>;
  resetHistoryMsg: string | null;
  onSaveTimezone: () => void;
  onSaveLogs: () => void;
  onResetOperationalHistory: () => void;
};

export function SettingsGeneralTab({
  editable,
  settingsData,
  save,
  appTimezone,
  setAppTimezone,
  timezoneDirty,
  setLogRetentionDaysDraft,
  normalizedLogRetentionDraft,
  finalizeLogRetentionDays,
  logsDirty,
  lastSuiteSaveTarget,
  displayDensity,
  setDisplayDensity,
  resetHistoryConfirm,
  setResetHistoryConfirm,
  resetHistory,
  resetHistoryMsg,
  onSaveTimezone,
  onSaveLogs,
  onResetOperationalHistory,
}: SettingsGeneralTabProps) {
  const navigate = useNavigate();
  const timezoneOptions = curatedTimezoneOptionsSorted();

  return (
    <div data-testid="suite-settings-global" className="mm-bubble-stack">
      {!editable ? (
        <p className="text-sm text-[var(--mm-text3)]">
          Operators and admins can edit General options; everyone can open
          the Logs tab to read recent events.
        </p>
      ) : null}

      <div className="grid grid-cols-1 gap-5">
        <div className={mmModuleTabBlurbBandClass}>
          <p className={mmModuleTabBlurbTextClass}>
            Suite-wide choices saved in the app database. Integration
            details for Refiner, Pruner, and Subber stay on those module
            pages.
          </p>
        </div>
        <div className="grid grid-cols-1 gap-5 xl:grid-cols-2">
          <section
            className={SUITE_SETTINGS_DASH_CARD_CLASS}
            aria-labelledby="suite-settings-wizard-heading"
          >
            <div className="mm-card-action-body">
              <div>
                <h3
                  id="suite-settings-wizard-heading"
                  className="text-base font-semibold text-[var(--mm-text1)]"
                >
                  Setup wizard
                </h3>
                <p className="mt-1 text-sm text-[var(--mm-text2)]">
                  Reopen the first-run wizard to adjust the basic suite
                  setup flow at any time.
                </p>
              </div>
              <div className="space-y-2 text-sm text-[var(--mm-text2)]">
                <p>
                  Current state:{" "}
                  <span className="font-medium capitalize text-[var(--mm-text1)]">
                    {settingsData.setup_wizard_state || "pending"}
                  </span>
                </p>
                <p>
                  Use this when you want the guided setup again without
                  exposing it in the sidebar.
                </p>
              </div>
            </div>
            <div className="mm-card-action-footer">
              <button
                type="button"
                className={mmActionButtonClass({
                  variant: "secondary",
                  disabled: false,
                })}
                data-testid="suite-settings-open-setup-wizard"
                onClick={() => navigate("/setup-wizard")}
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
                <h3
                  id="suite-settings-timezone-heading"
                  className="text-base font-semibold text-[var(--mm-text1)]"
                >
                  Timezone
                </h3>
                <p className="mt-1 text-sm text-[var(--mm-text2)]">
                  Main-country timezones for suite-level time displays.
                  Use Save timezone when you change the selection.
                </p>
              </div>
              <MmListboxPicker
                ariaLabelledBy="suite-settings-timezone-heading"
                ariaDescribedBy="suite-timezone-hint"
                placeholder="Select timezone"
                disabled={!editable || save.isPending}
                options={timezoneOptions.map((tz) => ({
                  value: tz.id,
                  label: tz.label,
                }))}
                value={appTimezone ?? ""}
                onChange={(v) => setAppTimezone(v)}
              />
              <p
                id="suite-timezone-hint"
                className="text-xs text-[var(--mm-text3)]"
              >
                If you do not see your zone, pick the closest match - this
                only affects how times are labeled in the suite.
              </p>
              {save.isError && lastSuiteSaveTarget === "timezone" ? (
                <p
                  className="text-sm text-red-300"
                  role="alert"
                  data-testid="suite-settings-timezone-save-error"
                >
                  {save.error instanceof Error
                    ? save.error.message
                    : "Could not save."}
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
                onClick={() => onSaveTimezone()}
              >
                {save.isPending ? "Saving..." : "Save timezone"}
              </button>
            </div>
          </section>
        </div>

        <div className="grid grid-cols-1 gap-5 xl:grid-cols-3">
          <section
            className={SUITE_SETTINGS_DASH_CARD_CLASS}
            aria-labelledby="suite-settings-log-retention-heading"
          >
            <div className="mm-card-action-body">
              <div>
                <h3
                  id="suite-settings-log-retention-heading"
                  className="text-base font-semibold text-[var(--mm-text1)]"
                >
                  Log retention
                </h3>
                <p className="mt-1 text-sm text-[var(--mm-text2)]">
                  Decide how long MediaMop keeps persisted system log
                  entries on disk.
                </p>
              </div>
              <label className="block max-w-md">
                <span className="text-xs font-semibold uppercase tracking-wide text-[var(--mm-text3)]">
                  System log retention (days)
                </span>
                <input
                  type="number"
                  min={1}
                  max={3650}
                  className={`${mmEditableTextFieldClass} mt-1`}
                  value={normalizedLogRetentionDraft}
                  disabled={!editable || save.isPending}
                  onFocus={() =>
                    setLogRetentionDaysDraft(
                      String(settingsData.log_retention_days),
                    )
                  }
                  onChange={(e) => setLogRetentionDaysDraft(e.target.value)}
                  onBlur={() =>
                    setLogRetentionDaysDraft(
                      String(finalizeLogRetentionDays()),
                    )
                  }
                  aria-describedby="suite-general-log-retention-hint"
                />
                <p
                  id="suite-general-log-retention-hint"
                  className="mt-1 text-xs text-[var(--mm-text3)]"
                >
                  Between 1 and 3650 days. Older system log entries are
                  removed automatically while MediaMop is running;
                  activity history is kept until you reset it.
                </p>
              </label>
              {save.isError && lastSuiteSaveTarget === "logs" ? (
                <p
                  className="text-sm text-red-300"
                  role="alert"
                  data-testid="suite-settings-logs-save-error"
                >
                  {save.error instanceof Error
                    ? save.error.message
                    : "Could not save."}
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
                onClick={() => onSaveLogs()}
              >
                {save.isPending ? "Saving..." : "Save log retention"}
              </button>
            </div>
          </section>
          {editable ? (
            <section
              className={SUITE_SETTINGS_DASH_CARD_CLASS}
              data-testid="suite-settings-history-reset"
              aria-labelledby="suite-settings-history-reset-heading"
            >
              <div className="mm-card-action-body">
                <div>
                  <h3
                    id="suite-settings-history-reset-heading"
                    className="text-base font-semibold text-[var(--mm-text1)]"
                  >
                    Dashboard and activity history
                  </h3>
                  <p className="mt-1 text-sm leading-6 text-[var(--mm-text2)]">
                    History is kept until you reset it. Sign-outs, expired
                    sessions, and log retention do not clear this data.
                  </p>
                </div>
                <label className="block text-sm text-[var(--mm-text2)]">
                  <span className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-[var(--mm-text3)]">
                    Type RESET to confirm
                  </span>
                  <input
                    type="text"
                    className="mm-input w-full"
                    value={resetHistoryConfirm}
                    disabled={resetHistory.isPending}
                    onChange={(e) => setResetHistoryConfirm(e.target.value)}
                  />
                  <p className="mt-1 text-xs leading-relaxed text-[var(--mm-text3)]">
                    Clears Activity entries and finished job history only.
                  </p>
                </label>
                {resetHistoryMsg ? (
                  <p className="rounded-md border border-emerald-500/30 bg-emerald-950/20 px-3 py-2 text-sm text-emerald-200">
                    {resetHistoryMsg}
                  </p>
                ) : null}
                {resetHistory.isError ? (
                  <p
                    className="rounded-md border border-red-500/40 bg-red-950/25 px-3 py-2 text-sm text-red-200"
                    role="alert"
                  >
                    {resetHistory.error instanceof Error
                      ? resetHistory.error.message
                      : "Could not reset dashboard and activity history."}
                  </p>
                ) : null}
              </div>
              <div className="mm-card-action-footer">
                <button
                  type="button"
                  className={mmActionButtonClass({
                    variant: "tertiary",
                    disabled:
                      resetHistory.isPending ||
                      resetHistoryConfirm.trim().toUpperCase() !== "RESET",
                  })}
                  disabled={
                    resetHistory.isPending ||
                    resetHistoryConfirm.trim().toUpperCase() !== "RESET"
                  }
                  onClick={() => onResetOperationalHistory()}
                >
                  {resetHistory.isPending ? "Resetting..." : "Reset history"}
                </button>
              </div>
            </section>
          ) : null}
          <section
            className={SUITE_SETTINGS_DASH_CARD_CLASS}
            aria-labelledby="suite-settings-density-heading"
          >
            <fieldset className="min-w-0 border-0 p-0">
              <legend
                id="suite-settings-density-heading"
                className="text-base font-semibold text-[var(--mm-text1)]"
              >
                Display density (this browser)
              </legend>
              <p className="mt-1 text-sm text-[var(--mm-text2)]">
                Adjust text, spacing, sidebar width, and card density for
                this browser. The change applies immediately.
              </p>
              <div
                className="mt-3 flex flex-col gap-2"
                data-testid="suite-settings-display-density"
                role="radiogroup"
                aria-label="Display density"
              >
                {(
                  [
                    {
                      id: "compact" as const,
                      label: "Compact",
                      hint: "Smaller, tighter app layout",
                    },
                    {
                      id: "default" as const,
                      label: "Balanced",
                      hint: "Readable default",
                    },
                    {
                      id: "comfortable" as const,
                      label: "Comfortable",
                      hint: "Larger text and controls",
                    },
                    {
                      id: "expanded" as const,
                      label: "Expanded",
                      hint: "Big-screen reading mode",
                    },
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
                    <span className="text-xs text-[var(--mm-text3)]">
                      ({hint})
                    </span>
                  </label>
                ))}
              </div>
            </fieldset>
          </section>
        </div>
      </div>
    </div>
  );
}
