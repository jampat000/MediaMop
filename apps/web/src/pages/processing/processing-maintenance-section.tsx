import { useState } from "react";

import { useMeQuery } from "../../lib/auth/queries";
import type {
  MaintenanceFamily,
  MaintenanceFamilyState,
} from "../../lib/processing/maintenance-api";
import {
  useProcessingMaintenanceQuery,
  useProcessingRuntimeSettingsQuery,
  useRunProcessingMaintenance,
} from "../../lib/processing/maintenance-queries";
import { mmActionButtonClass } from "../../lib/ui/mm-control-roles";
import { useAppDateFormatter } from "../../lib/ui/mm-format-date";

function canEdit(role: string | undefined): boolean {
  return role === "admin" || role === "operator";
}

const FAMILY_LABELS: Record<MaintenanceFamily, string> = {
  work_temp_stale_sweep: "Work file sweep",
  failure_cleanup: "Failure cleanup",
};

/**
 * Families that delete something an operator cannot get back. Their description is the
 * only warning this screen gives, so it is painted in the warning colour rather than
 * left as body text — when the boxes went (docs/design/content-language.md rule 3) that
 * sentence was the one thing on the tab that must not get quieter.
 *
 * This is a decision per family, not a guess from the wording: a new family has to be
 * added here deliberately, and the type makes the compiler ask.
 */
const DESTRUCTIVE_FAMILIES: Record<MaintenanceFamily, boolean> = {
  work_temp_stale_sweep: false,
  failure_cleanup: true,
};

function stateLine(
  family: MaintenanceFamilyState,
  formatDate: (iso: string) => string,
): string {
  if (family.running > 0) return `Running now (${family.running}).`;
  if (family.pending > 0)
    return `Queued (${family.pending}), waiting for a worker.`;
  if (family.last_failed_at)
    return `Last run failed: ${family.last_error ?? "no reason recorded"}.`;
  if (family.last_completed_at)
    return `Last finished ${formatDate(family.last_completed_at)}.`;
  return "Has not run yet.";
}

/**
 * Maintenance families, and what the running instance is actually configured with.
 *
 * Until #339 these families could only be switched on by an undocumented environment
 * variable, and there was no way to run one from outside the process at all — an operator
 * who wanted to reclaim stale work files had to wait for a timer they could not see.
 *
 * Laid out in the Weir content language: no band and no hero (nothing here is a "now"
 * and no number carries the tab), so it starts at rule 3 — see
 * docs/design/content-language.md.
 */
export function ProcessingMaintenanceSection() {
  const formatDate = useAppDateFormatter();
  const me = useMeQuery();
  const maintenance = useProcessingMaintenanceQuery();
  const runtime = useProcessingRuntimeSettingsQuery();
  const run = useRunProcessingMaintenance();
  const [notice, setNotice] = useState<string | null>(null);

  const editable = canEdit(me.data?.role);
  const families = maintenance.data?.families ?? [];

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
    <div
      className="mm-quiet-stack"
      data-testid="processing-maintenance-section"
    >
      <section
        className="mm-quiet-section"
        aria-labelledby="processing-maintenance-heading"
      >
        <div className="mm-quiet-section__head">
          <h2
            id="processing-maintenance-heading"
            className="mm-quiet-section__title"
          >
            Housekeeping
          </h2>
        </div>
        <div className="mm-quiet-section__body">
          <p className="mm-quiet-note">
            Housekeeping Weir runs on a schedule. You can also start one now —
            starting it by hand ignores the schedule switch.
          </p>

          {notice ? (
            <p
              className="mt-3 text-sm font-medium text-[var(--mm-text1)]"
              role="status"
              data-testid="processing-maintenance-notice"
            >
              {notice}
            </p>
          ) : null}

          {families.length === 0 ? (
            <p className="mm-quiet-note mt-4">
              No housekeeping families are available on this instance.
            </p>
          ) : (
            <div className="mm-quiet-table-wrap mt-4">
              <table className="mm-quiet-table">
                <thead>
                  <tr>
                    <th scope="col">Job</th>
                    <th scope="col">What it does</th>
                    <th scope="col">State</th>
                    {editable ? (
                      <th scope="col">
                        <span className="sr-only">Run now</span>
                      </th>
                    ) : null}
                  </tr>
                </thead>
                <tbody>
                  {families.map((family) => (
                    <tr
                      key={family.family}
                      data-testid={`processing-maintenance-${family.family}`}
                    >
                      <th scope="row" className="mm-quiet-table__name">
                        <span>{FAMILY_LABELS[family.family]}</span>
                        {family.enabled ? (
                          <span className="mm-quiet-badge">scheduled</span>
                        ) : (
                          <span className="mm-quiet-badge mm-quiet-badge--off">
                            not scheduled
                          </span>
                        )}
                      </th>
                      {/* The description carries the warning where the switch is: failure
                          cleanup deletes originals. A destructive family says so in the
                          warning colour, so losing the card border did not quieten it. */}
                      <td data-label="What it does">
                        <span
                          className={
                            DESTRUCTIVE_FAMILIES[family.family]
                              ? "font-medium text-[var(--mm-status-warning-text)]"
                              : undefined
                          }
                        >
                          {family.description}
                        </span>
                      </td>
                      <td data-label="State">
                        {stateLine(family, formatDate)}
                      </td>
                      {editable ? (
                        <td data-label="Run now">
                          <div className="flex flex-wrap gap-2">
                            <button
                              type="button"
                              className={mmActionButtonClass({
                                variant: "tertiary",
                              })}
                              disabled={run.isPending}
                              onClick={() =>
                                void trigger(family.family, "movie")
                              }
                              data-testid={`processing-maintenance-run-${family.family}-movie`}
                            >
                              Run for Movies
                            </button>
                            <button
                              type="button"
                              className={mmActionButtonClass({
                                variant: "tertiary",
                              })}
                              disabled={run.isPending}
                              onClick={() => void trigger(family.family, "tv")}
                              data-testid={`processing-maintenance-run-${family.family}-tv`}
                            >
                              Run for TV
                            </button>
                          </div>
                        </td>
                      ) : null}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </section>

      {runtime.data ? (
        <section
          className="mm-quiet-section"
          aria-labelledby="processing-runtime-settings-heading"
          data-testid="processing-runtime-settings"
        >
          <div className="mm-quiet-section__head">
            <h2
              id="processing-runtime-settings-heading"
              className="mm-quiet-section__title"
            >
              What this instance is running with
            </h2>
          </div>
          {/* Read-only. These come from the environment and a restart, so showing them
              as editable would promise something the screen cannot deliver. */}
          <div className="mm-quiet-section__body">
            <ul className="grid gap-1.5 text-[length:var(--mm-type-body)] leading-relaxed text-[var(--mm-text2)]">
              <li>{runtime.data.worker_mode_summary}</li>
              <li>{runtime.data.sqlite_throughput_note}</li>
              <li>
                File types accepted:{" "}
                {runtime.data.processing_media_extensions.join(", ")}
              </li>
            </ul>
            <p className="mm-quiet-note mt-3">
              {runtime.data.configuration_note}
            </p>
          </div>
        </section>
      ) : null}
    </div>
  );
}
