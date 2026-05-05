import { MmOnOffSwitch } from "../../components/ui/mm-on-off-switch";
import {
  MM_SCHEDULE_TIME_WINDOW_HELPER,
  MmScheduleDayChips,
  MmScheduleTimeFields,
} from "../../components/ui/mm-schedule-window-controls";
import {
  committedPrunerRunIntervalMinutes,
  PRUNER_RUN_INTERVAL_MAX_MINUTES,
  PRUNER_RUN_INTERVAL_MIN_MINUTES,
} from "../../lib/ui/pruner-schedule-interval";
import { mmActionButtonClass } from "../../lib/ui/mm-control-roles";
import type { PrunerScopeSummary } from "../../lib/pruner/api";

type PrunerScopeScheduleCardProps = {
  instanceId: number;
  scope: "tv" | "movies";
  showInteractiveControls: boolean;
  busy: boolean;
  scopeRow: PrunerScopeSummary | undefined;
  schedEnabled: boolean;
  setSchedEnabled: (value: boolean) => void;
  schedIntervalSec: number;
  schedIntervalMinDraft: string | null;
  setSchedIntervalMinDraft: (value: string | null) => void;
  schedHoursLimited: boolean;
  setSchedHoursLimited: (value: boolean) => void;
  schedDays: string;
  setSchedDays: (value: string) => void;
  schedStart: string;
  setSchedStart: (value: string) => void;
  schedEnd: string;
  setSchedEnd: (value: string) => void;
  fmt: (value: string | null | undefined) => string;
  schedMsg: string | null;
  saveSchedule: () => Promise<void>;
};

export function PrunerScopeScheduleCard({
  instanceId,
  scope,
  showInteractiveControls,
  busy,
  scopeRow,
  schedEnabled,
  setSchedEnabled,
  schedIntervalSec,
  schedIntervalMinDraft,
  setSchedIntervalMinDraft,
  schedHoursLimited,
  setSchedHoursLimited,
  schedDays,
  setSchedDays,
  schedStart,
  setSchedStart,
  schedEnd,
  setSchedEnd,
  fmt,
  schedMsg,
  saveSchedule,
}: PrunerScopeScheduleCardProps) {
  return (
    <div
      className="mm-card mm-dash-card flex min-h-0 flex-col p-6"
      data-testid="pruner-scope-scheduled-preview"
    >
      <div className="mm-card-action-body flex-1 min-h-0">
        <div>
          <h3 className="text-base font-semibold text-[var(--mm-text1)]">
            Automatic scans ({scope === "tv" ? "TV shows" : "Movies"})
          </h3>
          <p className="mt-1 text-sm text-[var(--mm-text2)]">
            The schedule runs your saved criteria automatically and records a
            review snapshot. Deleting only happens when automatic apply is
            enabled for this library and uses that saved snapshot.
          </p>
        </div>
        {showInteractiveControls ? (
          <>
            <MmOnOffSwitch
              id={`pruner-scope-${instanceId}-${scope}-timed`}
              label="Enable timed scans"
              enabled={schedEnabled}
              disabled={busy}
              onChange={setSchedEnabled}
            />
            <div>
              <span className="text-sm font-medium text-[var(--mm-text1)]">
                Run interval (minutes)
              </span>
              <p className="mt-1 text-xs text-[var(--mm-text3)]">
                How often this search runs automatically.
              </p>
              <input
                type="number"
                min={PRUNER_RUN_INTERVAL_MIN_MINUTES}
                max={PRUNER_RUN_INTERVAL_MAX_MINUTES}
                className="mm-input mt-2 w-full"
                value={
                  schedIntervalMinDraft !== null
                    ? schedIntervalMinDraft
                    : committedPrunerRunIntervalMinutes(schedIntervalSec)
                }
                onFocus={() =>
                  setSchedIntervalMinDraft(
                    committedPrunerRunIntervalMinutes(schedIntervalSec),
                  )
                }
                onChange={(e) => setSchedIntervalMinDraft(e.target.value)}
                onBlur={() => setSchedIntervalMinDraft(null)}
                disabled={busy}
                aria-label="Run interval in minutes"
              />
            </div>
            <div className="space-y-3">
              <div>
                <span className="text-sm font-medium text-[var(--mm-text1)]">
                  Schedule window
                </span>
                <p className="mt-1 text-xs text-[var(--mm-text3)]">
                  {MM_SCHEDULE_TIME_WINDOW_HELPER}
                </p>
              </div>
              <div className="space-y-4">
                <MmOnOffSwitch
                  id={`pruner-scope-${instanceId}-${scope}-hours`}
                  label="Limit to these hours"
                  enabled={schedHoursLimited}
                  disabled={busy}
                  onChange={setSchedHoursLimited}
                />
                <div className="space-y-2">
                  <span className="text-sm font-medium text-[var(--mm-text1)]">
                    Days
                  </span>
                  <MmScheduleDayChips
                    scheduleDaysCsv={schedDays}
                    disabled={busy}
                    onChangeCsv={setSchedDays}
                  />
                </div>
                <MmScheduleTimeFields
                  idPrefix={`pruner-scope-${instanceId}-${scope}`}
                  start={schedStart}
                  end={schedEnd}
                  disabled={busy}
                  onStart={setSchedStart}
                  onEnd={setSchedEnd}
                />
              </div>
            </div>
          </>
        ) : (
          <p className="text-sm text-[var(--mm-text2)]">
            Timed scans are{" "}
            <strong>{scopeRow?.scheduled_preview_enabled ? "on" : "off"}</strong>
            {scopeRow ? (
              <>
                {" "}
                (every {Math.round(scopeRow.scheduled_preview_interval_seconds / 60)}{" "}
                minutes). Sign in as an operator to change it.
              </>
            ) : null}
          </p>
        )}
        <p className="text-xs text-[var(--mm-text3)]">
          Last automatic scan:{" "}
          <span className="font-medium text-[var(--mm-text1)]">
            {scopeRow?.last_scheduled_preview_enqueued_at
              ? fmt(scopeRow.last_scheduled_preview_enqueued_at)
              : "Never run"}
          </span>
        </p>
      </div>
      {showInteractiveControls ? (
        <div className="mm-card-action-footer">
          <button
            type="button"
            className={`${mmActionButtonClass({ variant: "primary", disabled: busy })} w-full`}
            disabled={busy}
            onClick={() => void saveSchedule()}
          >
            {scope === "tv" ? "Save TV schedule window" : "Save Movies schedule window"}
          </button>
          {schedMsg ? <p className="text-xs text-green-600">{schedMsg}</p> : null}
        </div>
      ) : null}
    </div>
  );
}
