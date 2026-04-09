import {
  httpStatusFromApiError,
  isHttpErrorFromApi,
  isLikelyNetworkFailure,
} from "../../lib/api/error-guards";

/**
 * Honest copy for bootstrap/auth gate failures (root, login, setup).
 * Network failures ≠ HTTP 503 from a live API (e.g. database not configured).
 */
export function ApiEntryError({ error }: { error: unknown }) {
  if (isLikelyNetworkFailure(error)) {
    return (
      <>
        <h1 className="mm-auth-title mm-auth-title--alert">Cannot reach the API</h1>
        <p className="mm-auth-lead">
          Start the MediaMop backend from the <strong>repository root</strong> (e.g.{" "}
          <code className="rounded bg-[rgba(0,0,0,0.35)] px-1.5 py-0.5 text-[0.85em] text-[var(--mm-text)]">
            .\scripts\dev-backend.ps1
          </code>
          ). In another terminal, run the Vite dev server (e.g.{" "}
          <code className="rounded bg-[rgba(0,0,0,0.35)] px-1.5 py-0.5 text-[0.85em] text-[var(--mm-text)]">
            .\scripts\dev-web.ps1
          </code>
          ).
        </p>
        <p className="mm-auth-lead">
          With same-origin dev, leave{" "}
          <code className="rounded bg-[rgba(0,0,0,0.35)] px-1.5 py-0.5 text-[0.85em] text-[var(--mm-text)]">
            VITE_API_BASE_URL
          </code>{" "}
          unset so the browser uses relative{" "}
          <code className="rounded bg-[rgba(0,0,0,0.35)] px-1.5 py-0.5 text-[0.85em] text-[var(--mm-text)]">
            /api/v1
          </code>{" "}
          through the Vite proxy (see{" "}
          <code className="rounded bg-[rgba(0,0,0,0.35)] px-1.5 py-0.5 text-[0.85em] text-[var(--mm-text)]">
            apps/web/.env.example
          </code>
          ). Ports:{" "}
          <code className="rounded bg-[rgba(0,0,0,0.35)] px-1.5 py-0.5 text-[0.85em] text-[var(--mm-text)]">
            scripts/dev-ports.json
          </code>
          .
        </p>
      </>
    );
  }

  if (isHttpErrorFromApi(error)) {
    const status = httpStatusFromApiError(error);
    if (status === 503) {
      return (
        <>
          <h1 className="mm-auth-title mm-auth-title--caution">API is running but not ready</h1>
          <p className="mm-auth-lead">
            Auth routes need PostgreSQL. Set{" "}
            <code className="rounded bg-[rgba(0,0,0,0.35)] px-1.5 py-0.5 text-[0.85em] text-[var(--mm-text)]">
              MEDIAMOP_DATABASE_URL
            </code>{" "}
            and{" "}
            <code className="rounded bg-[rgba(0,0,0,0.35)] px-1.5 py-0.5 text-[0.85em] text-[var(--mm-text)]">
              MEDIAMOP_SESSION_SECRET
            </code>
            , run{" "}
            <code className="rounded bg-[rgba(0,0,0,0.35)] px-1.5 py-0.5 text-[0.85em] text-[var(--mm-text)]">
              alembic upgrade head
            </code>{" "}
            from <code className="text-[0.85em]">apps/backend</code>, then restart the backend. A typical{" "}
            <strong>native</strong> PostgreSQL listen address is{" "}
            <code className="rounded bg-[rgba(0,0,0,0.35)] px-1.5 py-0.5 text-[0.85em] text-[var(--mm-text)]">
              127.0.0.1:5432
            </code>
            ; optional dev-only Compose in this repo maps Postgres to host port{" "}
            <code className="rounded bg-[rgba(0,0,0,0.35)] px-1.5 py-0.5 text-[0.85em] text-[var(--mm-text)]">
              5433
            </code>{" "}
            (see <code className="text-[0.85em]">docs/local-development.md</code>).
          </p>
          <p className="mm-auth-lead">
            <code className="rounded bg-[rgba(0,0,0,0.35)] px-1.5 py-0.5 text-[0.85em] text-[var(--mm-text)]">
              GET /health
            </code>{" "}
            should still respond while the database is unset; product JSON under{" "}
            <code className="rounded bg-[rgba(0,0,0,0.35)] px-1.5 py-0.5 text-[0.85em] text-[var(--mm-text)]">
              /api/v1
            </code>{" "}
            returns 503 until the URL is set.
          </p>
        </>
      );
    }
    return (
      <>
        <h1 className="mm-auth-title mm-auth-title--alert">Unexpected API error</h1>
        <p className="mm-auth-lead">
          The server responded but the request failed
          {status != null ? ` (HTTP ${status})` : ""}. Check the backend terminal for details.
        </p>
        {error instanceof Error ? (
          <p className="mm-auth-lead font-mono text-sm text-[var(--mm-text3)]">{error.message}</p>
        ) : null}
      </>
    );
  }

  return (
    <>
      <h1 className="mm-auth-title mm-auth-title--alert">Cannot load the app</h1>
      <p className="mm-auth-lead">
        Something went wrong talking to the API. Check that the backend is running and try again.
      </p>
      {error instanceof Error ? (
        <p className="mm-auth-lead font-mono text-sm text-[var(--mm-text3)]">{error.message}</p>
      ) : null}
    </>
  );
}
