import { useNavigate } from "react-router-dom";
import type { SuiteSettingsOut } from "../../lib/suite/types";
import type {
  useSuiteOperationalHistoryResetMutation,
  useSuiteSettingsSaveMutation,
} from "../../lib/suite/queries";
import { curatedTimezoneOptionsSorted } from "../../lib/suite/timezone-options";
import { MmListboxPicker } from "../../components/ui/mm-listbox-picker";
import {
  mmActionButtonClass,
  mmEditableTextFieldClass,
} from "../../lib/ui/mm-control-roles";
import {
  mmModuleTabBlurbBandClass,
  mmModuleTabBlurbTextClass,
} from "../../lib/ui/mm-module-tab-blurb";
import {
  persistDisplayDensity,
  type DisplayDensity,
} from "../../lib/ui/display-density";
import { SUITE_SETTINGS_DASH_CARD_CLASS } from "./settings-shared";

const DENSITY_OPTIONS: ReadonlyArray<{
  id: DisplayDensity;
  label: string;
  hint: string;
}> = [
  { id: "compact", label: "Compact", hint: "Tighter, fits more" },
  { id: "default", label: "Balanced", hint: "The default" },
  { id: "comfortable", label: "Comfortable", hint: "Larger text" },
  { id: "expanded", label: "Expanded", hint: "For big screens" },
];

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
  normalizedActivityRetentionDraft: string;
  setActivityRetentionDaysDraft: (v: string | null) => void;
  finalizeActivityRetentionDays: () => number | undefined;
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
  normalizedActivityRetentionDraft,
  setActivityRetentionDaysDraft,
  finalizeActivityRetentionDays,
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
  const wizardState = (settingsData.setup_wizard_state || "pending")
    .trim()
    .toLowerCase();

  return (
    <div data-testid="suite-settings-global" className="mm-bubble-stack">
      {!editable ? (
        <p className="text-sm text-[var(--mm-text3)]">
          Operators and admins can edit General options; everyone can open the
          Logs tab to read recent events.
        </p>
      ) : null}

      <div className={mmModuleTabBlurbBandClass}>
        <p className={mmModuleTabBlurbTextClass}>
          Time zone, how long history is kept, and how this browser displays
          Weir.
        </p>
      </div>

      <div className="mm-settings-grid">
        <section
          className={`${SUITE_SETTINGS_DASH_CARD_CLASS} mm-settings-card`}
          aria-labelledby="suite-settings-timezone-heading"
        >
          <div>
            <h3
              id="suite-settings-timezone-heading"
              className="mm-settings-card__title"
            >
              Time zone
            </h3>
            <p className="mm-settings-card__lead">
              Times across Weir, and schedule windows, use this zone.
            </p>
          </div>
          <MmListboxPicker
            ariaLabelledBy="suite-settings-timezone-heading"
            ariaDescribedBy="suite-timezone-hint"
            placeholder="Select time zone"
            disabled={!editable || save.isPending}
            options={timezoneOptions.map((tz) => ({
              value: tz.id,
              label: tz.label,
            }))}
            value={appTimezone ?? ""}
            onChange={(v) => setAppTimezone(v)}
          />
          <p id="suite-timezone-hint" className="mm-settings-card__hint">
            Not listed? Pick a city in the same zone; it only changes how times
            are shown.
          </p>
          {save.isError && lastSuiteSaveTarget === "timezone" ? (
            <p
              className="text-sm text-[var(--mm-status-failed-text)]"
              role="alert"
              data-testid="suite-settings-timezone-save-error"
            >
              {save.error instanceof Error
                ? save.error.message
                : "Could not save."}
            </p>
          ) : null}
          <div className="mm-settings-card__actions">
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
              {save.isPending ? "Saving..." : "Save time zone"}
            </button>
          </div>
        </section>

        <section
          className={`${SUITE_SETTINGS_DASH_CARD_CLASS} mm-settings-card`}
          aria-labelledby="suite-settings-density-heading"
        >
          <fieldset className="min-w-0 border-0 p-0">
            <legend
              id="suite-settings-density-heading"
              className="mm-settings-card__title"
            >
              Display density
            </legend>
            <p className="mm-settings-card__lead">
              Text size and spacing for this browser only. Applies straight
              away.
            </p>
            <div
              className="mm-density-options"
              data-testid="suite-settings-display-density"
              role="radiogroup"
              aria-label="Display density"
            >
              {DENSITY_OPTIONS.map(({ id, label, hint }) => (
                <label
                  key={id}
                  className={`mm-density-option${displayDensity === id ? " mm-density-option--selected" : ""}`}
                >
                  <input
                    type="radio"
                    name="mm-display-density"
                    className="mm-density-option__input"
                    checked={displayDensity === id}
                    onChange={() => {
                      setDisplayDensity(id);
                      persistDisplayDensity(id);
                    }}
                  />
                  <span className="min-w-0">
                    <span className="mm-density-option__label">{label}</span>
                    <span className="mm-density-option__hint">{hint}</span>
                  </span>
                </label>
              ))}
            </div>
          </fieldset>
        </section>

        <section
          className={`${SUITE_SETTINGS_DASH_CARD_CLASS} mm-settings-card`}
          aria-labelledby="suite-settings-log-retention-heading"
        >
          <div>
            <h3
              id="suite-settings-log-retention-heading"
              className="mm-settings-card__title"
            >
              Log and history retention
            </h3>
            <p className="mm-settings-card__lead">
              How long Weir keeps its system log and how far back Activity goes.
            </p>
          </div>
          <div className="mm-settings-fields">
            <label className="block">
              <span className="mm-settings-field-label">
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
                  setLogRetentionDaysDraft(String(finalizeLogRetentionDays()))
                }
                aria-describedby="suite-general-log-retention-hint"
              />
              <span
                id="suite-general-log-retention-hint"
                className="mm-settings-card__hint mt-1 block"
              >
                1 to 3650 days. Older entries are removed while Weir runs.
              </span>
            </label>
            {settingsData.activity_retention_days !== undefined ? (
              <label className="block" id="activity-retention">
                <span className="mm-settings-field-label">
                  Keep Activity history for (days)
                </span>
                <input
                  type="number"
                  min={0}
                  max={3650}
                  className={`${mmEditableTextFieldClass} mt-1`}
                  value={normalizedActivityRetentionDraft}
                  disabled={!editable || save.isPending}
                  data-testid="suite-settings-activity-retention"
                  onChange={(e) =>
                    setActivityRetentionDaysDraft(e.target.value)
                  }
                  onBlur={() =>
                    setActivityRetentionDaysDraft(
                      String(finalizeActivityRetentionDays() ?? ""),
                    )
                  }
                  aria-describedby="suite-general-activity-retention-hint"
                />
                <span
                  id="suite-general-activity-retention-hint"
                  className="mm-settings-card__hint mt-1 block"
                >
                  0 keeps it until you clear it. Media files are never touched.
                </span>
              </label>
            ) : null}
          </div>
          {save.isError && lastSuiteSaveTarget === "logs" ? (
            <p
              className="text-sm text-[var(--mm-status-failed-text)]"
              role="alert"
              data-testid="suite-settings-logs-save-error"
            >
              {save.error instanceof Error
                ? save.error.message
                : "Could not save."}
            </p>
          ) : null}
          <div className="mm-settings-card__actions">
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
              {save.isPending ? "Saving..." : "Save retention"}
            </button>
          </div>
        </section>

        {editable ? (
          <section
            className={`${SUITE_SETTINGS_DASH_CARD_CLASS} mm-settings-card`}
            data-testid="suite-settings-history-reset"
            id="history-reset"
            aria-labelledby="suite-settings-history-reset-heading"
          >
            <div>
              <h3
                id="suite-settings-history-reset-heading"
                className="mm-settings-card__title"
              >
                Clear Activity history
              </h3>
              <p className="mm-settings-card__lead">
                Removes every Activity entry and finished job record now. Media
                files are not touched. Signing out does not clear history.
              </p>
            </div>
            <label className="block">
              <span className="mm-settings-field-label">
                Type RESET to confirm
              </span>
              <input
                type="text"
                className="mm-input mt-1 w-full"
                value={resetHistoryConfirm}
                disabled={resetHistory.isPending}
                autoComplete="off"
                onChange={(e) => setResetHistoryConfirm(e.target.value)}
              />
            </label>
            {resetHistoryMsg ? (
              <p
                className="rounded-md border border-[var(--mm-border)] bg-[var(--mm-status-healthy-bg)] px-3 py-2 text-sm text-[var(--mm-status-healthy-text)]"
                role="status"
              >
                {resetHistoryMsg}
              </p>
            ) : null}
            {resetHistory.isError ? (
              <p
                className="rounded-md border border-[var(--mm-border)] bg-[var(--mm-status-failed-bg)] px-3 py-2 text-sm text-[var(--mm-status-failed-text)]"
                role="alert"
              >
                {resetHistory.error instanceof Error
                  ? resetHistory.error.message
                  : "Could not reset activity history."}
              </p>
            ) : null}
            <div className="mm-settings-card__actions">
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
          className={`${SUITE_SETTINGS_DASH_CARD_CLASS} mm-settings-card`}
          aria-labelledby="suite-settings-wizard-heading"
        >
          <div>
            <h3
              id="suite-settings-wizard-heading"
              className="mm-settings-card__title"
            >
              Setup wizard
            </h3>
            <p className="mm-settings-card__lead">
              Go through the first-run steps again: time zone, display, backups
              and library folders. You can leave at any point.
            </p>
          </div>
          <p className="mm-settings-card__hint">
            {wizardState === "completed"
              ? "You finished the wizard."
              : wizardState === "skipped"
                ? "You skipped the wizard."
                : "The wizard has not been finished yet."}
          </p>
          <div className="mm-settings-card__actions">
            <button
              type="button"
              className={mmActionButtonClass({ variant: "secondary" })}
              data-testid="suite-settings-open-setup-wizard"
              onClick={() => navigate("/setup-wizard")}
            >
              Open setup wizard
            </button>
          </div>
        </section>
      </div>
    </div>
  );
}
