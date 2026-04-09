/** Honest placeholder — real route, no product settings logic yet (Phase 10). */

export function SettingsPlaceholder() {
  return (
    <div className="mb-page">
      <header className="mb-page__intro">
        <p className="mb-page__eyebrow">Account</p>
        <h1 className="mb-page__title">Settings</h1>
        <p className="mb-page__lead">
          This page exists so navigation and the shell behave like the shipping product. Account,
          integrations, and module preferences are not built here yet.
        </p>
      </header>
      <div className="mb-page__body">
        <article className="mb-card">
          <h2 className="mb-card__title">Placeholder</h2>
          <p className="mb-card__body">
            When settings ship, they will use this route and layout. No Fetcher settings are
            migrated in this pass.
          </p>
        </article>
      </div>
    </div>
  );
}
