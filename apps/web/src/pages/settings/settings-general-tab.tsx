import { useNavigate } from "react-router-dom";
import type { SuiteSettingsOut } from "../../lib/suite/types";
import type {
  useSuiteOperationalHistoryResetMutation,
  useSuiteSettingsSaveMutation,
} from "../../lib/suite/queries";
import { curatedTimezoneOptionsSorted } from "../../lib/suite/timezone-options";
import { MmListboxPicker } from "../../components/ui/mm-listbox-picker";
import { quietActionRowClass } from "../../components/shared/quiet-section";
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
import { SettingsQuietSection } from "./settings-shared";

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

/** The field caption, spelled exactly as the deleted `.mm-settings-field-label` rule
 *  spelled it, so losing the cards does not quietly restyle the confirmation field
 *  that guards Clear Activity history. */
const FIELD_LABEL_CLASS =
  "text-[length:var(--mm-type-caption)] font-semibold text-[var(--mm-text2)]";

/** The hint under a field. Same tokens the deleted `.mm-settings-card__hint` used. */
const FIELD_HINT_CLASS =
  "text-[length:var(--mm-type-caption)] leading-[1.45] text-[var(--mm-text3)]";

/**
 * A form on a page with no cards still has to say where it starts and stops, because
 * each of these Saves writes a different thing. Without a box, that is the section's
 * own hairline above it and the `.mm-quiet-stack`'s 2.5rem below it: a single column
 * of full-width groups, each closed by its own action row.
 *
 * The two-column grid this replaces could not be made to line up — five groups of
 * genuinely different heights always left a ragged bottom edge and an orphan in the
 * last row — and a settings form gains nothing from a second column anyway.
 */
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
    <div data-testid="suite-settings-global" className="mm-quiet-stack">
      {!editable ? (
        <p className="mm-quiet-note">
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

      <SettingsQuietSection
        headingId="suite-settings-timezone-heading"
        heading="Time zone"
      >
        <p className="mm-quiet-note">
          Times across Weir, and schedule windows, use this zone.
        </p>
        <div className="mt-4 max-w-md min-w-0">
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
          <p
            id="suite-timezone-hint"
            className={`mt-2 block ${FIELD_HINT_CLASS}`}
          >
            Not listed? Pick a city in the same zone; it only changes how times
            are shown.
          </p>
        </div>
        {save.isError && lastSuiteSaveTarget === "timezone" ? (
          <p
            className="mt-4 text-sm text-[var(--mm-status-failed-text)]"
            role="alert"
            data-testid="suite-settings-timezone-save-error"
          >
            {save.error instanceof Error
              ? save.error.message
              : "Could not save."}
          </p>
        ) : null}
        <div className={`${quietActionRowClass} mt-6`}>
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
      </SettingsQuietSection>

      <SettingsQuietSection
        headingId="suite-settings-density-heading"
        heading="Display density"
      >
        <p className="mm-quiet-note">
          Text size and spacing for this browser only. Applies straight away.
        </p>
        {/* The tiles keep their own border: it is the radio's target and its
            selected-state affordance, not a panel around content — the same call the
            setup wizard's conversion made, and `.mm-density-option` is shared with it.
            What rule 3 rejected here was the card around them, and that has gone. */}
        <div
          className="mm-density-options max-w-2xl"
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
      </SettingsQuietSection>

      <SettingsQuietSection
        headingId="suite-settings-log-retention-heading"
        heading="Log and history retention"
      >
        <p className="mm-quiet-note">
          How long Weir keeps its system log and how far back Activity goes.
        </p>
        <div className="mt-4 grid max-w-2xl gap-5 sm:grid-cols-2">
          <label className="block min-w-0">
            <span className={FIELD_LABEL_CLASS}>
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
              className={`mt-1 block ${FIELD_HINT_CLASS}`}
            >
              1 to 3650 days. Older entries are removed while Weir runs.
            </span>
          </label>
          {settingsData.activity_retention_days !== undefined ? (
            <label className="block min-w-0" id="activity-retention">
              <span className={FIELD_LABEL_CLASS}>
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
                onChange={(e) => setActivityRetentionDaysDraft(e.target.value)}
                onBlur={() =>
                  setActivityRetentionDaysDraft(
                    String(finalizeActivityRetentionDays() ?? ""),
                  )
                }
                aria-describedby="suite-general-activity-retention-hint"
              />
              <span
                id="suite-general-activity-retention-hint"
                className={`mt-1 block ${FIELD_HINT_CLASS}`}
              >
                0 keeps it until you clear it. Media files are never touched.
              </span>
            </label>
          ) : null}
        </div>
        {save.isError && lastSuiteSaveTarget === "logs" ? (
          <p
            className="mt-4 text-sm text-[var(--mm-status-failed-text)]"
            role="alert"
            data-testid="suite-settings-logs-save-error"
          >
            {save.error instanceof Error
              ? save.error.message
              : "Could not save."}
          </p>
        ) : null}
        <div className={`${quietActionRowClass} mt-6`}>
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
      </SettingsQuietSection>

      {editable ? (
        <SettingsQuietSection
          headingId="suite-settings-history-reset-heading"
          heading="Clear Activity history"
          id="history-reset"
          data-testid="suite-settings-history-reset"
        >
          <p className="mm-quiet-note">
            Removes every Activity entry and finished job record now. Media
            files are not touched. Signing out does not clear history.
          </p>
          <label className="mt-4 block max-w-md min-w-0">
            <span className={FIELD_LABEL_CLASS}>Type RESET to confirm</span>
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
              className="mt-4 max-w-md rounded-md border border-[var(--mm-border)] bg-[var(--mm-status-healthy-bg)] px-3 py-2 text-sm text-[var(--mm-status-healthy-text)]"
              role="status"
            >
              {resetHistoryMsg}
            </p>
          ) : null}
          {resetHistory.isError ? (
            <p
              className="mt-4 max-w-md rounded-md border border-[var(--mm-border)] bg-[var(--mm-status-failed-bg)] px-3 py-2 text-sm text-[var(--mm-status-failed-text)]"
              role="alert"
            >
              {resetHistory.error instanceof Error
                ? resetHistory.error.message
                : "Could not reset activity history."}
            </p>
          ) : null}
          <div className={`${quietActionRowClass} mt-6`}>
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
        </SettingsQuietSection>
      ) : null}

      <SettingsQuietSection
        headingId="suite-settings-wizard-heading"
        heading="Setup wizard"
      >
        <p className="mm-quiet-note">
          Go through the first-run steps again: time zone, display, backups and
          library folders. You can leave at any point.
        </p>
        <p className={`mt-3 block ${FIELD_HINT_CLASS}`}>
          {wizardState === "completed"
            ? "You finished the wizard."
            : wizardState === "skipped"
              ? "You skipped the wizard."
              : "The wizard has not been finished yet."}
        </p>
        <div className={`${quietActionRowClass} mt-6`}>
          <button
            type="button"
            className={mmActionButtonClass({ variant: "secondary" })}
            data-testid="suite-settings-open-setup-wizard"
            onClick={() => navigate("/setup-wizard")}
          >
            Open setup wizard
          </button>
        </div>
      </SettingsQuietSection>
    </div>
  );
}
