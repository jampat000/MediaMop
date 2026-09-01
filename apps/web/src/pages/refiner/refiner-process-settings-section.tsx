import { useEffect, useId, useState } from "react";
import {
  MmListboxPicker,
  type MmListboxOption,
} from "../../components/ui/mm-listbox-picker";
import { PageLoading } from "../../components/shared/page-loading";
import {
  isHttpErrorFromApi,
  isLikelyNetworkFailure,
} from "../../lib/api/error-guards";
import { useMeQuery } from "../../lib/auth/queries";
import {
  useRefinerOperatorSettingsQuery,
  useRefinerOperatorSettingsSaveMutation,
} from "../../lib/refiner/queries";
import { mmActionButtonClass } from "../../lib/ui/mm-control-roles";

function canEdit(role: string | undefined): boolean {
  return role === "operator" || role === "admin";
}

const FILES_AT_ONCE_OPTIONS: MmListboxOption[] = Array.from(
  { length: 8 },
  (_, i) => ({
    value: String(i + 1),
    label: String(i + 1),
  }),
);

/** Throughput and file-age gates (not paths or poll intervals — those live under Libraries). */
export function RefinerProcessSettingsSection() {
  const me = useMeQuery();
  const q = useRefinerOperatorSettingsQuery();
  const save = useRefinerOperatorSettingsSaveMutation();
  const filesAtOnceLabelId = useId();
  const editable = canEdit(me.data?.role);

  const [maxConcurrentFiles, setMaxConcurrentFiles] = useState("1");
  const [runnerCapacity, setRunnerCapacity] = useState("4");
  const [runnerCostSd, setRunnerCostSd] = useState("1");
  const [runnerCost720p, setRunnerCost720p] = useState("1");
  const [runnerCost1080p, setRunnerCost1080p] = useState("2");
  const [runnerCost4k, setRunnerCost4k] = useState("4");
  const [runnerCostUndetermined, setRunnerCostUndetermined] = useState("0");
  const [minFileAgeSeconds, setMinFileAgeSeconds] = useState("60");
  const [minInputFileSizeMb, setMinInputFileSizeMb] = useState("50");
  const [minimumFreeDiskSpaceGb, setMinimumFreeDiskSpaceGb] = useState("5");
  const [fileLogRetentionDays, setFileLogRetentionDays] = useState("90");
  const [workTempStaleSweepEnabled, setWorkTempStaleSweepEnabled] =
    useState(true);
  const [failureCleanupEnabled, setFailureCleanupEnabled] = useState(false);
  const [keepFailedWorkFiles, setKeepFailedWorkFiles] = useState(false);
  const [verboseDetectionLogging, setVerboseDetectionLogging] = useState(false);

  useEffect(() => {
    if (!q.data) {
      return;
    }
    setMaxConcurrentFiles(String(q.data.max_concurrent_files));
    setRunnerCapacity(String(q.data.runner_capacity));
    setRunnerCostSd(String(q.data.runner_cost_sd));
    setRunnerCost720p(String(q.data.runner_cost_720p));
    setRunnerCost1080p(String(q.data.runner_cost_1080p));
    setRunnerCost4k(String(q.data.runner_cost_4k));
    setRunnerCostUndetermined(String(q.data.runner_cost_undetermined));
    setMinFileAgeSeconds(String(q.data.min_file_age_seconds));
    setMinInputFileSizeMb(String(q.data.refiner_min_input_file_size_mb));
    setMinimumFreeDiskSpaceGb(
      String(Math.max(0, q.data.minimum_free_disk_space_mb / 1024)),
    );
    setFileLogRetentionDays(String(q.data.file_log_retention_days));
    setWorkTempStaleSweepEnabled(q.data.work_temp_stale_sweep_enabled);
    setFailureCleanupEnabled(q.data.failure_cleanup_enabled);
    setKeepFailedWorkFiles(q.data.keep_failed_work_files);
    setVerboseDetectionLogging(q.data.verbose_detection_logging);
  }, [q.data]);

  if (q.isPending || me.isPending) {
    return <PageLoading label="Loading Refiner processing settings" />;
  }
  if (q.isError) {
    return (
      <div
        className="mm-module-surface w-full min-w-0 rounded border border-red-900/40 bg-red-950/20 p-4 text-sm text-red-200"
        role="alert"
      >
        <p className="font-semibold">
          Could not load Refiner processing settings
        </p>
        <p className="mt-1">
          {isLikelyNetworkFailure(q.error)
            ? "Check that the MediaMop API is running."
            : isHttpErrorFromApi(q.error)
              ? "Sign in, then try again."
              : "Request failed."}
        </p>
      </div>
    );
  }
  if (!q.data) {
    return null;
  }

  const draftConcurrent = Number.parseInt(maxConcurrentFiles, 10);
  const draftRunnerCapacity = Number.parseInt(runnerCapacity, 10);
  const draftRunnerCostSd = Number.parseInt(runnerCostSd, 10);
  const draftRunnerCost720p = Number.parseInt(runnerCost720p, 10);
  const draftRunnerCost1080p = Number.parseInt(runnerCost1080p, 10);
  const draftRunnerCost4k = Number.parseInt(runnerCost4k, 10);
  const draftRunnerCostUndetermined = Number.parseInt(
    runnerCostUndetermined,
    10,
  );
  const draftMinAge = Number.parseInt(minFileAgeSeconds, 10);
  const draftMinInputSize = Number.parseInt(minInputFileSizeMb, 10);
  const draftMinimumFreeGb = Number.parseFloat(minimumFreeDiskSpaceGb);
  const draftMinimumFreeMb = Math.round(draftMinimumFreeGb * 1024);
  const draftFileLogRetentionDays = Number.parseInt(fileLogRetentionDays, 10);
  const runnerNumbers = [
    draftRunnerCapacity,
    draftRunnerCostSd,
    draftRunnerCost720p,
    draftRunnerCost1080p,
    draftRunnerCost4k,
    draftRunnerCostUndetermined,
  ];
  const draftValid =
    Number.isFinite(draftConcurrent) &&
    draftConcurrent >= 1 &&
    draftConcurrent <= 8 &&
    runnerNumbers.every(
      (value, index) =>
        Number.isFinite(value) && value >= (index === 0 ? 1 : 0) && value <= 64,
    ) &&
    Number.isFinite(draftMinAge) &&
    draftMinAge >= 0 &&
    Number.isFinite(draftMinInputSize) &&
    draftMinInputSize >= 0 &&
    Number.isFinite(draftMinimumFreeGb) &&
    draftMinimumFreeGb >= 0 &&
    Number.isFinite(draftFileLogRetentionDays) &&
    draftFileLogRetentionDays >= 0 &&
    draftFileLogRetentionDays <= 3650;
  const dirty =
    maxConcurrentFiles !== String(q.data.max_concurrent_files) ||
    runnerCapacity !== String(q.data.runner_capacity) ||
    runnerCostSd !== String(q.data.runner_cost_sd) ||
    runnerCost720p !== String(q.data.runner_cost_720p) ||
    runnerCost1080p !== String(q.data.runner_cost_1080p) ||
    runnerCost4k !== String(q.data.runner_cost_4k) ||
    runnerCostUndetermined !== String(q.data.runner_cost_undetermined) ||
    minFileAgeSeconds !== String(q.data.min_file_age_seconds) ||
    minInputFileSizeMb !== String(q.data.refiner_min_input_file_size_mb) ||
    draftMinimumFreeMb !== q.data.minimum_free_disk_space_mb ||
    fileLogRetentionDays !== String(q.data.file_log_retention_days) ||
    workTempStaleSweepEnabled !== q.data.work_temp_stale_sweep_enabled ||
    failureCleanupEnabled !== q.data.failure_cleanup_enabled ||
    keepFailedWorkFiles !== q.data.keep_failed_work_files ||
    verboseDetectionLogging !== q.data.verbose_detection_logging;

  const numberField = (
    label: string,
    value: string,
    setValue: (next: string) => void,
    options: { min?: number; max?: number; step?: number; hint?: string } = {},
  ) => (
    <label className="block min-w-0">
      <span className="text-xs font-semibold uppercase tracking-wide text-[var(--mm-text3)]">
        {label}
      </span>
      <input
        type="number"
        min={options.min ?? 0}
        max={options.max}
        step={options.step}
        value={value}
        disabled={!editable || save.isPending}
        onChange={(event) => setValue(event.target.value)}
        className="mm-input mt-1 w-full"
      />
      {options.hint ? (
        <span className="mt-1 block text-xs leading-5 text-[var(--mm-text3)]">
          {options.hint}
        </span>
      ) : null}
    </label>
  );

  const toggleField = (
    label: string,
    detail: string,
    checked: boolean,
    setChecked: (next: boolean) => void,
    warning = false,
  ) => (
    <label
      className={`flex items-start gap-3 rounded-lg border px-3 py-3 ${
        warning && checked
          ? "border-[var(--mm-warning-border)] bg-[var(--mm-status-warning-bg)]"
          : "border-[var(--mm-border)] bg-[var(--mm-card-bg)]"
      }`}
    >
      <input
        type="checkbox"
        className="mt-1"
        checked={checked}
        disabled={!editable || save.isPending}
        onChange={(event) => setChecked(event.target.checked)}
      />
      <span>
        <span className="block font-medium text-[var(--mm-text1)]">
          {label}
        </span>
        <span className="mt-0.5 block text-xs leading-5 text-[var(--mm-text3)]">
          {detail}
        </span>
      </span>
    </label>
  );

  return (
    <section className="mm-module-surface flex w-full min-w-0 flex-col rounded border border-[var(--mm-border)] bg-[var(--mm-card-bg)] p-6 text-sm leading-relaxed text-[var(--mm-text2)] sm:p-7">
      <p className="mm-page__eyebrow">Global Refiner controls</p>
      <h2 className="mt-1 text-lg font-semibold text-[var(--mm-text)]">
        Processing, safety and records
      </h2>
      <p className="mt-2 max-w-3xl text-[var(--mm-text3)]">
        These defaults apply across Refiner. A library can still narrow its own
        intake, schedule and concurrency above.
      </p>
      <div className="mm-card-action-body mt-6 flex-1 min-h-0">
        <div className="grid gap-4 xl:grid-cols-2">
          <section className="space-y-4 rounded-xl border border-[var(--mm-border)] bg-[var(--mm-surface2)] p-4">
            <div>
              <h3 className="font-semibold text-[var(--mm-text1)]">
                Throughput budget
              </h3>
              <p className="mt-1 text-xs leading-5 text-[var(--mm-text3)]">
                Files consume runner units by resolution. Work starts only when
                both a file slot and enough units are available.
              </p>
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="block min-w-0">
                <span
                  id={filesAtOnceLabelId}
                  className="text-xs font-semibold uppercase tracking-wide text-[var(--mm-text3)]"
                >
                  Absolute file limit
                </span>
                <MmListboxPicker
                  className="w-full min-w-0"
                  options={FILES_AT_ONCE_OPTIONS}
                  value={maxConcurrentFiles}
                  disabled={!editable || save.isPending}
                  onChange={setMaxConcurrentFiles}
                  ariaLabelledBy={filesAtOnceLabelId}
                  placeholder="Select…"
                />
              </div>
              {numberField(
                "Runner capacity (units)",
                runnerCapacity,
                setRunnerCapacity,
                { min: 1, max: 64 },
              )}
              {numberField("SD cost", runnerCostSd, setRunnerCostSd, {
                max: 64,
              })}
              {numberField("720p cost", runnerCost720p, setRunnerCost720p, {
                max: 64,
              })}
              {numberField("1080p cost", runnerCost1080p, setRunnerCost1080p, {
                max: 64,
              })}
              {numberField("4K cost", runnerCost4k, setRunnerCost4k, {
                max: 64,
              })}
              {numberField(
                "Unknown-resolution cost",
                runnerCostUndetermined,
                setRunnerCostUndetermined,
                {
                  max: 64,
                  hint: "0 admits an unmeasured file without consuming units.",
                },
              )}
            </div>
          </section>

          <section className="space-y-4 rounded-xl border border-[var(--mm-border)] bg-[var(--mm-surface2)] p-4">
            <div>
              <h3 className="font-semibold text-[var(--mm-text1)]">
                Admission safety
              </h3>
              <p className="mt-1 text-xs leading-5 text-[var(--mm-text3)]">
                Final global guardrails before Refiner probes or writes. Keep
                downloader limits too; these protect the processing host.
              </p>
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              {numberField(
                "Minimum unchanged age (seconds)",
                minFileAgeSeconds,
                setMinFileAgeSeconds,
              )}
              {numberField(
                "Minimum file size (MB)",
                minInputFileSizeMb,
                setMinInputFileSizeMb,
                { hint: "Smaller files are skipped before probing." },
              )}
              {numberField(
                "Minimum free output space (GB)",
                minimumFreeDiskSpaceGb,
                setMinimumFreeDiskSpaceGb,
                {
                  step: 0.1,
                  hint: "No new write starts below this threshold.",
                },
              )}
            </div>
          </section>

          <section className="space-y-4 rounded-xl border border-[var(--mm-border)] bg-[var(--mm-surface2)] p-4 xl:col-span-2">
            <div>
              <h3 className="font-semibold text-[var(--mm-text1)]">
                Records and cleanup
              </h3>
              <p className="mt-1 text-xs leading-5 text-[var(--mm-text3)]">
                Choose how much diagnostic history to keep and how MediaMop
                treats its own temporary data after work finishes or fails.
              </p>
            </div>
            <div className="grid gap-4 lg:grid-cols-3">
              {numberField(
                "Processing-record retention (days)",
                fileLogRetentionDays,
                setFileLogRetentionDays,
                { max: 3650, hint: "0 keeps file records forever." },
              )}
              <div className="space-y-3 lg:col-span-2">
                {toggleField(
                  "Reclaim stale temporary files",
                  "Safely removes old files from MediaMop's private work area. Recommended and enabled by default.",
                  workTempStaleSweepEnabled,
                  setWorkTempStaleSweepEnabled,
                )}
                {toggleField(
                  "Keep failed work files",
                  "Leaves failed temporary outputs available for inspection; the stale sweep will not remove them.",
                  keepFailedWorkFiles,
                  setKeepFailedWorkFiles,
                )}
                {toggleField(
                  "Verbose file-detection records",
                  "Adds noisy intake diagnostics while troubleshooting. Turn it off again after the cause is clear.",
                  verboseDetectionLogging,
                  setVerboseDetectionLogging,
                )}
                {toggleField(
                  "Delete source after a terminal failure",
                  "High risk: removes the original release folder after Refiner gives up. Successful processing cleanup is separate and remains automatic.",
                  failureCleanupEnabled,
                  setFailureCleanupEnabled,
                  true,
                )}
              </div>
            </div>
          </section>
        </div>
        {save.isError ? (
          <p className="mt-3 text-sm text-red-300" role="alert">
            {save.error instanceof Error ? save.error.message : "Save failed."}
          </p>
        ) : null}
      </div>
      <div className="mm-card-action-footer">
        <button
          type="button"
          className={mmActionButtonClass({
            variant: "primary",
            disabled: !editable || !dirty || !draftValid || save.isPending,
          })}
          disabled={!editable || !dirty || !draftValid || save.isPending}
          onClick={() =>
            save.mutate({
              max_concurrent_files: draftConcurrent,
              runner_capacity: draftRunnerCapacity,
              runner_cost_sd: draftRunnerCostSd,
              runner_cost_720p: draftRunnerCost720p,
              runner_cost_1080p: draftRunnerCost1080p,
              runner_cost_4k: draftRunnerCost4k,
              runner_cost_undetermined: draftRunnerCostUndetermined,
              work_temp_stale_sweep_enabled: workTempStaleSweepEnabled,
              failure_cleanup_enabled: failureCleanupEnabled,
              keep_failed_work_files: keepFailedWorkFiles,
              file_log_retention_days: draftFileLogRetentionDays,
              verbose_detection_logging: verboseDetectionLogging,
              min_file_age_seconds: draftMinAge,
              refiner_min_input_file_size_mb: draftMinInputSize,
              minimum_free_disk_space_mb: draftMinimumFreeMb,
            })
          }
        >
          {save.isPending ? "Saving…" : "Save processing settings"}
        </button>
      </div>
    </section>
  );
}
