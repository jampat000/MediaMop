import { FormEvent, useState } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { AuthBrandStack } from "../../components/brand/auth-brand-stack";
import { ApiEntryError } from "../../components/shared/api-entry-error";
import { PageLoading } from "../../components/shared/page-loading";
import { useBootstrapMutation, useBootstrapStatusQuery, useMeQuery } from "../../lib/auth/queries";

export function SetupPage() {
  const navigate = useNavigate();
  const me = useMeQuery();
  const boot = useBootstrapStatusQuery();
  const bootstrap = useBootstrapMutation();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");

  if (me.isPending || boot.isPending) {
    return <PageLoading label="Checking setup…" />;
  }

  if (me.data) {
    return <Navigate to="/app" replace />;
  }

  if (boot.isError) {
    return (
      <main className="mb-auth-body" id="mb-main-content" tabIndex={-1}>
        <div className="mb-auth-frame">
          <AuthBrandStack />
          <div className="mb-auth-card">
            <ApiEntryError error={boot.error} />
            <p className="mb-auth-footer-link !mt-4">
              <Link to="/login">Back to sign in</Link>
            </p>
          </div>
        </div>
      </main>
    );
  }

  if (!boot.data?.bootstrap_allowed) {
    return <Navigate to="/login" replace />;
  }

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    try {
      await bootstrap.mutateAsync({ username: username.trim(), password });
      navigate("/login", { replace: true, state: { fromSetup: true } });
    } catch {
      /* surfaced below */
    }
  };

  return (
    <main className="mb-auth-body" id="mb-main-content" tabIndex={-1}>
      <div className="mb-auth-frame">
        <AuthBrandStack />
        <div className="mb-auth-card">
          <p className="mb-auth-eyebrow">First run</p>
          <h1 className="mb-auth-title">Create admin</h1>
          <p className="mb-auth-lead">
            This workspace has no administrator yet. Choose credentials for the initial account —
            afterward this step is locked.
          </p>

          <form data-testid="setup-form" className="mb-auth-form" onSubmit={onSubmit}>
            <label className="mb-auth-label" htmlFor="setup-user">
              Admin username
            </label>
            <input
              id="setup-user"
              data-testid="setup-username"
              name="username"
              autoComplete="username"
              className="mb-auth-input"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
              maxLength={64}
            />
            <label className="mb-auth-label" htmlFor="setup-pass">
              Password (min. 8 characters)
            </label>
            <input
              id="setup-pass"
              data-testid="setup-password"
              name="password"
              type="password"
              autoComplete="new-password"
              className="mb-auth-input"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              minLength={8}
              maxLength={512}
            />
            {bootstrap.isError ? (
              <p className="mb-auth-banner" role="alert">
                {bootstrap.error instanceof Error ? bootstrap.error.message : "Setup failed."}
              </p>
            ) : null}
            <button
              type="submit"
              data-testid="setup-submit"
              className="mb-auth-submit"
              disabled={bootstrap.isPending}
            >
              {bootstrap.isPending ? "Creating…" : "Create admin account"}
            </button>
          </form>

          <p className="mb-auth-footer-link">
            Already have an account? <Link to="/login">Sign in</Link>
          </p>
        </div>
      </div>
    </main>
  );
}
