/** Honest placeholder — real route, no product settings logic yet. */

export function SettingsPlaceholder() {
  return (
    <div className="mm-page">
      <header className="mm-page__intro">
        <p className="mm-page__eyebrow">Account</p>
        <h1 className="mm-page__title">Settings</h1>
        <p className="mm-page__lead">
          This page exists so navigation and the shell behave like the shipping product. Account,
          integrations, and module preferences are not built here yet.
        </p>
      </header>
      <div className="mm-page__body">
        <article className="mm-card">
          <h2 className="mm-card__title">Placeholder</h2>
          <p className="mm-card__body">
            When settings ship, they will use this route and layout. No Fetcher settings are
            migrated in this pass.
          </p>
        </article>
      </div>
    </div>
  );
}
