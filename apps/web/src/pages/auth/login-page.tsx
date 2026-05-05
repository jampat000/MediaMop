import { FormEvent, useId, useState } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import { AuthBrandStack } from "../../components/brand/auth-brand-stack";
import { ApiEntryError } from "../../components/shared/api-entry-error";
import { PageLoading } from "../../components/shared/page-loading";
import {
  httpStatusFromApiError,
  isLikelyNetworkFailure,
} from "../../lib/api/error-guards";
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
  const searchParams = new URLSearchParams(location.search);
  const fromSetup =
    Boolean((location.state as { fromSetup?: boolean } | null)?.fromSetup) ||
    searchParams.get("bootstrap") === "created";
  const sessionExpired = searchParams.get("session") === "expired";
  const me = useMeQuery();
  const boot = useBootstrapStatusQuery();
  const login = useLoginMutation();
  const fieldId = useId();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [trustedDevice, setTrustedDevice] = useState(true);
  const [showPassword, setShowPassword] = useState(false);

  if (me.isPending || boot.isPending) {
    return <PageLoading />;
  }
  if (me.data) {
    return <Navigate to="/" replace />;
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
  if (boot.data?.bootstrap_allowed && !fromSetup) {
    return <Navigate to="/setup" replace />;
  }

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    try {
      await login.mutateAsync({
        username: username.trim(),
        password,
        trustedDevice,
      });
      navigate("/", { replace: true });
    } catch {
      /* mutation error surfaces below */
    }
  };

  const loginUserId = `${fieldId}-user`;
  const loginPasswordId = `${fieldId}-pass`;
  const loginErrorMessage = (() => {
    if (!login.isError) {
      return null;
    }
    const status = httpStatusFromApiError(login.error);
    if (status === 400 || status === 401) {
      return login.error instanceof Error
        ? login.error.message
        : "Sign-in failed.";
    }
    if (
      isLikelyNetworkFailure(login.error) ||
      status === 500 ||
      status === 503
    ) {
      console.error("MediaMop login failed against the backend.", login.error);
      return "Sign-in failed. Check that the MediaMop server is running.";
    }
    console.error(
      "MediaMop login failed with an unexpected error.",
      login.error,
    );
    return "Sign-in failed. Check that the MediaMop server is running.";
  })();

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
            <label className="mm-auth-label" htmlFor={loginUserId}>
              Username
            </label>
            <input
              id={loginUserId}
              data-testid="login-username"
              name="username"
              autoComplete="username"
              className="mm-auth-input"
              autoFocus
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
            />
            <label className="mm-auth-label" htmlFor={loginPasswordId}>
              Password
            </label>
            <div className="mm-auth-password-field">
              <input
                id={loginPasswordId}
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
            {loginErrorMessage ? (
              <p className="mm-auth-banner" role="alert">
                {loginErrorMessage}
              </p>
            ) : null}
            <label className="flex items-start gap-3 rounded-md border border-[var(--mm-line)] bg-[var(--mm-surface-2)] px-3 py-3 text-sm text-[var(--mm-text2)]">
              <input
                type="checkbox"
                className="mt-0.5 h-4 w-4"
                aria-label="Trust this device"
                checked={trustedDevice}
                onChange={(e) => setTrustedDevice(e.target.checked)}
              />
              <span>
                <span className="block font-medium text-[var(--mm-text1)]">
                  Trust this device
                </span>
                <span className="block">
                  Keep this browser signed in longer on this machine.
                </span>
              </span>
            </label>
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
