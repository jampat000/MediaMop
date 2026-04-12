/** Trimmer module — durable ``trimmer_jobs`` lane (see ADR-0007). */
export function TrimmerPage() {
  return (
    <div className="mm-page" data-testid="trimmer-scope-page">
      <header className="mm-page__intro">
        <p className="mm-page__eyebrow">MediaMop</p>
        <h1 className="mm-page__title">Trimmer</h1>
        <p className="mm-page__subtitle">
          Trimmer is for work that <strong>changes how much of a source you keep</strong> — cuts and length edits —
          on the <code className="rounded bg-black/25 px-1 py-0.5 font-mono text-[0.85em] text-[var(--mm-text)]">
            trimmer_jobs
          </code>{" "}
          queue. It is separate from Fetcher download-queue automation and from Refiner metadata refinement.
        </p>
      </header>

      <section
        className="mt-4 max-w-2xl space-y-3 text-sm leading-relaxed text-[var(--mm-text2)]"
        aria-labelledby="trimmer-shipped-heading"
      >
        <h2 id="trimmer-shipped-heading" className="text-base font-semibold text-[var(--mm-text)]">
          Shipped durable job kinds
        </h2>
        <p data-testid="trimmer-family-trim-plan-constraints">
          <strong>
            <code className="rounded bg-black/25 px-1 py-0.5 font-mono text-[0.85em] text-[var(--mm-text)]">
              trimmer.trim_plan.constraints_check.v1
            </code>
          </strong>{" "}
          — operators enqueue segment start/end times (seconds on a notional timeline). Workers check ordering,
          overlap, and optional source duration only.{" "}
          <strong>No</strong> transcoding, <strong>no</strong> disk read of your media files, and{" "}
          <strong>no</strong> calls to Radarr or Sonarr — constraint validation on the numbers you supply.
        </p>
        <p data-testid="trimmer-family-json-file-write">
          <strong>
            <code className="rounded bg-black/25 px-1 py-0.5 font-mono text-[0.85em] text-[var(--mm-text)]">
              trimmer.supplied_trim_plan.json_file_write.v1
            </code>
          </strong>{" "}
          — same segment rules; when valid, workers write one JSON file under{" "}
          <code className="font-mono text-[0.85em]">MEDIAMOP_HOME/trimmer/plan_exports/</code>. That is a plan export
          on disk, <strong>not</strong> cutting or remuxing media and <strong>not</strong> running FFmpeg.
        </p>
        <p className="text-[var(--mm-text2)]">
          Enable Trimmer workers with{" "}
          <code className="font-mono text-[0.85em]">MEDIAMOP_TRIMMER_WORKER_COUNT</code> in the backend configuration
          when you want jobs to run.
        </p>
      </section>
    </div>
  );
}
