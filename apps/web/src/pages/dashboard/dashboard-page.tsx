import { Link } from "react-router-dom";
import { PageLoading } from "../../components/shared/page-loading";
import { useActivityRecentQuery, activityRecentKey } from "../../lib/activity/queries";
import { useActivityStreamInvalidation } from "../../lib/activity/use-activity-stream-invalidation";
import type { ActivityEventItem } from "../../lib/api/types";
import { isHttpErrorFromApi, isLikelyNetworkFailure } from "../../lib/api/error-guards";
import { dashboardStatusKey, useDashboardStatusQuery } from "../../lib/dashboard/queries";
import {
  useFetcherArrOperatorSettingsQuery,
  fetcherArrOperatorSettingsQueryKey,
} from "../../lib/fetcher/arr-operator-settings/queries";
import {
  useFailedImportQueueAttentionSnapshotQuery,
  failedImportQueueAttentionSnapshotQueryKey,
} from "../../lib/fetcher/failed-imports/queries";
import { useFetcherJobsInspectionQuery, fetcherJobsInspectionQueryKey } from "../../lib/fetcher/jobs-inspection/queries";
import { mmActionButtonClass } from "../../lib/ui/mm-control-roles";

type ModuleKey = "fetcher" | "refiner" | "pruner" | "subber";
type ModuleStatus = "Healthy" | "Attention needed" | "Review needed" | "Active" | "Setup needed";

type ModuleCardData = {
  key: ModuleKey;
  name: string;
  status: ModuleStatus;
  summary: string;
  tvLine: string;
  moviesLine: string;
  actionLabel: string;
  actionTo: string;
};

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

function shortLastActivity(items: ActivityEventItem[]): string {
  if (items.length === 0) {
    return "No recent activity";
  }
  const ev = items[0];
  const moduleLabel = ev.module ? `${ev.module[0].toUpperCase()}${ev.module.slice(1)}` : "Module";
  const text = `${ev.title} ${ev.detail || ""}`.toLowerCase();
  let summary = "Update recorded";
  if (ev.module === "fetcher" && /manual|check|queue|queued|enqueue/.test(text)) {
    summary = /already/.test(text) ? "Failed-import check already queued" : "Manual failed-import check requested";
  } else if (ev.module === "fetcher" && /failed import|failed-import/.test(text)) {
    summary = "Failed-import status updated";
  } else if (ev.module === "auth") {
    summary = "Sign-in activity updated";
  } else if (ev.module === "settings") {
    summary = "Settings updated";
  }
  return `${moduleLabel}: ${summary} · ${formatEventTs(ev.created_at)}`;
}

function matchesAttentionText(ev: ActivityEventItem): boolean {
  const text = `${ev.title} ${ev.detail || ""}`.toLowerCase();
  return /(failed|error|needs|review|missing|stopped|follow-up)/.test(text);
}

function moduleEvents(items: ActivityEventItem[], module: ModuleKey): ActivityEventItem[] {
  return items.filter((i) => i.module === module);
}

function deriveGenericModuleCard(module: Exclude<ModuleKey, "fetcher">, items: ActivityEventItem[]): ModuleCardData {
  const events = moduleEvents(items, module);
  const hasAttention = events.some(matchesAttentionText);
  const status: ModuleStatus = hasAttention ? "Review needed" : events.length > 0 ? "Active" : "Healthy";
  const tvMentions = events.filter((e) => /(tv|episode|show)/i.test(`${e.title} ${e.detail || ""}`)).length;
  const movieMentions = events.filter((e) => /(movie|movies|film)/i.test(`${e.title} ${e.detail || ""}`)).length;
  const title = module[0].toUpperCase() + module.slice(1);
  return {
    key: module,
    name: title,
    status,
    summary:
      status === "Review needed"
        ? "Recent items may need review."
        : events.length > 0
          ? "Module activity is currently visible."
          : "No recent module activity.",
    tvLine: tvMentions > 0 ? `${tvMentions} TV updates in recent signals` : "TV: No recent signal",
    moviesLine: movieMentions > 0 ? `${movieMentions} movie updates in recent signals` : "Movies: No recent signal",
    actionLabel: `Open ${title}`,
    actionTo: `/app/${module}`,
  };
}

function StatusTile({ label, value }: { label: string; value: string }) {
  return (
    <section className="rounded-md border border-[var(--mm-border)] bg-[var(--mm-card-bg)] px-3 py-2.5">
      <p className="text-xs font-medium uppercase tracking-wide text-[var(--mm-text3)]">{label}</p>
      <p className="mt-1 text-sm font-semibold text-[var(--mm-text1)]">{value}</p>
    </section>
  );
}

export function DashboardPage() {
  useActivityStreamInvalidation(dashboardStatusKey);
  useActivityStreamInvalidation(activityRecentKey);
  useActivityStreamInvalidation(fetcherArrOperatorSettingsQueryKey);
  useActivityStreamInvalidation(failedImportQueueAttentionSnapshotQueryKey);
  useActivityStreamInvalidation(fetcherJobsInspectionQueryKey("pending"));
  useActivityStreamInvalidation(fetcherJobsInspectionQueryKey("leased"));

  const dash = useDashboardStatusQuery();
  const recent = useActivityRecentQuery();
  const arr = useFetcherArrOperatorSettingsQuery();
  const attention = useFailedImportQueueAttentionSnapshotQuery();
  const pendingJobs = useFetcherJobsInspectionQuery("pending");
  const runningJobs = useFetcherJobsInspectionQuery("leased");

  if (dash.isPending) {
    return <PageLoading label="Loading dashboard" />;
  }
  if (dash.isError) {
    const err = dash.error;
    return (
      <div className="mm-page">
        <header className="mm-page__intro">
          <h1 className="mm-page__title">Dashboard</h1>
          <p className="mm-page__lead">
            {isLikelyNetworkFailure(err)
              ? "Could not reach the MediaMop API. Check that the backend is running."
              : isHttpErrorFromApi(err)
                ? "The server refused this request. Sign in again or check API logs."
                : "Something went wrong loading dashboard status."}
          </p>
        </header>
      </div>
    );
  }

  const tvNeeds = attention.data?.tv_shows.needs_attention_count;
  const moviesNeeds = attention.data?.movies.needs_attention_count;
  const tvNeedsCount = typeof tvNeeds === "number" ? tvNeeds : null;
  const moviesNeedsCount = typeof moviesNeeds === "number" ? moviesNeeds : null;
  const fetcherTvConfigured = Boolean(arr.data?.sonarr_server_configured);
  const fetcherMoviesConfigured = Boolean(arr.data?.radarr_server_configured);
  const fetcherNeedsAttentionCount = (tvNeedsCount !== null && tvNeedsCount > 0 ? 1 : 0) + (moviesNeedsCount !== null && moviesNeedsCount > 0 ? 1 : 0);
  const activeJobsCount = (pendingJobs.data?.jobs.length ?? 0) + (runningJobs.data?.jobs.length ?? 0);
  const fetcherSetupIncomplete = !fetcherTvConfigured || !fetcherMoviesConfigured;
  const fetcherStatus: ModuleStatus =
    fetcherSetupIncomplete
      ? "Setup needed"
      : fetcherNeedsAttentionCount > 0
      ? "Attention needed"
      : activeJobsCount > 0
        ? "Active"
        : dash.data.fetcher.reachable === false
          ? "Review needed"
          : "Healthy";

  const fetcherCard: ModuleCardData = {
    key: "fetcher",
    name: "Fetcher",
    status: fetcherStatus,
    summary:
      fetcherSetupIncomplete
        ? "Finish Sonarr and Radarr setup to enable full checks."
        : fetcherNeedsAttentionCount > 0
        ? "Failed-import queue attention is needed."
        : activeJobsCount > 0
          ? "Search and cleanup work is active."
          : "Search and cleanup signals are currently clear.",
    tvLine: !fetcherTvConfigured
      ? "TV: Sonarr connection is not set up."
      : tvNeedsCount === null
        ? "TV: Queue check is unavailable right now."
        : tvNeedsCount > 0
          ? `TV: ${tvNeedsCount} failed imports need review`
          : "TV: All clear",
    moviesLine: !fetcherMoviesConfigured
      ? "Movies: Radarr connection is not set up."
      : moviesNeedsCount === null
        ? "Movies: Queue check is unavailable right now."
        : moviesNeedsCount > 0
          ? `Movies: ${moviesNeedsCount} failed imports need review`
          : "Movies: All clear",
    actionLabel: "Open Fetcher",
    actionTo: "/app/fetcher",
  };

  const recentItems = recent.data?.items ?? [];
  const moduleCards: ModuleCardData[] = [
    fetcherCard,
    deriveGenericModuleCard("refiner", recentItems),
    deriveGenericModuleCard("pruner", recentItems),
    deriveGenericModuleCard("subber", recentItems),
  ];
  const modulesNeedingAttentionTotal = moduleCards.filter(
    (m) => m.status === "Attention needed" || m.status === "Review needed" || m.status === "Setup needed",
  ).length;
  const nonFetcherActiveCount = moduleCards.filter((m) => m.key !== "fetcher" && m.status === "Active").length;

  const overallStatus =
    !dash.data.system.healthy || dash.data.fetcher.reachable === false
      ? "Review needed"
      : modulesNeedingAttentionTotal > 0
        ? "Attention needed"
        : activeJobsCount > 0
          ? "Active"
          : "Healthy";
  const lastActivity = shortLastActivity(recentItems);

  const attentionItems: string[] = [];
  if (!fetcherTvConfigured) {
    attentionItems.push("Fetcher: Set up Sonarr");
  }
  if (!fetcherMoviesConfigured) {
    attentionItems.push("Fetcher: Set up Radarr");
  }
  if (tvNeedsCount !== null && tvNeedsCount > 0) {
    attentionItems.push(`Fetcher: ${tvNeedsCount} TV failed imports still need attention`);
  }
  if (moviesNeedsCount !== null && moviesNeedsCount > 0) {
    attentionItems.push(`Fetcher: ${moviesNeedsCount} movie failed imports still need attention`);
  }
  for (const m of moduleCards.filter((x) => x.key !== "fetcher" && x.status === "Review needed")) {
    attentionItems.push(`${m.name}: ${m.summary}`);
  }

  return (
    <div className="mm-page" data-testid="dashboard-page">
      <header className="mm-page__intro">
        <h1 className="mm-page__title">Dashboard</h1>
        <p className="mm-page__lead">See what needs attention across MediaMop and which modules are active now.</p>
      </header>

      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4" data-testid="dashboard-status-strip">
        <StatusTile label="Overall status" value={overallStatus} />
        <StatusTile
          label="Modules needing attention"
          value={
            modulesNeedingAttentionTotal === 0
              ? "None detected"
              : `${modulesNeedingAttentionTotal} module${modulesNeedingAttentionTotal === 1 ? "" : "s"} need attention`
          }
        />
        <StatusTile label="Active jobs" value={activeJobsCount > 0 ? String(activeJobsCount) : "None running"} />
        <StatusTile label="Last activity" value={lastActivity} />
      </section>

      <section className="mt-5 grid gap-4 sm:grid-cols-2 xl:grid-cols-4" data-testid="dashboard-module-cards">
        {moduleCards.map((m) => (
          <article key={m.key} className="mm-card mm-dash-card flex h-full flex-col gap-3">
            <div className="flex items-start justify-between gap-2">
              <h2 className="text-base font-semibold text-[var(--mm-text1)]">{m.name}</h2>
              <span className="rounded border border-[var(--mm-border)] bg-[var(--mm-surface2)] px-2 py-0.5 text-xs text-[var(--mm-text2)]">
                {m.status}
              </span>
            </div>
            <p className="text-sm text-[var(--mm-text2)]">{m.summary}</p>
            <p className="text-sm text-[var(--mm-text2)]">{m.tvLine}</p>
            <p className="text-sm text-[var(--mm-text2)]">{m.moviesLine}</p>
            <div className="mt-auto pt-1">
              <Link to={m.actionTo} className={mmActionButtonClass({ variant: "secondary" })}>
                {m.actionLabel}
              </Link>
            </div>
          </article>
        ))}
      </section>

      <section className="mm-card mm-dash-card mt-6" data-testid="dashboard-needs-attention">
        <h2 className="mm-card__title">Needs attention</h2>
        <div className="mm-card__body mm-card__body--tight space-y-2 text-sm text-[var(--mm-text2)]">
          {attentionItems.length > 0 ? (
            attentionItems.map((line) => <p key={line}>{line}</p>)
          ) : (
            <p>No module attention signals are currently detected.</p>
          )}
        </div>
      </section>

      <section className="mm-card mm-dash-card mt-6" data-testid="dashboard-active-work">
        <h2 className="mm-card__title">Active work</h2>
        <div className="mm-card__body mm-card__body--tight space-y-2 text-sm text-[var(--mm-text2)]">
          <p>{activeJobsCount === 0 ? "Fetcher: No active jobs" : `Fetcher: ${runningJobs.data?.jobs.length ?? 0} running now, ${pendingJobs.data?.jobs.length ?? 0} queued.`}</p>
          <p>
            Other modules:{" "}
            {nonFetcherActiveCount > 0
              ? `${nonFetcherActiveCount} active module signals`
              : "No active work detected"}
            .
          </p>
        </div>
      </section>
    </div>
  );
}
