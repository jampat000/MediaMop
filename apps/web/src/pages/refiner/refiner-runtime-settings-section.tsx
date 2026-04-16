import { PageLoading } from "../../components/shared/page-loading";
import { isHttpErrorFromApi, isLikelyNetworkFailure } from "../../lib/api/error-guards";
import { useRefinerRuntimeSettingsQuery } from "../../lib/refiner/queries";

export function RefinerRuntimeSettingsSection() {
  const q = useRefinerRuntimeSettingsQuery();

  if (q.isPending) {
    return <PageLoading label="Loading workers" />;
  }
  if (q.isError) {
    return <RefinerRuntimeSettingsError err={q.error} />;
  }
  const d = q.data;
  return (
    <section
      className="mm-fetcher-module-surface w-full min-w-0 rounded border border-[var(--mm-border)] bg-[var(--mm-card-bg)] p-5 text-sm leading-relaxed text-[var(--mm-text2)] sm:p-6"
      aria-labelledby="refiner-runtime-settings-heading"
      data-testid="refiner-runtime-settings"
    >
      <h2 id="refiner-runtime-settings-heading" className="text-base font-semibold text-[var(--mm-text)]">
        Workers
      </h2>
      <p className="mt-2 text-[var(--mm-text3)]">Workers pick up queued Refiner jobs in the background.</p>
      <div className="mt-4 rounded-md border border-[var(--mm-border)] bg-[var(--mm-card-bg)]/65 px-4 py-3">
        <p className="text-xs font-semibold uppercase tracking-wide text-[var(--mm-text3)]">Current state</p>
        <p className="mt-1 text-base font-semibold text-[var(--mm-text1)]">
          {d.in_process_refiner_worker_count} worker{d.in_process_refiner_worker_count === 1 ? "" : "s"}
        </p>
        <p className="mt-1 text-sm text-[var(--mm-text2)]">{d.worker_mode_summary}</p>
      </div>
      <p className="mt-3 text-xs text-[var(--mm-text3)]">
        This is read-only status in MediaMop today. If you need to change worker count, change backend config and
        restart the API.
      </p>
      <p className="mt-1 text-xs text-[var(--mm-text3)]">{d.sqlite_throughput_note}</p>

      <details className="mt-5 rounded-md border border-[var(--mm-border)] bg-black/10 p-3">
        <summary className="cursor-pointer text-sm font-medium text-[var(--mm-text1)]">Advanced worker notes</summary>
        <p className="mt-2 text-xs text-[var(--mm-text3)]">{d.configuration_note}</p>
        <p className="mt-2 text-xs text-[var(--mm-text3)]">{d.visibility_note}</p>
      </details>

      <h3 className="mt-7 text-sm font-semibold text-[var(--mm-text)]">Timed folder scans</h3>
      <p className="mt-1 text-[var(--mm-text3)]">
        Refiner can check TV and Movies watched folders on a timer. Each scope is evaluated independently and this is
        not live filesystem watching.
      </p>
      <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-[var(--mm-text2)]">
        <li>Enabled: {d.refiner_watched_folder_remux_scan_dispatch_schedule_enabled ? "Yes" : "No"}</li>
        <li>Check interval: every {d.refiner_watched_folder_remux_scan_dispatch_schedule_interval_seconds} seconds</li>
        <li>Periodic file passes: {d.refiner_watched_folder_remux_scan_dispatch_periodic_enqueue_remux_jobs ? "Yes" : "No"}</li>
        <li>Periodic pass mode: {d.refiner_watched_folder_remux_scan_dispatch_periodic_remux_dry_run ? "Dry run" : "Live"}</li>
        <li>File readiness guardrail: skip files newer than {d.refiner_watched_folder_min_file_age_seconds} seconds</li>
      </ul>

      <details className="mt-4 rounded-md border border-[var(--mm-border)] bg-black/10 p-3">
        <summary className="cursor-pointer text-sm font-medium text-[var(--mm-text1)]">Advanced timer configuration</summary>
        <p className="mt-2 text-xs text-[var(--mm-text3)]">{d.watched_folder_scan_periodic_configuration_note}</p>
      </details>

      <details className="mt-4 rounded-md border border-[var(--mm-border)] bg-black/10 p-3">
        <summary className="cursor-pointer text-sm font-medium text-[var(--mm-text1)]">What each Refiner job does</summary>
        <ul className="mt-2 list-disc space-y-1 pl-5 text-xs text-[var(--mm-text2)]">
          <li>Payload check: evaluates supplied queue payload data only.</li>
          <li>Download queue check: checks one release against live Radarr/Sonarr queue rows.</li>
          <li>Library check: scans watched folders and can queue eligible file runs.</li>
          <li>Run one file: probes/plans/remuxes one file under a watched folder path.</li>
        </ul>
      </details>
    </section>
  );
}

function RefinerRuntimeSettingsError({ err }: { err: unknown }) {
  return (
    <div
      className="mm-fetcher-module-surface w-full min-w-0 rounded border border-red-900/40 bg-red-950/20 p-4 text-sm text-red-200"
      data-testid="refiner-runtime-settings-error"
      role="alert"
    >
      <p className="font-semibold">Could not load worker settings</p>
      <p className="mt-1">
        {isLikelyNetworkFailure(err)
          ? "Check that the MediaMop API is running."
          : isHttpErrorFromApi(err)
            ? "Sign in as an operator or admin, then try again."
            : "Request failed."}
      </p>
      {err instanceof Error ? <p className="mt-1 font-mono text-xs opacity-90">{err.message}</p> : null}
    </div>
  );
}
