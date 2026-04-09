import { FormEvent, useState } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import { AuthBrandStack } from "../../components/brand/auth-brand-stack";
import { ApiEntryError } from "../../components/shared/api-entry-error";
import { PageLoading } from "../../components/shared/page-loading";
import { useBootstrapStatusQuery, useLoginMutation, useMeQuery } from "../../lib/auth/queries";

export function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const fromSetup = Boolean(
    (location.state as { fromSetup?: boolean } | null)?.fromSetup,
  );
  const me = useMeQuery();
  const boot = useBootstrapStatusQuery();
  const login = useLoginMutation();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");

  if (me.isPending || boot.isPending) {
    return <PageLoading />;
  }
  if (me.data) {
    return <Navigate to="/app" replace />;
  }
  if (me.isError || boot.isError) {
    const err = boot.error ?? me.error;
    return (
      <main className="mb-auth-body" id="mb-main-content" tabIndex={-1}>
        <div className="mb-auth-frame">
          <AuthBrandStack />
          <div className="mb-auth-card">
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
    <main className="mb-auth-body" id="mb-main-content" tabIndex={-1}>
      <div className="mb-auth-frame">
        <AuthBrandStack />
        <div className="mb-auth-card">
          <p className="mb-auth-eyebrow">MediaMop</p>
          <h1 className="mb-auth-title">Sign in</h1>
          <p className="mb-auth-lead">Session authentication — your account stays on the server.</p>

          {fromSetup ? (
            <p className="mb-auth-banner mb-auth-banner--ok" role="status">
              Initial account created. Sign in with the credentials you chose.
            </p>
          ) : null}

          {boot.data?.bootstrap_allowed ? (
            <p className="mb-auth-lead mt-2">
              First-time setup?{" "}
              <Link to="/setup" className="font-medium text-[var(--mb-accent-bright)] hover:underline">
                Create the admin account
              </Link>
              .
            </p>
          ) : null}

          <form data-testid="login-form" className="mb-auth-form mt-4" onSubmit={onSubmit}>
            <label className="mb-auth-label" htmlFor="login-user">
              Username
            </label>
            <input
              id="login-user"
              data-testid="login-username"
              name="username"
              autoComplete="username"
              className="mb-auth-input"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
            />
            <label className="mb-auth-label" htmlFor="login-pass">
              Password
            </label>
            <input
              id="login-pass"
              data-testid="login-password"
              name="password"
              type="password"
              autoComplete="current-password"
              className="mb-auth-input"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
            {login.isError ? (
              <p className="mb-auth-banner" role="alert">
                {login.error instanceof Error ? login.error.message : "Sign-in failed."}
              </p>
            ) : null}
            <button
              type="submit"
              data-testid="login-submit"
              className="mb-auth-submit"
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
