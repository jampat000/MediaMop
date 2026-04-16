/**
 * What each Refiner job family does — operator language first; technical ids below each block.
 */
export function RefinerWorkTypesSection() {
  return (
    <section
      className="mm-fetcher-module-surface w-full min-w-0 space-y-6 rounded border border-[var(--mm-border)] bg-[var(--mm-card-bg)] p-5 text-sm leading-relaxed text-[var(--mm-text2)] sm:p-6"
      aria-labelledby="refiner-work-types-heading"
      data-testid="refiner-work-types-section"
    >
      <div>
        <h2 id="refiner-work-types-heading" className="text-base font-semibold text-[var(--mm-text)]">
          Job types
        </h2>
        <p className="mt-2 max-w-3xl text-[var(--mm-text3)]">
          Durable Refiner jobs only—finished work surfaces on{" "}
          <strong className="text-[var(--mm-text)]">Activity</strong>.
        </p>
      </div>

      <div className="space-y-4">
        <article
          data-testid="refiner-family-supplied-payload-evaluation"
          className="rounded-md border border-[var(--mm-border)] bg-[var(--mm-card-bg)]/60 p-4"
        >
          <h3 className="text-sm font-semibold text-[var(--mm-text1)]">Payload check</h3>
          <p className="mt-1.5 text-sm text-[var(--mm-text2)]">
            Reads JSON on the job (<span className="font-mono text-xs">rows</span> and optional{" "}
            <span className="font-mono text-xs">file</span> hints) and evaluates those values only—no Radarr/Sonarr
            calls, no library-wide audit, no disk sweep.
          </p>
          <p className="mt-2 font-mono text-[0.65rem] text-[var(--mm-text3)]">refiner.supplied_payload_evaluation.v1</p>
        </article>

        <article
          data-testid="refiner-family-candidate-gate"
          className="rounded-md border border-[var(--mm-border)] bg-[var(--mm-card-bg)]/60 p-4"
        >
          <h3 className="text-sm font-semibold text-[var(--mm-text1)]">Download queue check</h3>
          <p className="mt-1.5 text-sm text-[var(--mm-text2)]">
            Manual job: reads the live Radarr or Sonarr download queue, then checks one named release from the payload.
          </p>
          <p className="mt-2 font-mono text-[0.65rem] text-[var(--mm-text3)]">refiner.candidate_gate.v1</p>
        </article>

        <article
          data-testid="refiner-family-watched-folder-remux-scan-dispatch"
          className="rounded-md border border-[var(--mm-border)] bg-[var(--mm-card-bg)]/60 p-4"
        >
          <h3 className="text-sm font-semibold text-[var(--mm-text1)]">Watched-folder scan</h3>
          <p className="mt-1.5 text-sm text-[var(--mm-text2)]">
            Classifies files under the saved watched folder, applies ownership rules, optionally queues per-file passes,
            and writes one Activity summary. Interval enqueue is env-driven—not a filesystem watcher.
          </p>
          <p className="mt-2 font-mono text-[0.65rem] text-[var(--mm-text3)]">refiner.watched_folder.remux_scan_dispatch.v1</p>
        </article>

        <article data-testid="refiner-family-file-remux-pass" className="rounded-md border border-[var(--mm-border)] bg-[var(--mm-card-bg)]/60 p-4">
          <h3 className="text-sm font-semibold text-[var(--mm-text1)]">Single-file pass</h3>
          <p className="mt-1.5 text-sm text-[var(--mm-text2)]">
            One path under the saved watched folder: ffprobe, plan, optional ffmpeg write. Saved defaults and manual
            queue live on <strong className="text-[var(--mm-text)]">Audio & subtitles</strong>. Enqueue is rejected until a
            watched and output folder exist. Live runs need tools on disk and workers. Results appear on{" "}
            <strong className="text-[var(--mm-text)]">Activity</strong>.
          </p>
          <p className="mt-2 font-mono text-[0.65rem] text-[var(--mm-text3)]">refiner.file.remux_pass.v1</p>
        </article>
      </div>
    </section>
  );
}
