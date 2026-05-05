import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { MmOnOffSwitch } from "../../components/ui/mm-on-off-switch";
import {
  MM_SCHEDULE_TIME_WINDOW_HELPER,
  MmScheduleDayChips,
  MmScheduleTimeFields,
} from "../../components/ui/mm-schedule-window-controls";
import { mmActionButtonClass } from "../../lib/ui/mm-control-roles";
import { fetchCsrfToken } from "../../lib/api/auth-api";
import { useMeQuery } from "../../lib/auth/queries";
import type { PrunerServerInstance } from "../../lib/pruner/api";
import { patchPrunerScope } from "../../lib/pruner/api";
import { formatPrunerDateTime } from "./pruner-ui-utils";
import { PrunerDryRunControls } from "./pruner-provider-operator-workspace";
import type { ProviderTab } from "./pruner-page-types";
import { providerDisabledInstance } from "./pruner-page-utils";

type PrunerGlobalScheduleRowProps = {
  provider: ProviderTab;
  scope: "tv" | "movies";
  instance: PrunerServerInstance | undefined;
  ensureScopeSaved: () => Promise<void>;
};

export function PrunerGlobalScheduleRow({
  provider,
  scope,
  instance,
  ensureScopeSaved,
}: PrunerGlobalScheduleRowProps) {
  const qc = useQueryClient();
  const me = useMeQuery();
  const canOperate = me.data?.role === "admin" || me.data?.role === "operator";
  /** Draft UI uses defaults when no server exists yet; persist only once a real instance id is available. */
  const displayInstance = instance ?? providerDisabledInstance(provider);
  const scopeRow = displayInstance.scopes.find((s) => s.media_scope === scope);
  const persistable = Boolean(instance && instance.id > 0);
  const [schedHoursLimited, setSchedHoursLimited] = useState(false);
  const [schedDays, setSchedDays] = useState("");
  const [schedStart, setSchedStart] = useState("00:00");
  const [schedEnd, setSchedEnd] = useState("23:59");
  const [previewCap, setPreviewCap] = useState(500);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [dryRunEnabled, setDryRunEnabled] = useState(true);

  useEffect(() => {
    if (!scopeRow) {
      setSchedHoursLimited(false);
      setSchedDays("");
      setSchedStart("00:00");
      setSchedEnd("23:59");
      setPreviewCap(500);
      return;
    }
    setSchedHoursLimited(scopeRow.scheduled_preview_hours_limited ?? false);
    setSchedDays(scopeRow.scheduled_preview_days ?? "");
    setSchedStart(scopeRow.scheduled_preview_start ?? "00:00");
    setSchedEnd(scopeRow.scheduled_preview_end ?? "23:59");
    setPreviewCap(scopeRow.preview_max_items);
  }, [
    scopeRow?.scheduled_preview_hours_limited,
    scopeRow?.scheduled_preview_days,
    scopeRow?.scheduled_preview_start,
    scopeRow?.scheduled_preview_end,
    scopeRow?.preview_max_items,
    instance?.id,
  ]);

  const scheduleFieldsDirty =
    scopeRow != null &&
    (schedHoursLimited !== (scopeRow.scheduled_preview_hours_limited ?? false) ||
      schedDays !== (scopeRow.scheduled_preview_days ?? "") ||
      schedStart !== (scopeRow.scheduled_preview_start ?? "00:00") ||
      schedEnd !== (scopeRow.scheduled_preview_end ?? "23:59") ||
      previewCap !== scopeRow.preview_max_items);

  async function saveRow() {
    if (!scopeRow) return;
    if (!persistable) {
      setMsg(null);
      setErr(
        "Save a server on the Connection tab first, then you can save this schedule to that server.",
      );
      return;
    }
    setMsg(null);
    setErr(null);
    setBusy(true);
    try {
      const csrf_token = await fetchCsrfToken();
      const cap = Math.max(1, Math.min(5000, Number(previewCap) || 500));
      await patchPrunerScope(instance!.id, scope, {
        scheduled_preview_enabled: scopeRow.scheduled_preview_enabled,
        scheduled_preview_interval_seconds:
          scopeRow.scheduled_preview_interval_seconds,
        scheduled_preview_hours_limited: schedHoursLimited,
        scheduled_preview_days: schedDays,
        scheduled_preview_start: schedStart,
        scheduled_preview_end: schedEnd,
        preview_max_items: cap,
        csrf_token,
      });
      await qc.invalidateQueries({ queryKey: ["pruner", "instances"] });
      setMsg("Saved.");
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const controlsDisabled = !canOperate || busy;
  const saveDisabled = busy || !canOperate || !scopeRow || !scheduleFieldsDirty;
  const testId = `pruner-schedule-row-${provider}-${scope}`;
  const idPrefix = `pruner-sched-${provider}-${scope}`;

  const saveScheduleLabel =
    scope === "tv" ? "Save TV schedule" : "Save Movies schedule";

  const laneTitle =
    scope === "tv"
      ? "TV automatic scan window"
      : "Movies automatic scan window";
  const laneIntro =
    scope === "tv"
      ? "Limit which days and times Pruner may run scheduled TV cleanup previews for this provider."
      : "Limit which days and times Pruner may run scheduled Movies cleanup previews for this provider.";

  return (
    <section
      className="mm-card mm-dash-card flex h-full min-h-0 min-w-0 flex-col p-6"
      data-testid={testId}
    >
      <div className="mm-card-action-body flex-1 min-h-0">
        <div>
          <h3 className="text-base font-semibold text-[var(--mm-text1)]">
            {laneTitle}
          </h3>
          <p className="mt-1 text-sm text-[var(--mm-text2)]">{laneIntro}</p>
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
              id={`${idPrefix}-hours-limited`}
              label="Limit to these hours"
              enabled={schedHoursLimited}
              disabled={controlsDisabled}
              onChange={setSchedHoursLimited}
            />
            <div className="space-y-2">
              <span className="text-sm font-medium text-[var(--mm-text1)]">
                Days
              </span>
              <MmScheduleDayChips
                scheduleDaysCsv={schedDays}
                disabled={controlsDisabled}
                onChangeCsv={setSchedDays}
              />
            </div>
            <MmScheduleTimeFields
              idPrefix={idPrefix}
              start={schedStart}
              end={schedEnd}
              disabled={controlsDisabled}
              onStart={setSchedStart}
              onEnd={setSchedEnd}
            />
          </div>
        </div>
        <div>
          <span className="text-sm font-medium text-[var(--mm-text1)]">
            Items to scan per run
          </span>
          <p className="mt-1 text-xs text-[var(--mm-text3)]">
            How many items to check each time the scan runs. Higher numbers take
            longer. Maximum 5,000.
          </p>
          <input
            type="number"
            min={1}
            max={5000}
            className="mm-input mt-2 w-full"
            value={previewCap}
            disabled={controlsDisabled}
            onChange={(e) =>
              setPreviewCap(Math.max(1, Math.min(5000, Number(e.target.value) || 500)))
            }
            aria-label="Items to scan per run"
          />
        </div>
        <p className="text-xs text-[var(--mm-text3)]">
          Last automatic scan:{" "}
          <span className="font-medium text-[var(--mm-text1)]">
            {scopeRow?.last_scheduled_preview_enqueued_at
              ? formatPrunerDateTime(scopeRow.last_scheduled_preview_enqueued_at)
              : "Never run"}
          </span>
        </p>
        {!canOperate && msg ? <p className="text-xs text-green-600">{msg}</p> : null}
        {!canOperate && err ? (
          <p className="text-xs text-red-500" role="alert">
            {err}
          </p>
        ) : null}
      </div>
      {canOperate ? (
        <div className="mm-card-action-footer">
          <button
            type="button"
            className={`${mmActionButtonClass({ variant: "primary", disabled: saveDisabled })} w-full`}
            disabled={saveDisabled}
            onClick={() => void saveRow()}
          >
            {busy ? "Saving..." : saveScheduleLabel}
          </button>
          {msg ? <p className="text-xs text-green-600">{msg}</p> : null}
          {err ? (
            <p className="text-xs text-red-500" role="alert">
              {err}
            </p>
          ) : null}
        </div>
      ) : null}

      <div className="mt-4 border-t border-[var(--mm-border)] pt-6">
        <h4 className="text-base font-semibold text-[var(--mm-text1)]">Run now</h4>
        <p className="mt-1 text-xs text-[var(--mm-text3)]">
          Scan your saved cleanup criteria immediately without waiting for the
          schedule. This creates review snapshots; deletion still requires a
          saved snapshot confirmation.
        </p>
        <div className="mt-4">
          <PrunerDryRunControls
            instanceId={instance?.id ?? 0}
            mediaScope={scope}
            testIdPrefix={`pruner-schedule-${provider}`}
            ensureSaved={ensureScopeSaved}
            dryRunEnabled={dryRunEnabled}
            onDryRunEnabledChange={setDryRunEnabled}
            runDisabled={!instance || instance.id <= 0}
            controlsDisabled={!canOperate || busy}
          />
        </div>
      </div>
    </section>
  );
}
