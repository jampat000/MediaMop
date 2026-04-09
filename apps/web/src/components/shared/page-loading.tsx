export function PageLoading({ label = "Loading…" }: { label?: string }) {
  return (
    <main className="mm-auth-body" id="mm-main-content" tabIndex={-1}>
      <div className="mm-loading" role="status" aria-live="polite">
        <div className="mm-loading-dots" aria-hidden="true">
          <span className="mm-loading-dot" />
          <span className="mm-loading-dot" />
          <span className="mm-loading-dot" />
        </div>
        <span>{label}</span>
      </div>
    </main>
  );
}
