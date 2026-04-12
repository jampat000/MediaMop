import { useEffect, useState } from "react";
import { PageLoading } from "../../components/shared/page-loading";
import { isHttpErrorFromApi, isLikelyNetworkFailure } from "../../lib/api/error-guards";
import { useMeQuery } from "../../lib/auth/queries";
import {
  useSuiteSecurityOverviewQuery,
  useSuiteSettingsQuery,
  useSuiteSettingsSaveMutation,
} from "../../lib/suite/queries";

function canEditSuiteGlobal(role: string | undefined): boolean {
  return role === "operator" || role === "admin";
}

type TabId = "global" | "security";

function tabButtonClass(active: boolean): string {
  return [
    "rounded-md border px-3 py-1.5 text-sm font-medium transition-colors",
    active
      ? "border-[var(--mm-accent)] bg-[var(--mm-accent)]/15 text-[var(--mm-text)]"
      : "border-[var(--mm-border)] bg-transparent text-[var(--mm-text2)] hover:bg-[var(--mm-card-bg)]",
  ].join(" ");
}

/** Central suite settings: Global (saved in-app) and Security (read-only startup snapshot). */
export function SettingsPage() {
  const me = useMeQuery();
  const settingsQ = useSuiteSettingsQuery();
  const securityQ = useSuiteSecurityOverviewQuery();
  const save = useSuiteSettingsSaveMutation();

  const [tab, setTab] = useState<TabId>("global");
  const [productName, setProductName] = useState("");
  const [homeNotice, setHomeNotice] = useState("");

  useEffect(() => {
    if (!settingsQ.data) {
      return;
    }
    setProductName(settingsQ.data.product_display_name ?? "");
    setHomeNotice(settingsQ.data.signed_in_home_notice ?? "");
  }, [settingsQ.data]);

  const editable = canEditSuiteGlobal(me.data?.role);

  const dirty =
    settingsQ.data !== undefined &&
    (productName !== (settingsQ.data.product_display_name ?? "") ||
      homeNotice !== (settingsQ.data.signed_in_home_notice ?? ""));

  const loadingAny = settingsQ.isPending || securityQ.isPending || me.isPending;

  if (loadingAny) {
    return <PageLoading label="Loading settings" />;
  }

  if (settingsQ.isError || securityQ.isError) {
    const err = settingsQ.isError ? settingsQ.error : securityQ.error;
    return (
      <div className="mm-page" data-testid="suite-settings-page">
        <header className="mm-page__intro">
          <p className="mm-page__eyebrow">System</p>
          <h1 className="mm-page__title">Settings</h1>
          <p className="mm-page__lead">
            {isLikelyNetworkFailure(err)
              ? "Could not reach the MediaMop API. Check that the backend is running."
              : isHttpErrorFromApi(err)
                ? "The server refused this request. Sign in again, then try back here."
                : "Something went wrong loading settings."}
          </p>
        </header>
      </div>
    );
  }

  if (!settingsQ.data || !securityQ.data) {
    return null;
  }

  const sec = securityQ.data;

  return (
    <div className="mm-page" data-testid="suite-settings-page">
      <header className="mm-page__intro">
        <p className="mm-page__eyebrow">System</p>
        <h1 className="mm-page__title">Settings</h1>
        <p className="mm-page__lead">
          MediaMop-wide choices that are not part of Fetcher, Refiner, Trimmer, or Subber. Integration details stay on
          their module pages.
        </p>
      </header>

      <div className="mm-page__body">
        <div className="mb-4 flex flex-wrap gap-2" role="tablist" aria-label="Settings sections">
          <button
            type="button"
            role="tab"
            aria-selected={tab === "global"}
            className={tabButtonClass(tab === "global")}
            onClick={() => setTab("global")}
          >
            Global
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={tab === "security"}
            className={tabButtonClass(tab === "security")}
            onClick={() => setTab("security")}
          >
            Security
          </button>
        </div>

        {tab === "global" ? (
          <section
            className="mm-card max-w-2xl"
            aria-labelledby="suite-global-heading"
            data-testid="suite-settings-global"
          >
            <h2 id="suite-global-heading" className="mm-card__title">
              Global
            </h2>
            <p className="mm-card__body">
              These values are stored in the app database. Saving applies right away for everyone who is signed in. You
              do <strong className="text-[var(--mm-text)]">not</strong> need to restart the server for these fields.
            </p>
            {!editable ? (
              <p className="mm-card__body text-sm text-[var(--mm-text3)]">Operators and admins can edit these fields.</p>
            ) : null}

            <div className="mm-card__body space-y-4">
              <label className="block">
                <span className="text-xs font-semibold uppercase tracking-wide text-[var(--mm-text3)]">
                  Product name
                </span>
                <input
                  className="mt-1 w-full rounded border border-[var(--mm-border)] bg-[var(--mm-input-bg)] px-2 py-1.5 text-sm text-[var(--mm-text)]"
                  value={productName}
                  disabled={!editable}
                  onChange={(e) => setProductName(e.target.value)}
                  maxLength={120}
                  autoComplete="off"
                  aria-describedby="suite-product-name-hint"
                />
                <p id="suite-product-name-hint" className="mt-1 text-xs text-[var(--mm-text3)]">
                  Shown in the sidebar and a few other places (up to 120 characters).
                </p>
              </label>

              <label className="block">
                <span className="text-xs font-semibold uppercase tracking-wide text-[var(--mm-text3)]">
                  Optional home dashboard notice
                </span>
                <textarea
                  className="mt-1 min-h-[120px] w-full rounded border border-[var(--mm-border)] bg-[var(--mm-input-bg)] px-2 py-1.5 text-sm text-[var(--mm-text)]"
                  value={homeNotice}
                  disabled={!editable}
                  onChange={(e) => setHomeNotice(e.target.value)}
                  maxLength={4000}
                  aria-describedby="suite-home-notice-hint"
                />
                <p id="suite-home-notice-hint" className="mt-1 text-xs text-[var(--mm-text3)]">
                  Short message at the top of the home dashboard for signed-in people (leave blank for none).
                </p>
              </label>

              {save.isError ? (
                <p className="text-sm text-red-300" role="alert" data-testid="suite-settings-save-error">
                  {save.error instanceof Error ? save.error.message : "Could not save."}
                </p>
              ) : null}

              {save.isSuccess && !dirty && !save.isPending ? (
                <p className="text-xs text-[var(--mm-text3)]" data-testid="suite-settings-saved-hint">
                  Saved.
                </p>
              ) : null}

              <button
                type="button"
                className="rounded-md bg-[var(--mm-accent)] px-3 py-2 text-sm font-semibold text-black disabled:opacity-50"
                disabled={!editable || !dirty || save.isPending}
                data-testid="suite-settings-save"
                onClick={() => {
                  save.reset();
                  void save.mutateAsync({
                    product_display_name: productName,
                    signed_in_home_notice: homeNotice.trim() === "" ? null : homeNotice,
                  });
                }}
              >
                {save.isPending ? "Saving…" : "Save global settings"}
              </button>
            </div>
          </section>
        ) : (
          <section
            className="mm-card max-w-2xl"
            aria-labelledby="suite-security-heading"
            data-testid="suite-settings-security"
          >
            <h2 id="suite-security-heading" className="mm-card__title">
              Security
            </h2>
            <p className="mm-card__body">{sec.restart_required_note}</p>
            <p className="mm-card__body rounded-md border border-amber-900/40 bg-amber-950/25 p-3 text-sm text-amber-100">
              Nothing on this tab can be edited in the browser. If something needs to change, update the server
              configuration file and restart the app.
            </p>

            <dl className="mm-card__body mm-dash-kv">
              <dt className="mm-dash-kv-label">Sign-in session protection</dt>
              <dd className="mm-dash-kv-value">{sec.session_signing_configured ? "On" : "Off"}</dd>

              <dt className="mm-dash-kv-label">Sign-in cookie: HTTPS only</dt>
              <dd className="mm-dash-kv-value">{sec.sign_in_cookie_https_only ? "Yes" : "No"}</dd>

              <dt className="mm-dash-kv-label">Sign-in cookie: cross-site rule</dt>
              <dd className="mm-dash-kv-value">{sec.sign_in_cookie_same_site}</dd>

              <dt className="mm-dash-kv-label">Extra HTTPS hardening for browsers</dt>
              <dd className="mm-dash-kv-value">{sec.extra_https_hardening_enabled ? "On" : "Off"}</dd>

              <dt className="mm-dash-kv-label">Failed sign-in tries before cool-down</dt>
              <dd className="mm-dash-kv-value">
                {sec.sign_in_attempt_limit} per {sec.sign_in_attempt_window_plain}
              </dd>

              <dt className="mm-dash-kv-label">First-time setup tries before cool-down</dt>
              <dd className="mm-dash-kv-value">
                {sec.first_time_setup_attempt_limit} per {sec.first_time_setup_attempt_window_plain}
              </dd>

              <dt className="mm-dash-kv-label">Browser addresses allowed to call this app</dt>
              <dd className="mm-dash-kv-value">{sec.allowed_browser_origins_count}</dd>
            </dl>
          </section>
        )}
      </div>
    </div>
  );
}
