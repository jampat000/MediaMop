import { Link } from "react-router-dom";
import { PageLoading } from "../../components/shared/page-loading";
import { useFetcherOperationalOverviewQuery } from "../../lib/fetcher/queries";
import { isHttpErrorFromApi, isLikelyNetworkFailure } from "../../lib/api/error-guards";
import type { ActivityEventItem } from "../../lib/api/types";
import { FetcherAutomationSummaryStrip } from "./fetcher-automation-summary";
import { FetcherFailedImportsWorkspace } from "./fetcher-failed-imports-workspace";

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

  return (
    <div className="mm-page">
      <header className="mm-page__intro">
        <p className="mm-page__eyebrow">MediaMop</p>
        <h1 className="mm-page__title">Fetcher</h1>
        <p className="mm-page__subtitle">
          Fetcher handles failed imports in <strong>Radarr</strong> and <strong>Sonarr</strong> and shows whether your
          Fetcher service answered on recent checks.
        </p>
      </header>

      <FetcherAutomationSummaryStrip />

      <FetcherFailedImportsWorkspace />

      {overview.isPending ? (
        <PageLoading label="Loading Fetcher reachability" />
      ) : overview.isError ? (
        <FetcherOverviewError err={overview.error} />
      ) : (
        <FetcherOperationalOverviewSections data={overview.data} />
      )}
    </div>
  );
}

function FetcherOverviewError({ err }: { err: unknown }) {
  return (
    <div className="mm-page__intro">
      <p className="mm-page__lead">
        {isLikelyNetworkFailure(err)
          ? "Could not reach the MediaMop API. Check that the backend is running."
          : isHttpErrorFromApi(err)
            ? "The server refused this request. Sign in again or check API logs."
            : "Could not load Fetcher reachability."}
      </p>
      {err instanceof Error ? (
        <p className="mm-page__lead font-mono text-sm text-[var(--mm-text3)]">{err.message}</p>
      ) : null}
    </div>
  );
}

function FetcherOperationalOverviewSections({
  data,
}: {
  data: NonNullable<ReturnType<typeof useFetcherOperationalOverviewQuery>["data"]>;
}) {
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
  } = data;
  const lastProbeText = latest_probe_event ? formatEventTime(latest_probe_event) : "No probe event recorded yet";

  return (
    <>
      <header className="mm-page__intro mt-10 border-t border-[var(--mm-border)] pt-8">
        <h2 className="mm-page__title text-xl sm:text-2xl">Service checks</h2>
        <p className="mm-page__subtitle">
          Recent answers from your Fetcher service.{" "}
          <Link to="/app/activity" className="text-[var(--mm-accent)] underline-offset-2 hover:underline">
            Activity
          </Link>{" "}
          for more.
        </p>
      </header>

      <section
        className="mm-card mm-dash-card mm-fetcher-module-surface mt-4"
        aria-labelledby="mm-fetcher-status-heading"
      >
        <h2 id="mm-fetcher-status-heading" className="mm-card__title">
          Last check
        </h2>
        <p className="mm-card__body mm-card__body--tight text-sm text-[var(--mm-text3)]">
          Target URL is set on the MediaMop server, not in the browser.
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
            <FetcherStatusRow label="Round-trip time" value={`${connection.latency_ms} ms`} />
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
          Checks in the last day
        </h2>
        <p className="mm-card__body mm-card__body--tight text-sm text-[var(--mm-text3)]">
          Counts are what MediaMop saved (the server may merge rapid repeats).
        </p>
        <dl className="mm-dash-kv">
          <FetcherStatusRow label="Window" value={`Last ${probe_persisted_24h.window_hours} hours`} />
          <FetcherStatusRow label="OK" value={String(probe_persisted_24h.persisted_ok)} />
          <FetcherStatusRow label="Failed" value={String(probe_persisted_24h.persisted_failed)} />
        </dl>
      </section>

      <section
        className="mm-card mm-dash-card mm-fetcher-module-surface mt-4"
        aria-labelledby="mm-fetcher-failures-heading"
      >
        <h2 id="mm-fetcher-failures-heading" className="mm-card__title">
          Recent failed checks
        </h2>
        <p className="mm-card__body mm-card__body--tight text-sm text-[var(--mm-text3)]">
          Up to five saved failures from the last {probe_failure_window_days} days, newest first. Not every miss is
          listed.
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
          <p className="mt-3 text-sm text-[var(--mm-text3)]">None in this window.</p>
        )}
      </section>

      <section
        className="mm-card mm-dash-card mm-fetcher-module-surface mt-4"
        aria-labelledby="mm-fetcher-operational-heading"
      >
        <h2 id="mm-fetcher-operational-heading" className="mm-card__title">
          Summary
        </h2>
        <p className="mm-card__body mm-card__body--tight">
          <strong>{status_label}</strong>: {status_detail}
        </p>
        <dl className="mm-dash-kv">
          <FetcherStatusRow label="Latest event" value={lastProbeText} />
          <FetcherStatusRow label="Events shown" value={String(recent_probe_events.length)} />
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
          <p className="mt-3 text-sm text-[var(--mm-text3)]">No recent events yet.</p>
        )}
      </section>
    </>
  );
}

function formatEventTime(item: ActivityEventItem): string {
  const d = new Date(item.created_at);
  if (Number.isNaN(d.valueOf())) {
    return item.created_at;
  }
  return d.toLocaleString();
}
