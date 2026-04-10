import { Link } from "react-router-dom";
import { PageLoading } from "../../components/shared/page-loading";
import { useFetcherOperationalOverviewQuery } from "../../lib/fetcher/queries";
import { isHttpErrorFromApi, isLikelyNetworkFailure } from "../../lib/api/error-guards";
import type { ActivityEventItem } from "../../lib/api/types";

function FetcherStatusRow({ label, value }: { label: string; value: string }) {
  return (
    <>
      <dt className="mm-dash-kv-label">{label}</dt>
      <dd className="mm-dash-kv-value">{value}</dd>
    </>
  );
}

export function FetcherPage() {
  const overview = useFetcherOperationalOverviewQuery();

  if (overview.isPending) {
    return <PageLoading label="Loading Fetcher status" />;
  }

  if (overview.isError) {
    const err = overview.error;
    return (
      <div className="mm-page">
        <header className="mm-page__intro">
          <p className="mm-page__eyebrow">MediaMop</p>
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

  const {
    mediamop_version,
    connection,
    status_label,
    status_detail,
    probe_persisted_24h,
    probe_failure_window_days,
    recent_probe_failures,
    latest_probe_event,
    recent_probe_events,
  } = overview.data;
  const lastProbeText = latest_probe_event ? formatEventTime(latest_probe_event) : "No probe event recorded yet";

  return (
    <div className="mm-page">
      <header className="mm-page__intro">
        <p className="mm-page__eyebrow">MediaMop</p>
        <h1 className="mm-page__title">Fetcher</h1>
        <p className="mm-page__subtitle">
          Read-only operational view: live <code className="mm-dash-code">/healthz</code> probe plus throttled
          history in the activity log when you open this page.
        </p>
        <p className="mm-page__lead">
          No scheduler, queue browser, or settings controls here — only status for the separate Fetcher app.
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
          <FetcherStatusRow label="MediaMop API" value={mediamop_version} />
          <FetcherStatusRow label="Integration" value={connection.configured ? "URL configured" : "Not configured"} />
          {connection.target_display ? <FetcherStatusRow label="Target" value={connection.target_display} /> : null}
          {connection.configured ? (
            <FetcherStatusRow
              label="Reachable"
              value={
                connection.reachable === true ? "Yes" : connection.reachable === false ? "No" : "—"
              }
            />
          ) : null}
          {connection.http_status != null ? (
            <FetcherStatusRow label="HTTP status" value={String(connection.http_status)} />
          ) : null}
          {connection.latency_ms != null ? (
            <FetcherStatusRow label="Probe latency" value={`${connection.latency_ms} ms`} />
          ) : null}
          {connection.fetcher_app ? <FetcherStatusRow label="Service name" value={connection.fetcher_app} /> : null}
          {connection.fetcher_version ? (
            <FetcherStatusRow label="Fetcher version" value={connection.fetcher_version} />
          ) : null}
          {connection.detail ? <FetcherStatusRow label="Note" value={connection.detail} /> : null}
        </dl>
      </section>

      <section
        className="mm-card mm-dash-card mm-fetcher-module-surface mt-4"
        aria-labelledby="mm-fetcher-log-snapshot-heading"
      >
        <h2 id="mm-fetcher-log-snapshot-heading" className="mm-card__title">
          24-hour log snapshot
        </h2>
        <p className="mm-card__body mm-card__body--tight">
          Counts are <strong>persisted</strong> probe rows in MediaMop only (15-minute throttle can under-count
          actual <code className="mm-dash-code">/healthz</code> checks).
        </p>
        <dl className="mm-dash-kv">
          <FetcherStatusRow
            label="Window"
            value={`Last ${probe_persisted_24h.window_hours} hours`}
          />
          <FetcherStatusRow label="OK rows" value={String(probe_persisted_24h.persisted_ok)} />
          <FetcherStatusRow label="Failed rows" value={String(probe_persisted_24h.persisted_failed)} />
        </dl>
      </section>

      <section
        className="mm-card mm-dash-card mm-fetcher-module-surface mt-4"
        aria-labelledby="mm-fetcher-failures-heading"
      >
        <h2 id="mm-fetcher-failures-heading" className="mm-card__title">
          Recent health check failures
        </h2>
        <p className="mm-card__body mm-card__body--tight">
          Up to five persisted <code className="mm-dash-code">fetcher.probe_failed</code> rows from the last{" "}
          {probe_failure_window_days} days (newest first). Same throttle rules as other probe history; not every
          failed reachability attempt is guaranteed to appear.
        </p>
        {recent_probe_failures.length > 0 ? (
          <ul className="mt-3 space-y-2 text-sm">
            {recent_probe_failures.map((event) => (
              <li
                key={event.id}
                className="rounded-md border border-[var(--mm-border)] border-l-4 border-l-amber-600/80 p-2"
              >
                <p className="font-medium text-[var(--mm-text1)]">{event.title}</p>
                <p className="text-[var(--mm-text2)]">
                  {event.event_type} — {formatEventTime(event)}
                </p>
                {event.detail ? <p className="text-[var(--mm-text3)]">{event.detail}</p> : null}
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-3 text-sm text-[var(--mm-text3)]">No persisted failures in this window.</p>
        )}
        <p className="mm-card__body mm-card__body--tight mt-3">
          <Link to="/app/activity" className="text-[var(--mm-accent)] underline-offset-2 hover:underline">
            Open Activity
          </Link>{" "}
          for the full persisted event list.
        </p>
      </section>

      <section
        className="mm-card mm-dash-card mm-fetcher-module-surface mt-4"
        aria-labelledby="mm-fetcher-operational-heading"
      >
        <h2 id="mm-fetcher-operational-heading" className="mm-card__title">
          Operational signal
        </h2>
        <p className="mm-card__body mm-card__body--tight">
          Persisted probe rows (same target + outcome within 15 minutes are collapsed).{" "}
          <strong>{status_label}</strong>: {status_detail}
        </p>
        <dl className="mm-dash-kv">
          <FetcherStatusRow label="Latest probe event" value={lastProbeText} />
          <FetcherStatusRow label="Recent probe events" value={String(recent_probe_events.length)} />
        </dl>
        {recent_probe_events.length > 0 ? (
          <ul className="mt-3 space-y-2 text-sm">
            {recent_probe_events.map((event) => (
              <li key={event.id} className="rounded-md border border-[var(--mm-border)] p-2">
                <p className="font-medium text-[var(--mm-text1)]">{event.title}</p>
                <p className="text-[var(--mm-text2)]">
                  {event.event_type} - {formatEventTime(event)}
                </p>
                {event.detail ? <p className="text-[var(--mm-text3)]">{event.detail}</p> : null}
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-3 text-sm text-[var(--mm-text3)]">No persisted probe events yet.</p>
        )}
      </section>
    </div>
  );
}

function formatEventTime(item: ActivityEventItem): string {
  const d = new Date(item.created_at);
  if (Number.isNaN(d.valueOf())) {
    return item.created_at;
  }
  return d.toLocaleString();
}
