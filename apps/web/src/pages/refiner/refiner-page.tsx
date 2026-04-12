import { RefinerPathSettingsSection } from "./refiner-path-settings-section";
import { RefinerRuntimeSettingsSection } from "./refiner-runtime-settings-section";

/** Refiner module home — honest scope for shipped durable ``refiner_jobs`` families. */
export function RefinerPage() {
  return (
    <div className="mm-page" data-testid="refiner-scope-page">
      <header className="mm-page__intro">
        <p className="mm-page__eyebrow">MediaMop</p>
        <h1 className="mm-page__title">Refiner</h1>
        <p className="mm-page__subtitle">
          Refiner is the in-app place for durable <strong>Refiner</strong> work stored on{" "}
          <code className="rounded bg-black/25 px-1 py-0.5 font-mono text-[0.85em] text-[var(--mm-text)]">
            refiner_jobs
          </code>{" "}
          — separate from automated download-queue and Arr-search jobs, which persist on{" "}
          <code className="rounded bg-black/25 px-1 py-0.5 font-mono text-[0.85em] text-[var(--mm-text)]">
            fetcher_jobs
          </code>
          . Shipped families below apply Refiner domain rules where relevant; they are not a full watched-folder
          service.
        </p>
      </header>

      <RefinerRuntimeSettingsSection />

      <RefinerPathSettingsSection />

      <section
        className="mt-4 max-w-2xl space-y-3 text-sm leading-relaxed text-[var(--mm-text2)]"
        aria-labelledby="refiner-shipped-families-heading"
      >
        <h2 id="refiner-shipped-families-heading" className="text-base font-semibold text-[var(--mm-text)]">
          Shipped durable job kinds
        </h2>
        <ul className="list-disc space-y-3 pl-5">
          <li data-testid="refiner-family-supplied-payload-evaluation">
            <strong>
              <code className="rounded bg-black/25 px-1 py-0.5 font-mono text-[0.85em] text-[var(--mm-text)]">
                refiner.supplied_payload_evaluation.v1
              </code>
            </strong>{" "}
            — reads an optional JSON payload on the job (
            <code className="rounded bg-black/25 px-1 font-mono text-[0.8em]">rows</code> plus optional{" "}
            <code className="rounded bg-black/25 px-1 font-mono text-[0.8em]">file</code> title/year) and evaluates
            those values only. It does <strong>not</strong> call Radarr or Sonarr, and it does <strong>not</strong>{" "}
            perform a library-wide audit or filesystem sweep. Optional periodic enqueue uses Refiner-only schedule
            settings in the backend configuration.
          </li>
          <li data-testid="refiner-family-candidate-gate">
            <strong>
              <code className="rounded bg-black/25 px-1 py-0.5 font-mono text-[0.85em] text-[var(--mm-text)]">
                refiner.candidate_gate.v1
              </code>
            </strong>{" "}
            — manual jobs that fetch the live <strong>Radarr</strong> or <strong>Sonarr</strong> download queue from
            your configured service, then evaluate domain rules for a specific release named in the payload.
          </li>
          <li data-testid="refiner-family-file-remux-pass">
            <strong>
              <code className="rounded bg-black/25 px-1 py-0.5 font-mono text-[0.85em] text-[var(--mm-text)]">
                refiner.file.remux_pass.v1
              </code>
            </strong>{" "}
            — one file path relative to the saved <strong>Refiner watched folder</strong>: <strong>ffprobe</strong>{" "}
            plus remux <strong>planning</strong> (audio/subtitle selection). Path settings may be saved without a watched
            folder, but <strong>enqueue is rejected</strong> until a watched folder is configured (same requirement at
            worker run if a job were queued by other means). Manual enqueue defaults to <strong>dry run</strong> (no
            ffmpeg output, no source deletion). Live remux requires{" "}
            <code className="font-mono text-[0.85em]">dry_run: false</code>, a saved output folder, ffmpeg/ffprobe
            available, remux temp on the saved work/temp folder, and final output
            under the saved output folder with relative folders preserved. Finished passes write a structured summary to
            the Activity feed (Overview → Activity), including when an existing output file was replaced and whether the
            source file under the watched folder was removed after success.
          </li>
        </ul>
      </section>
    </div>
  );
}
