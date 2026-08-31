import { PageLoading } from "../components/shared/page-loading";

/** Route-level fallback keeps the page geometry and announces navigation progress. */
export function AppHydrateFallback() {
  return (
    <div className="mm-app-layout" data-testid="app-hydrate-fallback">
      <aside className="mm-sidebar mm-sidebar--fallback" aria-hidden="true">
        <div className="mm-sidebar-fallback-mark" />
        <div className="mm-sidebar-fallback-lines" />
      </aside>
      <main className="mm-main" id="mm-main-content" tabIndex={-1}>
        <div className="mm-main-inner">
          <PageLoading label="Loading MediaMop" />
        </div>
      </main>
    </div>
  );
}
