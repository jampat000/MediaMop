/** Subber module — durable ``subber_jobs`` lane (see ADR-0007). */
export function SubberPage() {
  return (
    <div className="mm-page" data-testid="subber-scope-page">
      <header className="mm-page__intro">
        <p className="mm-page__eyebrow">MediaMop</p>
        <h1 className="mm-page__title">Subber</h1>
        <p className="mm-page__subtitle">
          Subber is for <strong>subtitle and caption workflows</strong> on the{" "}
          <code className="rounded bg-black/25 px-1 py-0.5 font-mono text-[0.85em] text-[var(--mm-text)]">
            subber_jobs
          </code>{" "}
          queue, separate from Fetcher, Refiner, and Pruner. What ships today is a narrow, manual check — not a full
          subtitle pipeline.
        </p>
      </header>

      <section
        className="mt-4 max-w-2xl space-y-3 text-sm leading-relaxed text-[var(--mm-text2)]"
        aria-labelledby="subber-shipped-heading"
      >
        <h2 id="subber-shipped-heading" className="text-base font-semibold text-[var(--mm-text)]">
          Shipped durable job kind
        </h2>
        <p data-testid="subber-family-cue-timeline-constraints">
          <strong>
            <code className="rounded bg-black/25 px-1 py-0.5 font-mono text-[0.85em] text-[var(--mm-text)]">
              subber.supplied_cue_timeline.constraints_check.v1
            </code>
          </strong>{" "}
          — operators can enqueue a job with cue display intervals (start/end seconds on a notional media clock).
          Workers check ordering, overlap, and optional notional program length only.{" "}
          <strong>No</strong> OCR, <strong>no</strong> subtitle download or sync, <strong>no</strong> muxing, and{" "}
          <strong>no</strong> read of your media files — this is validation on the numbers you supply. Enable Subber
          workers with <code className="font-mono text-[0.85em]">MEDIAMOP_SUBBER_WORKER_COUNT</code> in the backend
          configuration when you want jobs to run.
        </p>
      </section>
    </div>
  );
}
