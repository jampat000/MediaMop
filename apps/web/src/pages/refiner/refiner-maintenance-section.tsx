import { useState } from "react";

import { useMeQuery } from "../../lib/auth/queries";
import type {
  MaintenanceFamily,
  MaintenanceFamilyState,
} from "../../lib/refiner/maintenance-api";
import {
  useRefinerMaintenanceQuery,
  useRefinerRuntimeSettingsQuery,
  useRunRefinerMaintenance,
} from "../../lib/refiner/maintenance-queries";
import { mmActionButtonClass } from "../../lib/ui/mm-control-roles";

function canEdit(role: string | undefined): boolean {
  return role === "admin" || role === "operator";
}

const FAMILY_LABELS: Record<MaintenanceFamily, string> = {
  work_temp_stale_sweep: "Work file sweep",
  failure_cleanup: "Failure cleanup",
};

function stateLine(family: MaintenanceFamilyState): string {
  if (family.running > 0) return `Running now (${family.running}).`;
  if (family.pending > 0)
    return `Queued (${family.pending}), waiting for a worker.`;
  if (family.last_failed_at)
    return `Last run failed: ${family.last_error ?? "no reason recorded"}.`;
  if (family.last_completed_at)
    return `Last finished ${new Date(family.last_completed_at).toLocaleString()}.`;
  return "Has not run yet.";
}

/**
 * Maintenance families, and what the running instance is actually configured with.
 *
 * Until #339 these families could only be switched on by an undocumented environment
 * variable, and there was no way to run one from outside the process at all — an operator
 * who wanted to reclaim stale work files had to wait for a timer they could not see.
 */
export function RefinerMaintenanceSection() {
  const me = useMeQuery();
  const maintenance = useRefinerMaintenanceQuery();
  const runtime = useRefinerRuntimeSettingsQuery();
  const run = useRunRefinerMaintenance();
  const [notice, setNotice] = useState<string | null>(null);

  const editable = canEdit(me.data?.role);

  const trigger = async (
    family: MaintenanceFamily,
    mediaScope: "movie" | "tv",
  ) => {
    setNotice(null);
    try {
      // The server says whether anything was actually queued — a run already waiting
      // reports that rather than a success for a button press that did nothing.
      const result = await run.mutateAsync({ family, mediaScope });
      setNotice(result.detail);
    } catch {
      setNotice("That maintenance job could not be started.");
    }
  };

  return (
    <div className="space-y-4" data-testid="refiner-maintenance-section">
      <p className="text-sm text-[var(--mm-text2)]">
        Housekeeping MediaMop runs on a schedule. You can also start one now —
        starting it by hand ignores the schedule switch.
      </p>

      {notice ? (
        <p
          className="rounded border border-[var(--mm-border)] px-3 py-2 text-sm"
          role="status"
          data-testid="refiner-maintenance-notice"
        >
          {notice}
        </p>
      ) : null}

      <ul className="space-y-2">
        {(maintenance.data?.families ?? []).map((family) => (
          <li
            key={family.family}
            className="rounded border border-[var(--mm-border)] p-3"
            data-testid={`refiner-maintenance-${family.family}`}
          >
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div className="min-w-0">
                <p className="font-medium text-[var(--mm-text1)]">
                  {FAMILY_LABELS[family.family]}{" "}
                  <span className="text-xs font-normal text-[var(--mm-text3)]">
                    {family.enabled ? "scheduled" : "not scheduled"}
                  </span>
                </p>
                {/* The description carries the warning where the switch is: failure
                    cleanup deletes originals. */}
                <p className="text-sm text-[var(--mm-text2)]">
                  {family.description}
                </p>
                <p className="mt-1 text-xs text-[var(--mm-text3)]">
                  {stateLine(family)}
                </p>
              </div>
              {editable ? (
                <div className="flex gap-2">
                  <button
                    type="button"
                    className={mmActionButtonClass({ variant: "tertiary" })}
                    disabled={run.isPending}
                    onClick={() => void trigger(family.family, "movie")}
                    data-testid={`refiner-maintenance-run-${family.family}-movie`}
                  >
                    Run for Movies
                  </button>
                  <button
                    type="button"
                    className={mmActionButtonClass({ variant: "tertiary" })}
                    disabled={run.isPending}
                    onClick={() => void trigger(family.family, "tv")}
                    data-testid={`refiner-maintenance-run-${family.family}-tv`}
                  >
                    Run for TV
                  </button>
                </div>
              ) : null}
            </div>
          </li>
        ))}
      </ul>

      {runtime.data ? (
        <div
          className="rounded border border-[var(--mm-border)] p-3"
          data-testid="refiner-runtime-settings"
        >
          <p className="font-medium text-[var(--mm-text1)]">
            What this instance is running with
          </p>
          {/* Read-only. These come from the environment and a restart, so showing them
              as editable would promise something the screen cannot deliver. */}
          <ul className="mt-1 space-y-1 text-sm text-[var(--mm-text2)]">
            <li>{runtime.data.worker_mode_summary}</li>
            <li>{runtime.data.sqlite_throughput_note}</li>
            <li>
              File types accepted:{" "}
              {runtime.data.refiner_media_extensions.join(", ")}
            </li>
          </ul>
          <p className="mt-1 text-xs text-[var(--mm-text3)]">
            {runtime.data.configuration_note}
          </p>
        </div>
      ) : null}
    </div>
  );
}
