import { PageLoading } from "../../components/shared/page-loading";
import { useDashboardStatusQuery } from "../../lib/dashboard/queries";
import { isHttpErrorFromApi, isLikelyNetworkFailure } from "../../lib/api/error-guards";

function FetcherStatusRow({ label, value }: { label: string; value: string }) {
  return (
    <>
      <dt className="mm-dash-kv-label">{label}</dt>
      <dd className="mm-dash-kv-value">{value}</dd>
    </>
  );
}

export function FetcherPage() {
  const dash = useDashboardStatusQuery();

  if (dash.isPending) {
    return <PageLoading label="Loading Fetcher status" />;
  }

  if (dash.isError) {
    const err = dash.error;
    return (
      <div className="mm-page">
        <header className="mm-page__intro">
          <p className="mm-page__eyebrow">Suite</p>
          <h1 className="mm-page__title">Fetcher</h1>
          <p className="mm-page__lead">
            {isLikelyNetworkFailure(err)
              ? "Could not reach the MediaMop API. Check that the backend is running."
              : isHttpErrorFromApi(err)
                ? "The server refused this request. Sign in again or check API logs."
                : "Could not load Fetcher status."}
          </p>
        </header>
        {err instanceof Error ? (
          <p className="mm-page__lead font-mono text-sm text-[var(--mm-text3)]">{err.message}</p>
        ) : null}
      </div>
    );
  }

  const { fetcher } = dash.data;

  return (
    <div className="mm-page">
      <header className="mm-page__intro">
        <p className="mm-page__eyebrow">Suite</p>
        <h1 className="mm-page__title">Fetcher</h1>
        <p className="mm-page__subtitle">
          Read-only bridge to the standalone Fetcher app. MediaMop only performs a configured{" "}
          <code className="mm-dash-code">/healthz</code> probe — no jobs, queues, or settings from here.
        </p>
        <p className="mm-page__lead">
          Intentionally read-only: no scheduler controls, history, or configuration surface on this page yet.
        </p>
      </header>

      <section
        className="mm-card mm-dash-card mm-fetcher-module-surface"
        aria-labelledby="mm-fetcher-status-heading"
      >
        <h2 id="mm-fetcher-status-heading" className="mm-card__title">
          Connection
        </h2>
        <p className="mm-card__body mm-card__body--tight">
          Values below come from <code className="mm-dash-code">MEDIAMOP_FETCHER_BASE_URL</code> and a single GET
          to <code className="mm-dash-code">/healthz</code> on that origin.
        </p>
        <dl className="mm-dash-kv">
          <FetcherStatusRow label="Integration" value={fetcher.configured ? "URL configured" : "Not configured"} />
          {fetcher.target_display ? <FetcherStatusRow label="Target" value={fetcher.target_display} /> : null}
          {fetcher.configured ? (
            <FetcherStatusRow
              label="Reachable"
              value={
                fetcher.reachable === true ? "Yes" : fetcher.reachable === false ? "No" : "—"
              }
            />
          ) : null}
          {fetcher.http_status != null ? (
            <FetcherStatusRow label="HTTP status" value={String(fetcher.http_status)} />
          ) : null}
          {fetcher.latency_ms != null ? (
            <FetcherStatusRow label="Probe latency" value={`${fetcher.latency_ms} ms`} />
          ) : null}
          {fetcher.fetcher_app ? <FetcherStatusRow label="Fetcher app" value={fetcher.fetcher_app} /> : null}
          {fetcher.fetcher_version ? (
            <FetcherStatusRow label="Fetcher version" value={fetcher.fetcher_version} />
          ) : null}
          {fetcher.detail ? <FetcherStatusRow label="Note" value={fetcher.detail} /> : null}
        </dl>
      </section>
    </div>
  );
}
