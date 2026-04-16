import { useEffect, useId, useState } from "react";
import { MmListboxPicker, type MmListboxOption } from "../../components/ui/mm-listbox-picker";
import { PageLoading } from "../../components/shared/page-loading";
import { isHttpErrorFromApi, isLikelyNetworkFailure } from "../../lib/api/error-guards";
import { useMeQuery } from "../../lib/auth/queries";
import {
  useRefinerOperatorSettingsQuery,
  useRefinerOperatorSettingsSaveMutation,
  useRefinerPathSettingsQuery,
  useRefinerWatchedFolderRemuxScanDispatchEnqueueMutation,
} from "../../lib/refiner/queries";
import type { RefinerWatchedFolderRemuxScanDispatchEnqueueBody } from "../../lib/refiner/types";
import { mmActionButtonClass, mmCheckboxControlClass } from "../../lib/ui/mm-control-roles";

const FILES_AT_ONCE_OPTIONS: MmListboxOption[] = Array.from({ length: 8 }, (_, i) => ({
  value: String(i + 1),
  label: String(i + 1),
}));

function canTriggerRefinerJobs(role: string | undefined): boolean {
  return role === "operator" || role === "admin";
}

/** Manual watched-folder scan on ``refiner_jobs`` (classify; optional per-file pass enqueue). */
export function RefinerWatchedFolderScanSection() {
  const me = useMeQuery();
  const filesAtOnceLabelId = useId();
  const paths = useRefinerPathSettingsQuery();
  const operatorSettings = useRefinerOperatorSettingsQuery();
  const saveOperatorSettings = useRefinerOperatorSettingsSaveMutation();
  const enqueueScan = useRefinerWatchedFolderRemuxScanDispatchEnqueueMutation();

  const [mediaScope, setMediaScope] = useState<RefinerWatchedFolderRemuxScanDispatchEnqueueBody["media_scope"]>("movie");
  const [alsoEnqueueRemux, setAlsoEnqueueRemux] = useState(false);
  const [maxConcurrentFiles, setMaxConcurrentFiles] = useState("1");
  const [minFileAgeSeconds, setMinFileAgeSeconds] = useState("60");

  useEffect(() => {
    if (!operatorSettings.data) {
      return;
    }
    setMaxConcurrentFiles(String(operatorSettings.data.max_concurrent_files));
    setMinFileAgeSeconds(String(operatorSettings.data.min_file_age_seconds));
  }, [operatorSettings.data]);

  const canTrigger = canTriggerRefinerJobs(me.data?.role);
  const movieWatchedSet = Boolean((paths.data?.refiner_watched_folder ?? "").trim());
  const tvWatchedSet = Boolean((paths.data?.refiner_tv_watched_folder ?? "").trim());
  const movieOutputSet = Boolean((paths.data?.refiner_output_folder ?? "").trim());
  const tvOutputSet = Boolean((paths.data?.refiner_tv_output_folder ?? "").trim());
  const watchedSet = mediaScope === "movie" ? movieWatchedSet : tvWatchedSet;
  const outputSet = mediaScope === "movie" ? movieOutputSet : tvOutputSet;
  const missingLivePrereq = alsoEnqueueRemux && !outputSet;

  if (paths.isPending || me.isPending || operatorSettings.isPending) {
    return <PageLoading label="Loading Refiner path settings" />;
  }
  if (paths.isError || operatorSettings.isError) {
    return (
      <div
        className="mm-fetcher-module-surface w-full min-w-0 rounded border border-red-900/40 bg-red-950/20 p-4 text-sm text-red-200"
        data-testid="refiner-watched-folder-scan-path-error"
        role="alert"
      >
        <p className="font-semibold">Could not load path settings for watched-folder scan</p>
        <p className="mt-1">
          {isLikelyNetworkFailure(paths.error ?? operatorSettings.error)
            ? "Check that the MediaMop API is running."
            : isHttpErrorFromApi(paths.error ?? operatorSettings.error)
              ? "Sign in, then try again."
              : "Request failed."}
        </p>
      </div>
    );
  }
  if (!operatorSettings.data) {
    return null;
  }
  const draftConcurrent = Number.parseInt(maxConcurrentFiles, 10);
  const draftMinAge = Number.parseInt(minFileAgeSeconds, 10);
  const draftValid =
    Number.isFinite(draftConcurrent) &&
    draftConcurrent >= 1 &&
    draftConcurrent <= 8 &&
    Number.isFinite(draftMinAge) &&
    draftMinAge >= 0;
  const automationDirty =
    maxConcurrentFiles !== String(operatorSettings.data.max_concurrent_files) ||
    minFileAgeSeconds !== String(operatorSettings.data.min_file_age_seconds);

  return (
    <section
      className="mm-fetcher-module-surface w-full min-w-0 rounded border border-[var(--mm-border)] bg-[var(--mm-card-bg)] p-5 text-sm leading-relaxed text-[var(--mm-text2)] sm:p-6"
      aria-labelledby="refiner-watched-folder-scan-heading"
      data-testid="refiner-watched-folder-scan-section"
    >
      <h2 id="refiner-watched-folder-scan-heading" className="text-base font-semibold text-[var(--mm-text)]">
        Library check (manual)
      </h2>
      <div className="mt-4 rounded-md border border-[var(--mm-border)] bg-[var(--mm-card-bg)]/65 p-4">
        <h3 className="text-sm font-semibold text-[var(--mm-text1)]">Process and safety</h3>
        <p className="mt-1 text-xs text-[var(--mm-text3)]">
          Control how many files Refiner can process at once and how long files must sit unchanged before they are
          eligible. Per-library folder check intervals are under{" "}
          <strong className="text-[var(--mm-text2)]">Libraries</strong>.
        </p>
        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          <div className="block min-w-0">
            <span id={filesAtOnceLabelId} className="text-xs font-semibold uppercase tracking-wide text-[var(--mm-text3)]">
              Files at once
            </span>
            <MmListboxPicker
              className="w-full min-w-0"
              options={FILES_AT_ONCE_OPTIONS}
              value={maxConcurrentFiles}
              disabled={!canTrigger || saveOperatorSettings.isPending}
              onChange={setMaxConcurrentFiles}
              ariaLabelledBy={filesAtOnceLabelId}
              placeholder="Select…"
            />
          </div>
          <label className="block">
            <span className="text-xs font-semibold uppercase tracking-wide text-[var(--mm-text3)]">
              Min file age (seconds)
            </span>
            <input
              type="number"
              min={0}
              step={1}
              value={minFileAgeSeconds}
              disabled={!canTrigger || saveOperatorSettings.isPending}
              onChange={(e) => setMinFileAgeSeconds(e.target.value)}
              className="mm-input mt-1 w-full"
            />
          </label>
        </div>
        <div className="mt-3 rounded-md border border-[var(--mm-border)] bg-black/10 px-3 py-3">
          <button
            type="button"
            className={mmActionButtonClass({
              variant: "primary",
              disabled: !canTrigger || !automationDirty || !draftValid || saveOperatorSettings.isPending,
            })}
            disabled={!canTrigger || !automationDirty || !draftValid || saveOperatorSettings.isPending}
            onClick={() =>
              saveOperatorSettings.mutate({
                max_concurrent_files: draftConcurrent,
                min_file_age_seconds: draftMinAge,
              })
            }
          >
            {saveOperatorSettings.isPending ? "Saving…" : "Save processing settings"}
          </button>
        </div>
      </div>
      <p className="mt-2">
        Queues one walk of the <strong className="text-[var(--mm-text)]">saved watched folder</strong> for the scope you
        pick. The worker classifies supported media, runs ownership checks, then writes one{" "}
        <strong className="text-[var(--mm-text)]">Activity</strong> summary. This is{" "}
        <strong className="text-[var(--mm-text)]">not</strong> a filesystem watcher.
      </p>
      <details className="mt-3 rounded-md border border-[var(--mm-border)] bg-black/10 px-3 py-2.5 text-xs text-[var(--mm-text3)]">
        <summary className="cursor-pointer font-medium text-[var(--mm-text2)]">Timing, optional passes, and dedupe</summary>
        <p className="mt-2">
          Interval scans (when enabled) enqueue TV and Movies separately once those watched folders are saved. You can
          optionally queue per-file passes for eligible media; they follow your saved{" "}
          <strong className="text-[var(--mm-text)]">Audio & subtitles</strong>. Per-file passes are always live and need
          a saved output folder for that scope. Duplicate guards use scope plus relative path.
        </p>
      </details>

      {!canTrigger ? (
        <p className="mt-3 text-xs text-[var(--mm-text3)]">Operators and admins can queue this scan.</p>
      ) : null}

      <fieldset className="mt-4 space-y-2">
        <legend className="text-xs font-semibold uppercase tracking-wide text-[var(--mm-text3)]">Scan scope</legend>
        <label className="flex cursor-pointer items-center gap-2">
          <input
            type="radio"
            name="refiner-scan-scope"
            checked={mediaScope === "tv"}
            disabled={!canTrigger || enqueueScan.isPending}
            onChange={() => setMediaScope("tv")}
          />
          <span>TV paths</span>
        </label>
        <label className="flex cursor-pointer items-center gap-2">
          <input
            type="radio"
            name="refiner-scan-scope"
            checked={mediaScope === "movie"}
            disabled={!canTrigger || enqueueScan.isPending}
            onChange={() => setMediaScope("movie")}
          />
          <span>Movies paths</span>
        </label>
      </fieldset>

      {!watchedSet ? (
        <p className="mt-3 text-sm text-amber-200/90" role="status">
          Save a <strong className="text-[var(--mm-text)]">{mediaScope === "movie" ? "Movies" : "TV"} watched folder</strong>{" "}
          under Saved folders before queuing this scan.
        </p>
      ) : null}

      <div className="mt-5 space-y-3">
        <label className="flex cursor-pointer items-start gap-3">
          <input
            type="checkbox"
            className={mmCheckboxControlClass}
            checked={alsoEnqueueRemux}
            disabled={!canTrigger || enqueueScan.isPending || !watchedSet}
            onChange={(e) => setAlsoEnqueueRemux(e.target.checked)}
          />
          <span className="text-sm text-[var(--mm-text2)]">
            Also queue file passes for eligible media (ownership OK, not blocked by active upstream work).
          </span>
        </label>
      </div>

      {missingLivePrereq ? (
        <p className="mt-3 text-sm text-amber-200/90" role="status">
          Live file-pass enqueue needs a saved <strong className="text-[var(--mm-text)]">output folder</strong> for{" "}
          {mediaScope === "movie" ? "Movies" : "TV"} in path settings.
        </p>
      ) : null}

      {enqueueScan.isError ? (
        <p className="mt-3 text-sm text-red-300" role="alert" data-testid="refiner-watched-folder-scan-enqueue-error">
          {enqueueScan.error instanceof Error ? enqueueScan.error.message : "Enqueue failed."}
        </p>
      ) : null}

      {enqueueScan.isSuccess ? (
        <p className="mt-3 text-xs text-[var(--mm-text3)]" data-testid="refiner-watched-folder-scan-enqueued-hint">
          Queued scan job #{enqueueScan.data.job_id}. When workers run, check Activity (sidebar) for the summary.
        </p>
      ) : null}

      <div className="mt-6">
        <button
          type="button"
          className={mmActionButtonClass({
            variant: "secondary",
            disabled: !canTrigger || !watchedSet || enqueueScan.isPending || missingLivePrereq,
          })}
          disabled={!canTrigger || !watchedSet || enqueueScan.isPending || missingLivePrereq}
          onClick={() =>
            enqueueScan.mutate({
              enqueue_remux_jobs: alsoEnqueueRemux,
              media_scope: mediaScope,
            })
          }
        >
          {enqueueScan.isPending ? "Queuing…" : "Queue folder scan"}
        </button>
      </div>
    </section>
  );
}
