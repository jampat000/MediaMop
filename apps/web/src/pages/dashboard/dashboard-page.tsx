import { PageLoading } from "../../components/shared/page-loading";
import { useActivityStreamInvalidation } from "../../lib/activity/use-activity-stream-invalidation";
import type { ActivityEventItem } from "../../lib/api/types";
import { useMeQuery } from "../../lib/auth/queries";
import { dashboardStatusKey, useDashboardStatusQuery } from "../../lib/dashboard/queries";
import { useSuiteSettingsQuery } from "../../lib/suite/queries";
import { isHttpErrorFromApi, isLikelyNetworkFailure } from "../../lib/api/error-guards";

function formatEventTs(iso: string): string {
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) {
      return iso;
    }
    return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(d);
  } catch {
    return iso;
  }
}

function eventOneLine(ev: ActivityEventItem): string {
  const t = formatEventTs(ev.created_at);
  const tail = ev.detail ? ` · ${ev.detail}` : "";
  return `${ev.title}${tail} (${t})`;
}

function StatusRow({ label, value }: { label: string; value: string }) {
  return (
    <>
      <dt className="mm-dash-kv-label">{label}</dt>
      <dd className="mm-dash-kv-value">{value}</dd>
    </>
  );
}

export function DashboardPage() {
  useActivityStreamInvalidation(dashboardStatusKey);
  const me = useMeQuery();
  const dash = useDashboardStatusQuery();
  const suite = useSuiteSettingsQuery();

  if (dash.isPending) {
    return <PageLoading label="Loading dashboard" />;
  }

  if (dash.isError) {
    const err = dash.error;
    return (
      <div className="mm-page">
        <header className="mm-page__intro">
          <p className="mm-page__eyebrow">Overview</p>
          <h1 className="mm-page__title">Dashboard</h1>
          <p className="mm-page__lead">
            {isLikelyNetworkFailure(err)
              ? "Could not reach the MediaMop API. Check that the backend is running."
              : isHttpErrorFromApi(err)
                ? "The server refused this request. Sign in again or check API logs."
                : "Something went wrong loading dashboard status."}
          </p>
        </header>
        {err instanceof Error ? (
          <p className="mm-page__lead font-mono text-sm text-[var(--mm-text3)]">{err.message}</p>
        ) : null}
      </div>
    );
  }

  const { system, fetcher, scope_note, activity_summary } = dash.data;

  return (
    <div className="mm-page">
      <header className="mm-page__intro">
        <p className="mm-page__eyebrow">Overview</p>
        <h1 className="mm-page__title">Dashboard</h1>
        <p className="mm-page__subtitle">
          Read-only snapshot of MediaMop and your linked Fetcher instance. Nothing here runs jobs or changes
          settings.
        </p>
        <p className="mm-page__lead">
          Signed in as <strong className="font-semibold text-[var(--mm-text)]">{me.data?.username}</strong>
          {me.data?.role ? (
            <>
              {" "}
              <span className="text-[var(--mm-text3)]">({me.data.role})</span>
            </>
          ) : null}
          . {scope_note}
        </p>
      </header>

      {suite.data?.signed_in_home_notice?.trim() ? (
        <section
          className="mm-card mb-4 max-w-3xl border border-[var(--mm-border)] bg-[var(--mm-card-bg)]"
          aria-label="Home notice from settings"
          data-testid="suite-home-notice"
        >
          <p className="mm-card__body whitespace-pre-wrap text-sm leading-relaxed text-[var(--mm-text)]">
            {suite.data.signed_in_home_notice.trim()}
          </p>
        </section>
      ) : null}

      <div className="mm-dash-grid" data-testid="shell-ready">
        <section className="mm-card mm-dash-card" aria-labelledby="mm-dash-system-heading">
          <h2 id="mm-dash-system-heading" className="mm-card__title">
            System
          </h2>
          <p className="mm-card__body mm-card__body--tight">MediaMop API process and environment.</p>
          <dl className="mm-dash-kv">
            <StatusRow label="API version" value={system.api_version} />
            <StatusRow label="Environment" value={system.environment} />
            <StatusRow label="Healthy" value={system.healthy ? "Yes" : "No"} />
          </dl>
        </section>

        <section className="mm-card mm-dash-card" aria-labelledby="mm-dash-fetcher-heading">
          <h2 id="mm-dash-fetcher-heading" className="mm-card__title">
            Fetcher
          </h2>
          <p className="mm-card__body mm-card__body--tight">
            Read-only check against Fetcher&apos;s <code className="mm-dash-code">/healthz</code> when a base URL
            is configured. Scheduler state, queues, and activity are not shown here yet.
          </p>
          <dl className="mm-dash-kv">
            <StatusRow label="Integration" value={fetcher.configured ? "URL configured" : "Not configured"} />
            {fetcher.target_display ? <StatusRow label="Target" value={fetcher.target_display} /> : null}
            {fetcher.configured ? (
              <StatusRow
                label="Reachable"
                value={
                  fetcher.reachable === true
                    ? "Yes"
                    : fetcher.reachable === false
                      ? "No"
                      : "—"
                }
              />
            ) : null}
            {fetcher.http_status != null ? (
              <StatusRow label="HTTP status" value={String(fetcher.http_status)} />
            ) : null}
            {fetcher.latency_ms != null ? (
              <StatusRow label="Probe latency" value={`${fetcher.latency_ms} ms`} />
            ) : null}
            {fetcher.fetcher_app ? <StatusRow label="Service name" value={fetcher.fetcher_app} /> : null}
            {fetcher.fetcher_version ? <StatusRow label="Fetcher version" value={fetcher.fetcher_version} /> : null}
            {fetcher.detail ? <StatusRow label="Note" value={fetcher.detail} /> : null}
          </dl>
        </section>

        <section
          className="mm-card mm-dash-card mm-dash-activity-summary"
          aria-labelledby="mm-dash-activity-summary-heading"
        >
          <h2 id="mm-dash-activity-summary-heading" className="mm-card__title">
            Recent activity
          </h2>
          <p className="mm-card__body mm-card__body--tight">
            From persisted events (last 24 hours and latest probe). Open Activity for the full list.
          </p>
          <dl className="mm-dash-kv">
            <StatusRow label="Events (24h)" value={String(activity_summary.events_last_24h)} />
            <StatusRow
              label="Latest"
              value={activity_summary.latest ? eventOneLine(activity_summary.latest) : "—"}
            />
            <StatusRow
              label="Last Fetcher check"
              value={
                activity_summary.last_fetcher_probe
                  ? eventOneLine(activity_summary.last_fetcher_probe)
                  : "—"
              }
            />
          </dl>
        </section>
      </div>
    </div>
  );
}
