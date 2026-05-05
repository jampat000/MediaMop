import { FormEvent, useState } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { AuthBrandStack } from "../../components/brand/auth-brand-stack";
import { ApiEntryError } from "../../components/shared/api-entry-error";
import { PageLoading } from "../../components/shared/page-loading";
import {
  useBootstrapMutation,
  useBootstrapStatusQuery,
  useMeQuery,
} from "../../lib/auth/queries";

export function SetupPage() {
  const navigate = useNavigate();
  const me = useMeQuery();
  const boot = useBootstrapStatusQuery();
  const bootstrap = useBootstrapMutation();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [validationError, setValidationError] = useState<string | null>(null);

  if (me.isPending || boot.isPending) {
    return <PageLoading label="Checking setup..." />;
  }

  if (me.data) {
    return <Navigate to="/" replace />;
  }

  if (boot.isError) {
    return (
      <main className="mm-auth-body" id="mm-main-content" tabIndex={-1}>
        <div className="mm-auth-frame">
          <AuthBrandStack />
          <div className="mm-auth-card">
            <ApiEntryError error={boot.error} />
            <p className="mm-auth-footer-link !mt-4">
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
    const trimmedUsername = username.trim();
    if (!trimmedUsername) {
      setValidationError("Admin username is required.");
      return;
    }
    if (password.length < 8) {
      setValidationError("Password must be at least 8 characters.");
      return;
    }
    setValidationError(null);
    try {
      await bootstrap.mutateAsync({ username: trimmedUsername, password });
      navigate("/login?bootstrap=created", { replace: true });
    } catch {
      /* surfaced below */
    }
  };

  return (
    <main className="mm-auth-body" id="mm-main-content" tabIndex={-1}>
      <div className="mm-auth-frame">
        <AuthBrandStack />
        <div className="mm-auth-card">
          <p className="mm-auth-eyebrow">First run</p>
          <h1 className="mm-auth-title">Create admin</h1>
          <p className="mm-auth-lead">
            This workspace has no administrator yet. Choose credentials for the
            initial account. After you sign in, MediaMop will run the first-run
            setup wizard.
          </p>

          <form
            data-testid="setup-form"
            className="mm-auth-form"
            onSubmit={onSubmit}
          >
            <label className="mm-auth-label" htmlFor="setup-user">
              Admin username
            </label>
            <input
              id="setup-user"
              data-testid="setup-username"
              name="username"
              autoComplete="username"
              className="mm-auth-input"
              value={username}
              onChange={(e) => {
                setUsername(e.target.value);
                if (validationError) {
                  setValidationError(null);
                }
              }}
              required
              maxLength={64}
            />
            <label className="mm-auth-label" htmlFor="setup-pass">
              Password (min. 8 characters)
            </label>
            <input
              id="setup-pass"
              data-testid="setup-password"
              name="password"
              type="password"
              autoComplete="new-password"
              className="mm-auth-input"
              value={password}
              onChange={(e) => {
                setPassword(e.target.value);
                if (validationError) {
                  setValidationError(null);
                }
              }}
              required
              minLength={8}
              maxLength={512}
            />
            {validationError ? (
              <p className="mm-auth-banner" role="alert">
                {validationError}
              </p>
            ) : null}
            {bootstrap.isError ? (
              <p className="mm-auth-banner" role="alert">
                {bootstrap.error instanceof Error
                  ? bootstrap.error.message
                  : "Setup failed."}
              </p>
            ) : null}
            <button
              type="submit"
              data-testid="setup-submit"
              className="mm-auth-submit"
              disabled={bootstrap.isPending}
            >
              {bootstrap.isPending ? "Creating..." : "Create admin account"}
            </button>
          </form>

          <p className="mm-auth-footer-link">
            Already have an account? <Link to="/login">Sign in</Link>
          </p>
        </div>
      </div>
    </main>
  );
}
