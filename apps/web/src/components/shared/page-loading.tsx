export function PageLoading({ label = "Loading…" }: { label?: string }) {
  return (
    <main className="mb-auth-body" id="mb-main-content" tabIndex={-1}>
      <div className="mb-loading" role="status" aria-live="polite">
        <div className="mb-loading-dots" aria-hidden="true">
          <span className="mb-loading-dot" />
          <span className="mb-loading-dot" />
          <span className="mb-loading-dot" />
        </div>
        <span>{label}</span>
      </div>
    </main>
  );
}
