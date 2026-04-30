import {
  httpStatusFromApiError,
  isHttpErrorFromApi,
  isLikelyNetworkFailure,
  isLikelyViteProxyUpstreamDown,
} from "../../lib/api/error-guards";

/**
 * Honest copy for bootstrap/auth gate failures (root, login, setup).
 * Network failures ≠ HTTP 503 from a live API (e.g. database not configured).
 */
export function ApiEntryError({ error }: { error: unknown }) {
  if (isLikelyNetworkFailure(error) || isLikelyViteProxyUpstreamDown(error)) {
    return (
      <>
        <h1 className="mm-auth-title mm-auth-title--alert">
          Cannot reach the API
        </h1>
        {isLikelyViteProxyUpstreamDown(error) ? (
          <p className="mm-auth-lead">
            With Vite alone, <code className="text-[0.85em]">/api</code> is
            proxied to the API port. If nothing is listening there, the dev
            server often returns <strong>HTTP 500</strong> — that means the API
            is not up, not a handler bug inside MediaMop.
          </p>
        ) : null}
        <p className="mm-auth-lead">
          <strong>Easiest:</strong> from{" "}
          <code className="text-[0.85em]">apps/web</code>, run{" "}
          <code className="rounded bg-[rgba(0,0,0,0.35)] px-1.5 py-0.5 text-[0.85em] text-[var(--mm-text)]">
            npm run dev
          </code>{" "}
          — it starts the API, waits until{" "}
          <code className="text-[0.85em]">GET /health</code> succeeds, then
          starts Vite (ports in{" "}
          <code className="text-[0.85em]">scripts/dev-ports.json</code>
          ). If you still see this screen, the API never became ready: read the
          same terminal for Python errors (venv,{" "}
          <code className="text-[0.85em]">MEDIAMOP_SESSION_SECRET</code>,
          migrations).
        </p>
        <p className="mm-auth-lead">
          <strong>Alternative:</strong> two terminals from the repo root —{" "}
          <code className="rounded bg-[rgba(0,0,0,0.35)] px-1.5 py-0.5 text-[0.85em] text-[var(--mm-text)]">
            .\scripts\dev-backend.ps1
          </code>{" "}
          then{" "}
          <code className="rounded bg-[rgba(0,0,0,0.35)] px-1.5 py-0.5 text-[0.85em] text-[var(--mm-text)]">
            .\scripts\dev-web.ps1
          </code>
          . If the API is already running, use{" "}
          <code className="rounded bg-[rgba(0,0,0,0.35)] px-1.5 py-0.5 text-[0.85em] text-[var(--mm-text)]">
            npm run dev:web
          </code>{" "}
          in <code className="text-[0.85em]">apps/web</code> for Vite only.
        </p>
        <p className="mm-auth-lead">
          During <code className="text-[0.85em]">vite dev</code>, the app always
          uses relative{" "}
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
          <h1 className="mm-auth-title mm-auth-title--caution">
            API is running but not ready
          </h1>
          <p className="mm-auth-lead">
            Auth routes need a migrated SQLite database under{" "}
            <code className="rounded bg-[rgba(0,0,0,0.35)] px-1.5 py-0.5 text-[0.85em] text-[var(--mm-text)]">
              MEDIAMOP_HOME
            </code>{" "}
            (optional{" "}
            <code className="rounded bg-[rgba(0,0,0,0.35)] px-1.5 py-0.5 text-[0.85em] text-[var(--mm-text)]">
              MEDIAMOP_DB_PATH
            </code>
            ), plus{" "}
            <code className="rounded bg-[rgba(0,0,0,0.35)] px-1.5 py-0.5 text-[0.85em] text-[var(--mm-text)]">
              MEDIAMOP_SESSION_SECRET
            </code>
            . Run{" "}
            <code className="rounded bg-[rgba(0,0,0,0.35)] px-1.5 py-0.5 text-[0.85em] text-[var(--mm-text)]">
              .\scripts\dev-migrate.ps1
            </code>{" "}
            from the repo root (or{" "}
            <code className="rounded bg-[rgba(0,0,0,0.35)] px-1.5 py-0.5 text-[0.85em] text-[var(--mm-text)]">
              alembic upgrade head
            </code>{" "}
            from <code className="text-[0.85em]">apps/backend</code> with{" "}
            <code className="text-[0.85em]">PYTHONPATH=src</code>
            ), then restart the backend. See{" "}
            <code className="text-[0.85em]">
              apps/backend/.env.example
            </code> and{" "}
            <code className="text-[0.85em]">docs/local-development.md</code>.
          </p>
          <p className="mm-auth-lead">
            <code className="rounded bg-[rgba(0,0,0,0.35)] px-1.5 py-0.5 text-[0.85em] text-[var(--mm-text)]">
              GET /health
            </code>{" "}
            can still return 200 while{" "}
            <code className="text-[0.85em]">/api/v1</code> returns 503 if
            migrations, session secret, or the database path are not ready.
          </p>
        </>
      );
    }
    return (
      <>
        <h1 className="mm-auth-title mm-auth-title--alert">
          Unexpected API error
        </h1>
        <p className="mm-auth-lead">
          The server responded but the request failed
          {status != null ? ` (HTTP ${status})` : ""}. Check the backend
          terminal for details.
        </p>
        {error instanceof Error ? (
          <p className="mm-auth-lead font-mono text-sm text-[var(--mm-text3)]">
            {error.message}
          </p>
        ) : null}
      </>
    );
  }

  return (
    <>
      <h1 className="mm-auth-title mm-auth-title--alert">
        Cannot load the app
      </h1>
      <p className="mm-auth-lead">
        Something went wrong talking to the API. From{" "}
        <code className="text-[0.85em]">apps/web</code> try{" "}
        <code className="rounded bg-[rgba(0,0,0,0.35)] px-1.5 py-0.5 text-[0.85em] text-[var(--mm-text)]">
          npm run dev
        </code>{" "}
        (API + Vite), or confirm the backend is running, then reload.
      </p>
      {error instanceof Error ? (
        <p className="mm-auth-lead font-mono text-sm text-[var(--mm-text3)]">
          {error.message}
        </p>
      ) : null}
    </>
  );
}
