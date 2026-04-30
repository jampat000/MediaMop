import { FormEvent, useState } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import { AuthBrandStack } from "../../components/brand/auth-brand-stack";
import { ApiEntryError } from "../../components/shared/api-entry-error";
import { PageLoading } from "../../components/shared/page-loading";
import {
  useBootstrapStatusQuery,
  useLoginMutation,
  useMeQuery,
} from "../../lib/auth/queries";

function EyeIcon() {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="20"
      height="20"
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden
    >
      <path
        d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12Z"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx="12" cy="12" r="3" stroke="currentColor" strokeWidth="2" />
    </svg>
  );
}

function EyeOffIcon() {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="20"
      height="20"
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden
    >
      <path
        d="M10.73 5.08A10.4 10.4 0 0 1 12 5c7 0 10 7 10 7a13.2 13.2 0 0 1-1.67 2.68M6.61 6.61A13.5 13.5 0 0 0 2 12s4 7 10 7c1.38 0 2.65-.21 3.78-.6M9.88 9.88a3 3 0 1 0 4.24 4.24"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="m2 2 20 20"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
      />
    </svg>
  );
}

export function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const fromSetup = Boolean(
    (location.state as { fromSetup?: boolean } | null)?.fromSetup,
  );
  const sessionExpired =
    new URLSearchParams(location.search).get("session") === "expired";
  const me = useMeQuery();
  const boot = useBootstrapStatusQuery();
  const login = useLoginMutation();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);

  if (me.isPending || boot.isPending) {
    return <PageLoading />;
  }
  if (me.data) {
    return <Navigate to="/app" replace />;
  }
  if (me.isError || boot.isError) {
    const err = boot.error ?? me.error;
    return (
      <main className="mm-auth-body" id="mm-main-content" tabIndex={-1}>
        <div className="mm-auth-frame">
          <AuthBrandStack />
          <div className="mm-auth-card">
            <ApiEntryError error={err} />
          </div>
        </div>
      </main>
    );
  }

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    try {
      await login.mutateAsync({ username: username.trim(), password });
      navigate("/app", { replace: true });
    } catch {
      /* mutation error surfaces below */
    }
  };

  return (
    <main className="mm-auth-body" id="mm-main-content" tabIndex={-1}>
      <div className="mm-auth-frame">
        <AuthBrandStack />
        <div className="mm-auth-card">
          <p className="mm-auth-eyebrow">MediaMop</p>
          <h1 className="mm-auth-title">Sign in</h1>
          <p className="mm-auth-lead">
            Server-side session sign-in — MediaMop keeps your sign-in on the
            backend, not browser storage.
          </p>

          {fromSetup ? (
            <p className="mm-auth-banner mm-auth-banner--ok" role="status">
              Initial account created. Sign in with the credentials you chose.
            </p>
          ) : null}
          {sessionExpired ? (
            <p className="mm-auth-banner" role="status">
              Your session expired. Sign in again to keep using MediaMop.
            </p>
          ) : null}

          {boot.data?.bootstrap_allowed ? (
            <p className="mm-auth-lead mt-2">
              First-time setup?{" "}
              <Link
                to="/setup"
                className="font-medium text-[var(--mm-accent-bright)] hover:underline"
              >
                Create the admin account
              </Link>
              .
            </p>
          ) : null}

          <form
            data-testid="login-form"
            className="mm-auth-form mt-4"
            onSubmit={onSubmit}
          >
            <label className="mm-auth-label" htmlFor="login-user">
              Username
            </label>
            <input
              id="login-user"
              data-testid="login-username"
              name="username"
              autoComplete="username"
              className="mm-auth-input"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
            />
            <label className="mm-auth-label" htmlFor="login-pass">
              Password
            </label>
            <div className="mm-auth-password-field">
              <input
                id="login-pass"
                data-testid="login-password"
                name="password"
                type={showPassword ? "text" : "password"}
                autoComplete="current-password"
                className="mm-auth-input mm-auth-input--password-toggle"
                value={password}
                onChange={(e) => {
                  const next = e.target.value;
                  setPassword(next);
                  if (next === "") setShowPassword(false);
                }}
                required
              />
              <button
                type="button"
                className="mm-auth-password-toggle"
                data-testid="login-password-toggle"
                aria-label={showPassword ? "Hide password" : "Show password"}
                title={showPassword ? "Hide password" : "Show password"}
                onClick={() => setShowPassword((v) => !v)}
              >
                {showPassword ? <EyeOffIcon /> : <EyeIcon />}
              </button>
            </div>
            {login.isError ? (
              <p className="mm-auth-banner" role="alert">
                {login.error instanceof Error
                  ? login.error.message
                  : "Sign-in failed."}
              </p>
            ) : null}
            <button
              type="submit"
              data-testid="login-submit"
              className="mm-auth-submit"
              disabled={login.isPending}
            >
              {login.isPending ? "Signing in…" : "Sign in"}
            </button>
          </form>
        </div>
      </div>
    </main>
  );
}
