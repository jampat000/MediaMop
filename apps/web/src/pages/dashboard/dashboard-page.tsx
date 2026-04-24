import { Link } from "react-router-dom";
import { PageLoading } from "../../components/shared/page-loading";
import { activityRecentKey, useActivityRecentQuery } from "../../lib/activity/queries";
import { useActivityStreamInvalidation } from "../../lib/activity/use-activity-stream-invalidation";
import type { ActivityEventItem } from "../../lib/api/types";
import { isHttpErrorFromApi, isLikelyNetworkFailure } from "../../lib/api/error-guards";
import { dashboardStatusKey, useDashboardStatusQuery } from "../../lib/dashboard/queries";
import { usePrunerInstancesQuery, usePrunerJobsInspectionQuery, usePrunerOverviewStatsQuery } from "../../lib/pruner/queries";
import { useRefinerJobsInspectionQuery } from "../../lib/refiner/jobs-inspection/queries";
import { useRefinerOverviewStatsQuery, useRefinerPathSettingsQuery } from "../../lib/refiner/queries";
import { useSubberJobsQuery, useSubberOverviewQuery, useSubberProvidersQuery, useSubberSettingsQuery } from "../../lib/subber/subber-queries";
import { useSuiteMetricsQuery } from "../../lib/suite/queries";
import { mmActionButtonClass } from "../../lib/ui/mm-control-roles";
import { useAppDateFormatter } from "../../lib/ui/mm-format-date";

type ModuleKey = "refiner" | "pruner" | "subber";
type ModuleStatus = "Healthy" | "Review needed" | "Active";

type ModuleMetric = {
  label: string;
  value: string;
  detail?: string;
};

type ModuleCardData = {
  key: ModuleKey;
  name: string;
  status: ModuleStatus;
  summary: string;
  metrics: ModuleMetric[];
  facts: string[];
  actionLabel: string;
  actionTo: string;
};

type GlobalJobRow = {
  key: string;
  module: string;
  status: string;
  title: string;
  detail: string;
  updatedAt: string;
};

function shortLastActivity(items: ActivityEventItem[], fmt: (iso: string) => string): string {
  if (items.length === 0) return "No recent activity";
  const ev = items[0];
  return `${ev.title} - ${fmt(ev.created_at)}`;
}

function healthTone(status: ModuleStatus): string {
  if (status === "Review needed") return "border-amber-400/30 bg-amber-400/10 text-amber-100";
  if (status === "Active") return "border-sky-400/30 bg-sky-400/10 text-sky-100";
  return "border-emerald-500/30 bg-emerald-500/10 text-emerald-100";
}

function statusFromSignals(attention: boolean, active: boolean): ModuleStatus {
  if (attention) return "Review needed";
  if (active) return "Active";
  return "Healthy";
}

function formatCount(value: number): string {
  if (!Number.isFinite(value)) return "0";
  return value.toLocaleString();
}

function formatBytesCompact(value: number): string {
  const abs = Math.abs(value);
  const units = ["B", "KB", "MB", "GB", "TB"];
  let size = abs;
  let unitIndex = 0;
  while (size >= 1024 && unitIndex < units.length - 1) {
    size /= 1024;
    unitIndex += 1;
  }
  const decimals = size >= 100 || unitIndex === 0 ? 0 : size >= 10 ? 1 : 2;
  const text = `${size.toFixed(decimals)} ${units[unitIndex]}`;
  return value < 0 ? `-${text}` : text;
}

function formatPercent(value: number): string {
  if (!Number.isFinite(value)) return "0%";
  return `${value.toFixed(1)}%`;
}

function describeNetSizeChange(bytes: number, percent: number): string {
  if (!Number.isFinite(bytes) || bytes === 0) return "No net size change";
  if (bytes > 0) return `Saved ${formatBytesCompact(bytes)} (${formatPercent(percent)})`;
  return `Grew by ${formatBytesCompact(Math.abs(bytes))} (${formatPercent(Math.abs(percent))})`;
}

function MetricCard({ label, value, detail }: { label: string; value: string; detail?: string }) {
  return (
    <section className="rounded-lg border border-[var(--mm-border)] bg-[var(--mm-card-bg)] px-4 py-3">
      <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--mm-text3)]">{label}</p>
      <p className="mt-1 text-lg font-semibold text-[var(--mm-text1)]">{value}</p>
      {detail ? <p className="mt-1 text-xs text-[var(--mm-text3)]">{detail}</p> : null}
    </section>
  );
}

function ModuleCard({ card }: { card: ModuleCardData }) {
  return (
    <article className="mm-card mm-dash-card flex h-full flex-col gap-4">
      <div className="flex items-start justify-between gap-2">
        <h2 className="text-lg font-semibold text-[var(--mm-text1)]">{card.name}</h2>
        <span className={`rounded-full border px-2.5 py-1 text-xs font-medium ${healthTone(card.status)}`}>{card.status}</span>
      </div>
      <p className="text-sm leading-6 text-[var(--mm-text2)]">{card.summary}</p>
      <div className="grid gap-3 sm:grid-cols-2">
        {card.metrics.map((metric) => (
          <section
            key={`${card.key}-${metric.label}`}
            className="rounded-lg border border-[var(--mm-border)] bg-black/10 px-3 py-2.5"
          >
            <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--mm-text3)]">{metric.label}</p>
            <p className="mt-1 text-base font-semibold text-[var(--mm-text1)]">{metric.value}</p>
            {metric.detail ? <p className="mt-1 text-xs text-[var(--mm-text3)]">{metric.detail}</p> : null}
          </section>
        ))}
      </div>
      <div className="space-y-2 text-sm text-[var(--mm-text2)]">
        {card.facts.map((fact) => (
          <p key={`${card.key}-${fact}`}>{fact}</p>
        ))}
      </div>
      <div className="mt-auto pt-2">
        <Link to={card.actionTo} className={mmActionButtonClass({ variant: "secondary" })}>
          {card.actionLabel}
        </Link>
      </div>
    </article>
  );
}

function jobStatusLabel(status: string): string {
  switch (status) {
    case "pending":
      return "Queued";
    case "leased":
      return "Running";
    case "completed":
      return "Completed";
    case "failed":
    case "handler_ok_finalize_failed":
      return "Failed";
    default:
      return "Needs review";
  }
}

function refinerJobTitle(jobKind: string): string {
  if (jobKind === "refiner.file_remux_pass") return "Remux file";
  if (jobKind === "refiner.watched_folder_remux_scan_dispatch") return "Scan watched folders";
  if (jobKind === "refiner.work_temp_stale_sweep") return "Clean temporary files";
  if (jobKind === "refiner.failure_cleanup_sweep") return "Clean failed remux leftovers";
  return "Refiner job";
}

function prunerJobTitle(jobKind: string): string {
  if (jobKind.includes("preview")) return "Preview cleanup";
  if (jobKind.includes("apply")) return "Run cleanup";
  if (jobKind.includes("connection")) return "Check media server";
  return "Pruner job";
}

function subberJobTitle(jobKind: string): string {
  if (jobKind.includes("library_sync")) return "Sync library";
  if (jobKind.includes("library_scan")) return "Check library";
  if (jobKind.includes("search")) return "Search subtitles";
  if (jobKind.includes("upgrade")) return "Upgrade subtitles";
  if (jobKind.includes("webhook")) return "Import new file";
  return "Subber job";
}

function buildRefinerCard(args: {
  processed: number;
  failed: number;
  outputWritten: number;
  alreadyOptimized: number;
  netSpaceSavedBytes: number;
  netSpaceSavedPercent: number;
  successRatePercent: number;
  movieFolder: string | null | undefined;
  tvFolder: string | null | undefined;
}): ModuleCardData {
  const attention = !args.movieFolder && !args.tvFolder;
  const active = args.processed > 0 || args.failed > 0 || args.outputWritten > 0 || args.alreadyOptimized > 0;

  return {
    key: "refiner",
    name: "Refiner",
    status: statusFromSignals(attention || args.failed > 0, active),
    summary: attention
      ? "No watched folders are configured yet."
      : args.outputWritten > 0
        ? `Refiner wrote ${formatCount(args.outputWritten)} output ${args.outputWritten === 1 ? "file" : "files"} in the last 30 days.`
        : active
          ? "Remux activity and watched-folder processing are active."
          : "Ready. No recent remux work recorded.",
    metrics: [
      { label: "Completed jobs", value: formatCount(args.processed), detail: `Success rate ${formatPercent(args.successRatePercent)}` },
      { label: "Output written", value: formatCount(args.outputWritten), detail: `Already optimized ${formatCount(args.alreadyOptimized)}` },
      { label: "Net space saved", value: formatBytesCompact(args.netSpaceSavedBytes), detail: describeNetSizeChange(args.netSpaceSavedBytes, args.netSpaceSavedPercent) },
      { label: "Failures", value: formatCount(args.failed) },
    ],
    facts: [
      `TV watched folder: ${args.tvFolder?.trim() ? "Configured" : "Not set"}`,
      `Movies watched folder: ${args.movieFolder?.trim() ? "Configured" : "Not set"}`,
    ],
    actionLabel: "Open Refiner",
    actionTo: "/app/refiner",
  };
}

function buildPrunerCard(args: {
  enabledServers: number;
  totalServers: number;
  previewRuns: number;
  applyRuns: number;
  itemsRemoved: number;
  itemsSkipped: number;
  failedApplies: number;
}): ModuleCardData {
  const attention = args.enabledServers === 0 || args.failedApplies > 0;
  const active = args.previewRuns > 0 || args.applyRuns > 0 || args.itemsRemoved > 0;
  const reviewedItems = args.itemsRemoved + args.itemsSkipped;
  const removalRate = reviewedItems > 0 ? (args.itemsRemoved / reviewedItems) * 100.0 : 0;

  return {
    key: "pruner",
    name: "Pruner",
    status: statusFromSignals(attention, active),
    summary:
      args.enabledServers === 0
        ? "No media servers are enabled yet."
        : args.itemsRemoved > 0
          ? `Pruner removed ${formatCount(args.itemsRemoved)} library ${args.itemsRemoved === 1 ? "item" : "items"} in the last 30 days.`
          : active
            ? "Preview and cleanup work has recent activity."
            : "Ready. No recent preview or delete work recorded.",
    metrics: [
      { label: "Items removed", value: formatCount(args.itemsRemoved) },
      { label: "Cleanup runs", value: formatCount(args.applyRuns), detail: `Failed cleanups ${formatCount(args.failedApplies)}` },
      { label: "Candidates reviewed", value: formatCount(reviewedItems), detail: `Preview runs ${formatCount(args.previewRuns)}` },
      { label: "Removal rate", value: formatPercent(removalRate), detail: `${formatCount(args.itemsRemoved)} removed - ${formatCount(args.itemsSkipped)} skipped` },
    ],
    facts: [
      `Servers enabled: ${formatCount(args.enabledServers)} of ${formatCount(args.totalServers)}`,
      `Last 30 days: ${formatCount(args.previewRuns)} previews and ${formatCount(args.applyRuns)} cleanup ${args.applyRuns === 1 ? "run" : "runs"}`,
    ],
    actionLabel: "Open Pruner",
    actionTo: "/app/pruner",
  };
}

function buildSubberCard(args: {
  sonarrConfigured: boolean;
  radarrConfigured: boolean;
  enabledProviders: number;
  providerTotal: number;
  tvTracked: number;
  moviesTracked: number;
  downloaded: number;
  stillMissing: number;
  foundRecently: number;
  notFoundRecently: number;
  upgradesRecently: number;
  tvMissing: number;
  moviesMissing: number;
}): ModuleCardData {
  const attention = !args.sonarrConfigured || !args.radarrConfigured || args.enabledProviders === 0;
  const trackedTotal = args.tvTracked + args.moviesTracked;
  const active = trackedTotal > 0 || args.downloaded > 0 || args.foundRecently > 0;
  const coveredItems = Math.max(0, trackedTotal - args.stillMissing);
  const coveragePercent = trackedTotal > 0 ? (coveredItems / trackedTotal) * 100.0 : 0;

  return {
    key: "subber",
    name: "Subber",
    status: statusFromSignals(attention, active),
    summary: attention
      ? "One or more connections or providers still need setup."
      : trackedTotal > 0
        ? `Tracking ${formatCount(trackedTotal)} library ${trackedTotal === 1 ? "item" : "items"} with ${formatCount(args.stillMissing)} still missing subtitles.`
        : "Ready. No recent subtitle work recorded.",
    metrics: [
      { label: "Downloaded", value: formatCount(args.downloaded) },
      { label: "Still missing", value: formatCount(args.stillMissing) },
      { label: "Coverage", value: formatPercent(coveragePercent), detail: `${formatCount(coveredItems)} of ${formatCount(trackedTotal)} covered` },
      { label: "Found recently", value: formatCount(args.foundRecently), detail: `Not found ${formatCount(args.notFoundRecently)} - Upgrades ${formatCount(args.upgradesRecently)}` },
    ],
    facts: [
      `TV missing: ${formatCount(args.tvMissing)} - Movies missing: ${formatCount(args.moviesMissing)}`,
      `Connections: Sonarr ${args.sonarrConfigured ? "ready" : "not set"} - Radarr ${args.radarrConfigured ? "ready" : "not set"}`,
      `Providers enabled: ${formatCount(args.enabledProviders)} of ${formatCount(args.providerTotal)}`,
    ],
    actionLabel: "Open Subber",
    actionTo: "/app/subber",
  };
}

function formatRuntimeUptime(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds <= 0) return "Just started";
  const totalSeconds = Math.max(0, Math.floor(seconds));
  const days = Math.floor(totalSeconds / 86400);
  const hours = Math.floor((totalSeconds % 86400) / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  if (days > 0) return `${days}d ${hours}h`;
  if (hours > 0) return `${hours}h ${minutes}m`;
  return `${minutes}m`;
}

function formatAverageMs(value: number): string {
  if (!Number.isFinite(value) || value <= 0) return "0 ms";
  return `${value >= 100 ? value.toFixed(0) : value.toFixed(1)} ms`;
}

function httpHealthSummary(statusCounts: Record<string, number> | undefined): { value: string; detail: string } {
  const counts = statusCounts ?? {};
  const success = counts["2xx"] ?? 0;
  const redirects = counts["3xx"] ?? 0;
  const client = counts["4xx"] ?? 0;
  const server = counts["5xx"] ?? 0;
  let value = "Healthy";
  if (server > 0) value = `${server} server ${server === 1 ? "error" : "errors"}`;
  else if (client > 0) value = `${client} client ${client === 1 ? "error" : "errors"}`;
  const detail = `2xx ${success} - 3xx ${redirects} - 4xx ${client} - 5xx ${server}`;
  return { value, detail };
}

export function DashboardPage() {
  const fmt = useAppDateFormatter();
  useActivityStreamInvalidation(dashboardStatusKey);
  useActivityStreamInvalidation(activityRecentKey);

  const dash = useDashboardStatusQuery();
  const recent = useActivityRecentQuery({ limit: 20 });
  const metrics = useSuiteMetricsQuery();
  const refinerStats = useRefinerOverviewStatsQuery();
  const refinerPaths = useRefinerPathSettingsQuery();
  const refinerJobs = useRefinerJobsInspectionQuery("recent");
  const prunerStats = usePrunerOverviewStatsQuery();
  const prunerInstances = usePrunerInstancesQuery();
  const prunerJobs = usePrunerJobsInspectionQuery(12);
  const subberOverview = useSubberOverviewQuery();
  const subberSettings = useSubberSettingsQuery();
  const subberProviders = useSubberProvidersQuery();
  const subberJobs = useSubberJobsQuery(12);

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

  const recentItems = recent.data?.items ?? [];
  const refinerCard = buildRefinerCard({
    processed: refinerStats.data?.files_processed ?? 0,
    failed: refinerStats.data?.files_failed ?? 0,
    outputWritten: refinerStats.data?.output_written_count ?? 0,
    alreadyOptimized: refinerStats.data?.already_optimized_count ?? 0,
    netSpaceSavedBytes: refinerStats.data?.net_space_saved_bytes ?? 0,
    netSpaceSavedPercent: refinerStats.data?.net_space_saved_percent ?? 0,
    successRatePercent: refinerStats.data?.success_rate_percent ?? 0,
    movieFolder: refinerPaths.data?.refiner_watched_folder,
    tvFolder: refinerPaths.data?.refiner_tv_watched_folder,
  });
  const prunerCard = buildPrunerCard({
    enabledServers: prunerInstances.data?.filter((row) => row.enabled).length ?? 0,
    totalServers: prunerInstances.data?.length ?? 0,
    previewRuns: prunerStats.data?.preview_runs ?? 0,
    applyRuns: prunerStats.data?.apply_runs ?? 0,
    itemsRemoved: prunerStats.data?.items_removed ?? 0,
    itemsSkipped: prunerStats.data?.items_skipped ?? 0,
    failedApplies: prunerStats.data?.failed_applies ?? 0,
  });
  const subberCard = buildSubberCard({
    sonarrConfigured: Boolean(subberSettings.data?.sonarr_base_url?.trim() && subberSettings.data?.sonarr_api_key_set),
    radarrConfigured: Boolean(subberSettings.data?.radarr_base_url?.trim() && subberSettings.data?.radarr_api_key_set),
    enabledProviders: subberProviders.data?.filter((row) => row.enabled).length ?? 0,
    providerTotal: subberProviders.data?.length ?? 0,
    tvTracked: subberOverview.data?.tv_tracked ?? 0,
    moviesTracked: subberOverview.data?.movies_tracked ?? 0,
    downloaded: subberOverview.data?.subtitles_downloaded ?? 0,
    stillMissing: subberOverview.data?.still_missing ?? 0,
    foundRecently: subberOverview.data?.found_last_30_days ?? 0,
    notFoundRecently: subberOverview.data?.not_found_last_30_days ?? 0,
    upgradesRecently: subberOverview.data?.upgrades_last_30_days ?? 0,
    tvMissing: subberOverview.data?.tv_missing ?? 0,
    moviesMissing: subberOverview.data?.movies_missing ?? 0,
  });

  const moduleCards = [refinerCard, prunerCard, subberCard];
  const modulesNeedingAttentionTotal = moduleCards.filter((m) => m.status === "Review needed").length;
  const activeModuleCount = moduleCards.filter((m) => m.status === "Active").length;
  const overallStatus =
    !dash.data.system.healthy || modulesNeedingAttentionTotal > 0
      ? "Review needed"
      : activeModuleCount > 0
        ? "Active"
        : "Healthy";

  const attentionItems = moduleCards.filter((m) => m.status === "Review needed").map((m) => `${m.name}: ${m.summary}`);
  const activeItems = moduleCards.filter((m) => m.status === "Active").map((m) => `${m.name}: ${m.summary}`);

  const globalJobs: GlobalJobRow[] = [
    ...(refinerJobs.data?.jobs.slice(0, 4).map((job) => ({
      key: `refiner-${job.id}`,
      module: "Refiner",
      status: jobStatusLabel(job.status),
      title: refinerJobTitle(job.job_kind),
      detail: job.last_error ? job.last_error : `${refinerJobTitle(job.job_kind)} is ${jobStatusLabel(job.status).toLowerCase()}.`,
      updatedAt: job.updated_at,
    })) ?? []),
    ...(prunerJobs.data?.jobs.slice(0, 4).map((job) => ({
      key: `pruner-${job.id}`,
      module: "Pruner",
      status: jobStatusLabel(job.status),
      title: prunerJobTitle(job.job_kind),
      detail: job.last_error ? job.last_error : `${prunerJobTitle(job.job_kind)} is ${jobStatusLabel(job.status).toLowerCase()}.`,
      updatedAt: job.updated_at,
    })) ?? []),
    ...(subberJobs.data?.jobs.slice(0, 4).map((job) => ({
      key: `subber-${job.id}`,
      module: "Subber",
      status: jobStatusLabel(job.status),
      title: subberJobTitle(job.job_kind),
      detail: job.last_error ? job.last_error : `${subberJobTitle(job.job_kind)} is ${jobStatusLabel(job.status).toLowerCase()}.`,
      updatedAt: job.updated_at,
    })) ?? []),
  ]
    .sort((a, b) => b.updatedAt.localeCompare(a.updatedAt))
    .slice(0, 10);

  const runtime = metrics.data;
  const health = httpHealthSummary(runtime?.status_counts);

  return (
    <div className="mm-page" data-testid="dashboard-page">
      <header className="mm-page__intro">
        <h1 className="mm-page__title">Dashboard</h1>
        <p className="mm-page__lead">See what needs attention across MediaMop and what the modules are doing right now.</p>
      </header>

      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4" data-testid="dashboard-status-strip">
        <MetricCard label="Overall status" value={overallStatus} />
        <MetricCard
          label="Modules needing attention"
          value={modulesNeedingAttentionTotal === 0 ? "None detected" : String(modulesNeedingAttentionTotal)}
        />
        <MetricCard label="Active modules" value={activeModuleCount === 0 ? "None" : String(activeModuleCount)} />
        <MetricCard label="Last activity" value={shortLastActivity(recentItems, fmt)} />
      </section>

      <section className="mt-5 grid gap-4 xl:grid-cols-3" data-testid="dashboard-module-cards">
        {moduleCards.map((card) => (
          <ModuleCard key={card.key} card={card} />
        ))}
      </section>

      <section className="mt-6 grid gap-4 xl:grid-cols-2">
        <article className="mm-card mm-dash-card" data-testid="dashboard-needs-attention">
          <h2 className="mm-card__title">Needs attention</h2>
          <div className="mm-card__body space-y-2 text-sm text-[var(--mm-text2)]">
            {attentionItems.length > 0 ? attentionItems.map((line) => <p key={line}>{line}</p>) : <p>Nothing needs attention right now.</p>}
          </div>
        </article>
        <article className="mm-card mm-dash-card" data-testid="dashboard-active-work">
          <h2 className="mm-card__title">Active work</h2>
          <div className="mm-card__body space-y-2 text-sm text-[var(--mm-text2)]">
            {activeItems.length > 0 ? activeItems.map((line) => <p key={line}>{line}</p>) : <p>No modules are actively processing right now.</p>}
          </div>
        </article>
      </section>

      <section className="mm-card mm-dash-card mt-6" data-testid="dashboard-global-jobs">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2 className="mm-card__title">Global jobs</h2>
            <p className="mt-1 text-sm text-[var(--mm-text2)]">Recent background work across Refiner, Pruner, and Subber.</p>
          </div>
        </div>
        <div className="mm-card__body space-y-3">
          {globalJobs.length === 0 ? (
            <p className="text-sm text-[var(--mm-text2)]">No recent jobs are recorded.</p>
          ) : (
            globalJobs.map((job) => (
              <article key={job.key} className="rounded-lg border border-[var(--mm-border)] bg-black/10 p-3">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="space-y-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--mm-gold)]">{job.module}</span>
                      <span className="rounded-full border border-[var(--mm-border)] bg-[var(--mm-card-bg)] px-2 py-0.5 text-xs text-[var(--mm-text2)]">
                        {job.status}
                      </span>
                    </div>
                    <h3 className="text-sm font-semibold text-[var(--mm-text1)]">{job.title}</h3>
                    <p className="text-sm text-[var(--mm-text2)]">{job.detail}</p>
                  </div>
                  <time className="text-sm text-[var(--mm-text3)]">{fmt(job.updatedAt)}</time>
                </div>
              </article>
            ))
          )}
        </div>
      </section>

      <section className="mm-card mm-dash-card mt-6" data-testid="dashboard-runtime-health">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2 className="mm-card__title">Runtime health</h2>
            <p className="mt-1 text-sm text-[var(--mm-text2)]">Live process and request health for the running MediaMop server.</p>
          </div>
        </div>
        {metrics.isError ? (
          <div className="mm-card__body">
            <p className="rounded-md border border-red-500/40 bg-red-950/25 px-3 py-2 text-sm text-red-200" role="alert">
              {metrics.error instanceof Error ? metrics.error.message : "Could not load runtime health."}
            </p>
          </div>
        ) : (
          <div className="mm-card__body grid gap-3 md:grid-cols-2 xl:grid-cols-5">
            <MetricCard label="Uptime" value={runtime ? formatRuntimeUptime(runtime.uptime_seconds) : "Loading..."} />
            <MetricCard label="Requests handled" value={runtime ? String(runtime.total_requests) : "Loading..."} />
            <MetricCard label="Average response" value={runtime ? formatAverageMs(runtime.average_response_ms) : "Loading..."} />
            <MetricCard label="Errors logged" value={runtime ? String(runtime.error_log_count) : "Loading..."} />
            <MetricCard label="HTTP health" value={runtime ? health.value : "Loading..."} detail={runtime ? health.detail : undefined} />
          </div>
        )}
      </section>
    </div>
  );
}
