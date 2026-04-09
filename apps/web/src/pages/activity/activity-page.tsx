/** Read-only Activity slice (Stage 7 Pass 2) — empty until a real event source exists. */

export function ActivityPage() {
  return (
    <div className="mm-page">
      <header className="mm-page__intro">
        <p className="mm-page__eyebrow">Overview</p>
        <h1 className="mm-page__title">Activity</h1>
        <p className="mm-page__subtitle">
          Read-only timeline of events from MediaMop and suite modules, when they are available.
        </p>
        <p className="mm-page__lead">
          This view is read-only and intentionally narrow: no filters, export, or actions. A stable event feed is
          not wired yet.
        </p>
      </header>

      <section className="mm-activity-panel" aria-label="Activity entries">
        <p className="mm-activity-empty">
          Nothing to show — recent activity is not connected to this view yet.
        </p>
      </section>
    </div>
  );
}
