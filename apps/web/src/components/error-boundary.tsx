import { Component, type ErrorInfo, type ReactNode } from "react";
import { isRouteErrorResponse, useRouteError } from "react-router-dom";

type ErrorBoundaryState = {
  error: Error | null;
};

type ErrorBoundaryProps = {
  children: ReactNode;
  fallback?: ReactNode | ((error: Error) => ReactNode);
};

export class ErrorBoundary extends Component<
  ErrorBoundaryProps,
  ErrorBoundaryState
> {
  state: ErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error("MediaMop UI crashed", error, info.componentStack);
  }

  render(): ReactNode {
    const { error } = this.state;
    if (error) {
      const { fallback } = this.props;
      if (typeof fallback === "function") {
        return fallback(error);
      }
      return fallback ?? <AppErrorScreen error={error} />;
    }
    return this.props.children;
  }
}

export function AppErrorScreen({
  error,
  onReload,
}: {
  error: Error;
  onReload?: () => void;
}) {
  const reload = onReload ?? (() => window.location.reload());

  return (
    <main className="mm-auth-body" id="mm-main-content" tabIndex={-1}>
      <div className="mm-auth-frame">
        <aside className="mm-sidebar" aria-label="MediaMop recovery navigation">
          <div className="mm-sidebar-brand">
            <span className="mm-brand-kicker">MediaMop</span>
            <strong>Recovery mode</strong>
          </div>
          <nav className="mm-nav-list" aria-label="Unavailable sections">
            <span className="mm-nav-link">Dashboard</span>
            <span className="mm-nav-link">Refiner</span>
            <span className="mm-nav-link">Pruner</span>
            <span className="mm-nav-link">Subber</span>
            <span className="mm-nav-link">Settings</span>
          </nav>
        </aside>
        <section className="mm-auth-card" aria-labelledby="app-error-title">
          <p className="mm-section-kicker">Application recovery</p>
          <h1 id="app-error-title">Something went wrong</h1>
          <p className="mm-muted">
            MediaMop hit a screen error before it could finish loading this
            view. Reloading usually clears a temporary browser state problem.
          </p>
          <button
            className="mm-btn mm-btn-primary"
            type="button"
            onClick={reload}
          >
            Reload MediaMop
          </button>
          <details className="mm-error-details">
            <summary>Show technical details</summary>
            <pre>{error.message || "Unknown error"}</pre>
          </details>
        </section>
      </div>
    </main>
  );
}

function routeErrorToError(error: unknown): Error {
  if (error instanceof Error) {
    return error;
  }
  if (isRouteErrorResponse(error)) {
    return new Error(
      error.statusText || error.data || `Route error ${error.status}`,
    );
  }
  if (typeof error === "string" && error.trim()) {
    return new Error(error);
  }
  return new Error("Unknown route error");
}

export function RouteErrorScreen() {
  const routeError = useRouteError();
  return <AppErrorScreen error={routeErrorToError(routeError)} />;
}
