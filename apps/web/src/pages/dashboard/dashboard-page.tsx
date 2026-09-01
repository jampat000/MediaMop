import { Link } from "react-router-dom";
import { PageLoading } from "../../components/shared/page-loading";
import {
  activityRecentKey,
  useActivityRecentQuery,
} from "../../lib/activity/queries";
import {
  REFINER_FILE_PROCESSING_PROGRESS_EVENT,
  RefinerFileProcessingProgressDetail,
} from "../../lib/activity/refiner-file-remux-pass-detail";
import { useActivityStreamInvalidations } from "../../lib/activity/use-activity-stream-invalidation";
import type { ActivityEventItem, DashboardStatus } from "../../lib/api/types";
import {
  isHttpErrorFromApi,
  isLikelyNetworkFailure,
} from "../../lib/api/error-guards";
import {
  dashboardStatusKey,
  useDashboardStatusQuery,
} from "../../lib/dashboard/queries";
import {
  usePrunerInstancesQuery,
  usePrunerJobsInspectionQuery,
  usePrunerOverviewStatsQuery,
} from "../../lib/pruner/queries";
import { useRefinerJobsInspectionQuery } from "../../lib/refiner/jobs-inspection/queries";
import {
  useRefinerOverviewStatsQuery,
  useRefinerPathSettingsQuery,
} from "../../lib/refiner/queries";
import { useSuitePauseQuery } from "../../lib/suite/pause-queries";
import { mmActionButtonClass } from "../../lib/ui/mm-control-roles";
import { useAppDateFormatter } from "../../lib/ui/mm-format-date";

type ModuleKey = "refiner" | "pruner";
type ModuleStatus =
  | "Healthy"
  | "Review needed"
  | "Active"
  | "Setup required"
  | "Paused";
type OperationalModule = NonNullable<DashboardStatus["modules"]>[number];

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
  nextAction: string;
  technicalDetail?: string;
  actionTo: string;
  actionLabel: string;
  updatedAt: string;
};

const DASHBOARD_LIVE_INVALIDATION_KEYS = [
  dashboardStatusKey,
  activityRecentKey,
  ["refiner"] as const,
  ["pruner"] as const,
  ["suite"] as const,
] as const;

type DashboardJobRow = {
  id: number;
  job_kind: string;
  status: string;
  last_error: string | null;
  operator_message?: string;
  next_action?: string;
  technical_detail?: string | null;
  updated_at: string;
};

type AttentionItem = {
  key: string;
  title: string;
  detail: string;
  actionTo: string;
  actionLabel: string;
};

const REFINER_FILE_REMUX_PASS_JOB_KIND = "refiner.file.remux_pass.v1";
const REFINER_DASHBOARD_JOB_KINDS = new Set([
  REFINER_FILE_REMUX_PASS_JOB_KIND,
  "refiner.candidate_gate.v1",
  "refiner.supplied_payload_evaluation.v1",
]);

function compactMetricText(
  text: string,
  maxLength = 60,
  tailLength = 22,
): string {
  const normalized = text.trim();
  if (normalized.length <= maxLength) {
    return normalized;
  }
  const tail = Math.max(12, Math.min(tailLength, maxLength - 16));
  const head = Math.max(16, maxLength - tail - 1);
  return `${normalized.slice(0, head).trimEnd()}...${normalized.slice(-tail).trimStart()}`;
}

function healthTone(status: ModuleStatus): string {
  if (status === "Review needed" || status === "Setup required")
    return "border-[var(--mm-status-warning-text)]/40 bg-[var(--mm-status-warning-bg)] text-[var(--mm-status-warning-text)]";
  if (status === "Paused")
    return "border-[var(--mm-status-info-text)]/40 bg-[var(--mm-status-info-bg)] text-[var(--mm-status-info-text)]";
  if (status === "Active")
    return "border-[var(--mm-status-info-text)]/40 bg-[var(--mm-status-info-bg)] text-[var(--mm-status-info-text)]";
  return "border-[var(--mm-status-healthy-text)]/40 bg-[var(--mm-status-healthy-bg)] text-[var(--mm-status-healthy-text)]";
}

function statusFromSignals(attention: boolean, active: boolean): ModuleStatus {
  if (attention) return "Review needed";
  if (active) return "Active";
  return "Healthy";
}

function statusFromOperationalState(state: string): ModuleStatus {
  switch (state) {
    case "setup_required":
      return "Setup required";
    case "processing":
      return "Active";
    case "paused":
      return "Paused";
    case "degraded":
      return "Review needed";
    default:
      return "Healthy";
  }
}

function moduleNeedsAttention(status: ModuleStatus): boolean {
  return (
    status === "Review needed" ||
    status === "Setup required" ||
    status === "Paused"
  );
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
  if (
    Number.isFinite(percent) &&
    (Math.abs(percent) < 0.1 || Math.abs(bytes) < 1024 * 1024)
  ) {
    return bytes > 0
      ? `Size basically unchanged (${formatBytesCompact(bytes)} saved)`
      : `Size basically unchanged (${formatBytesCompact(Math.abs(bytes))} container overhead)`;
  }
  if (bytes > 0)
    return `Saved ${formatBytesCompact(bytes)} (${formatPercent(percent)})`;
  return `Grew by ${formatBytesCompact(Math.abs(bytes))} (${formatPercent(Math.abs(percent))})`;
}

function MetricCard({
  label,
  value,
  detail,
  valueTitle,
}: {
  label: string;
  value: string;
  detail?: string;
  valueTitle?: string;
}) {
  return (
    <section className="min-w-0 rounded-lg border border-[var(--mm-border)] bg-[var(--mm-card-bg)] px-4 py-3">
      <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--mm-text3)]">
        {label}
      </p>
      <p
        className="mt-1 min-w-0 text-lg font-semibold leading-snug text-[var(--mm-text1)] [overflow-wrap:anywhere]"
        title={valueTitle ?? value}
      >
        {value}
      </p>
      {detail ? (
        <p className="mt-1 text-xs text-[var(--mm-text3)]" title={detail}>
          {detail}
        </p>
      ) : null}
    </section>
  );
}

function activityModuleLabel(module: string): string {
  const value = module.trim();
  if (!value) return "System";
  return `${value[0].toUpperCase()}${value.slice(1)}`;
}

function LiveSignal({
  item,
  fmt,
}: {
  item: ActivityEventItem;
  fmt: (iso: string) => string;
}) {
  return (
    <li className="mm-dashboard-signal">
      <span className="mm-dashboard-signal__marker" aria-hidden="true" />
      <div className="min-w-0">
        <div className="mm-dashboard-signal__meta">
          <span>{activityModuleLabel(item.module)}</span>
          <time>{fmt(item.created_at)}</time>
        </div>
        <p title={item.title}>{item.title}</p>
      </div>
    </li>
  );
}

function ModuleCard({ card }: { card: ModuleCardData }) {
  const needsAction = card.status !== "Healthy";
  return (
    <article className="mm-card mm-dash-card flex h-full flex-col gap-4">
      <div className="flex items-start justify-between gap-2">
        <h2 className="text-lg font-semibold text-[var(--mm-text1)]">
          {card.name}
        </h2>
        {needsAction ? (
          <Link
            to={card.actionTo}
            data-testid={`dashboard-${card.key}-status-link`}
            aria-label={`${card.name}: ${card.status}. Open the next action.`}
            title={`Open ${card.name} action: ${card.actionLabel}`}
            className={`rounded-full border px-2.5 py-1 text-xs font-medium transition hover:brightness-125 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--mm-accent-ring)] ${healthTone(card.status)}`}
          >
            {card.status}
          </Link>
        ) : (
          <span
            className={`rounded-full border px-2.5 py-1 text-xs font-medium ${healthTone(card.status)}`}
          >
            {card.status}
          </span>
        )}
      </div>
      <p className="text-sm leading-6 text-[var(--mm-text2)]">{card.summary}</p>
      <div className="grid gap-3 sm:grid-cols-2">
        {card.metrics.map((metric) => (
          <section
            key={`${card.key}-${metric.label}`}
            className="rounded-lg border border-[var(--mm-border)] bg-black/10 px-3 py-2.5"
          >
            <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--mm-text3)]">
              {metric.label}
            </p>
            <p className="mt-1 text-base font-semibold text-[var(--mm-text1)]">
              {metric.value}
            </p>
            {metric.detail ? (
              <p className="mt-1 text-xs text-[var(--mm-text3)]">
                {metric.detail}
              </p>
            ) : null}
          </section>
        ))}
      </div>
      <div className="space-y-2 text-sm text-[var(--mm-text2)]">
        {card.facts.map((fact) => (
          <p key={`${card.key}-${fact}`}>{fact}</p>
        ))}
      </div>
      <div className="mt-auto pt-2">
        <Link
          to={card.actionTo}
          className={mmActionButtonClass({ variant: "secondary" })}
        >
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
      return "Failed";
    case "handler_ok_finalize_failed":
      return "Needs recovery";
    default:
      return "Needs review";
  }
}

function readableLegacyJobMessage(
  module: string,
  title: string,
  status: string,
  raw: string | null,
): string {
  const value = raw?.trim() ?? "";
  const lower = value.toLowerCase();
  if (
    lower.includes("database is locked") ||
    lower.includes("database table is locked")
  ) {
    return `${module} could not save this result while another local operation was using the database.`;
  }
  if (lower.includes("not a supported refiner media")) {
    return "This file is not a supported Refiner media file for this pass.";
  }
  if (
    lower.includes("could not find this file") ||
    lower.includes("no such file")
  ) {
    return "MediaMop could not find this file under the saved watched folder.";
  }
  const withoutTechnical = value.split(/\bTechnical detail:\s*/i)[0].trim();
  if (withoutTechnical.length > 0) {
    return compactMetricText(withoutTechnical, 260, 80);
  }
  return `${title} is ${jobStatusLabel(status).toLowerCase()}.`;
}

function isDashboardVisibleRefinerJob(jobKind: string): boolean {
  return REFINER_DASHBOARD_JOB_KINDS.has(jobKind);
}

function refinerJobTitle(jobKind: string): string {
  if (jobKind === REFINER_FILE_REMUX_PASS_JOB_KIND) return "Process file";
  if (jobKind === "refiner.candidate_gate.v1") return "Check file readiness";
  if (jobKind === "refiner.supplied_payload_evaluation.v1")
    return "Check new media";
  return "Refiner job";
}

function prunerJobTitle(jobKind: string): string {
  if (jobKind.includes("preview")) return "Preview cleanup";
  if (jobKind.includes("apply")) return "Run cleanup";
  if (jobKind.includes("connection")) return "Check media server";
  return "Pruner job";
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
  operational?: OperationalModule;
}): ModuleCardData {
  const attention = !args.movieFolder && !args.tvFolder;
  const active =
    args.processed > 0 ||
    args.failed > 0 ||
    args.outputWritten > 0 ||
    args.alreadyOptimized > 0;

  const card: ModuleCardData = {
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
      {
        label: "Completed jobs",
        value: formatCount(args.processed),
        detail: `Success rate ${formatPercent(args.successRatePercent)}`,
      },
      {
        label: "Output written",
        value: formatCount(args.outputWritten),
        detail: `No-change files ${formatCount(args.alreadyOptimized)}`,
      },
      {
        label: "Net space saved",
        value: formatBytesCompact(args.netSpaceSavedBytes),
        detail: describeNetSizeChange(
          args.netSpaceSavedBytes,
          args.netSpaceSavedPercent,
        ),
      },
      { label: "Failures", value: formatCount(args.failed) },
    ],
    facts: [
      `TV watched folder: ${args.tvFolder?.trim() ? "Configured" : "Not set"}`,
      `Movies watched folder: ${args.movieFolder?.trim() ? "Configured" : "Not set"}`,
    ],
    actionLabel: "Open Refiner",
    actionTo: "/refiner",
  };
  if (args.operational) {
    card.status = statusFromOperationalState(args.operational.state);
    card.summary = args.operational.summary;
    if (card.status === "Setup required") {
      card.actionTo = args.operational.action_path;
      card.actionLabel = "Configure Refiner";
    } else if (card.status === "Review needed") {
      card.actionTo = args.operational.action_path;
      card.actionLabel = "Review Refiner";
    } else if (card.status === "Active") {
      card.actionTo = "/refiner?tab=files&status=processing";
      card.actionLabel = "View live work";
    } else {
      card.actionTo = "/refiner";
      card.actionLabel = "Open Refiner";
    }
    card.facts = [
      `Current queue: ${formatCount(args.operational.queued_job_count)} queued, ${formatCount(args.operational.active_job_count)} active`,
      `Current failures: ${formatCount(args.operational.failed_job_count)} jobs · ${formatCount(args.operational.quarantined_file_count)} quarantined files`,
    ];
  }
  return card;
}

function buildPrunerCard(args: {
  enabledServers: number;
  totalServers: number;
  previewRuns: number;
  applyRuns: number;
  itemsRemoved: number;
  itemsSkipped: number;
  failedApplies: number;
  operational?: OperationalModule;
}): ModuleCardData {
  const attention = args.enabledServers === 0 || args.failedApplies > 0;
  const active =
    args.previewRuns > 0 || args.applyRuns > 0 || args.itemsRemoved > 0;
  const reviewedItems = args.itemsRemoved + args.itemsSkipped;
  const removalRate =
    reviewedItems > 0 ? (args.itemsRemoved / reviewedItems) * 100.0 : 0;

  const card: ModuleCardData = {
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
      {
        label: "Cleanup runs",
        value: formatCount(args.applyRuns),
        detail: `Failed cleanups ${formatCount(args.failedApplies)}`,
      },
      {
        label: "Candidates reviewed",
        value: formatCount(reviewedItems),
        detail: `Preview runs ${formatCount(args.previewRuns)}`,
      },
      {
        label: "Removal rate",
        value: formatPercent(removalRate),
        detail: `${formatCount(args.itemsRemoved)} removed - ${formatCount(args.itemsSkipped)} skipped`,
      },
    ],
    facts: [
      `Servers enabled: ${formatCount(args.enabledServers)} of ${formatCount(args.totalServers)}`,
      `Last 30 days: ${formatCount(args.previewRuns)} previews and ${formatCount(args.applyRuns)} cleanup ${args.applyRuns === 1 ? "run" : "runs"}`,
    ],
    actionLabel: "Open Pruner",
    actionTo: "/pruner",
  };
  if (args.operational) {
    card.status = statusFromOperationalState(args.operational.state);
    card.summary = args.operational.summary;
    if (card.status === "Setup required") {
      card.actionTo = args.operational.action_path;
      card.actionLabel = "Configure Pruner";
    } else if (card.status === "Review needed") {
      card.actionTo = args.operational.action_path;
      card.actionLabel = "Review Pruner";
    } else if (card.status === "Active") {
      card.actionTo = "/pruner?tab=jobs";
      card.actionLabel = "View live work";
    } else {
      card.actionTo = "/pruner";
      card.actionLabel = "Open Pruner";
    }
    card.facts = [
      `Current queue: ${formatCount(args.operational.queued_job_count)} queued, ${formatCount(args.operational.active_job_count)} active`,
      `Current failures: ${formatCount(args.operational.failed_job_count)}`,
    ];
  }
  return card;
}

export function DashboardPage() {
  const fmt = useAppDateFormatter();
  useActivityStreamInvalidations(DASHBOARD_LIVE_INVALIDATION_KEYS);

  const dash = useDashboardStatusQuery();
  const recent = useActivityRecentQuery({ limit: 20 });
  const refinerStats = useRefinerOverviewStatsQuery();
  const refinerPaths = useRefinerPathSettingsQuery();
  const refinerJobs = useRefinerJobsInspectionQuery("recent");
  const prunerStats = usePrunerOverviewStatsQuery();
  const prunerInstances = usePrunerInstancesQuery();
  const prunerJobs = usePrunerJobsInspectionQuery(12);
  const suitePause = useSuitePauseQuery();

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
  const operationalModules = dash.data.modules ?? [];
  const operationalByModule = new Map(
    operationalModules.map((module) => [module.module, module]),
  );
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
    operational: operationalByModule.get("refiner"),
  });
  const prunerCard = buildPrunerCard({
    enabledServers:
      prunerInstances.data?.filter((row) => row.enabled).length ?? 0,
    totalServers: prunerInstances.data?.length ?? 0,
    previewRuns: prunerStats.data?.preview_runs ?? 0,
    applyRuns: prunerStats.data?.apply_runs ?? 0,
    itemsRemoved: prunerStats.data?.items_removed ?? 0,
    itemsSkipped: prunerStats.data?.items_skipped ?? 0,
    failedApplies: prunerStats.data?.failed_applies ?? 0,
    operational: operationalByModule.get("pruner"),
  });

  const refinerFileOutcomes =
    (refinerStats.data?.output_written_count ?? 0) +
    (refinerStats.data?.already_optimized_count ?? 0);
  const refinerCardForDashboard = {
    ...refinerCard,
    metrics: refinerCard.metrics.map((metric) =>
      metric.label === "Completed jobs"
        ? {
            label: "Files handled",
            value: formatCount(refinerFileOutcomes),
            detail:
              refinerFileOutcomes > 0
                ? `${formatCount(refinerStats.data?.output_written_count ?? 0)} changed - ${formatCount(refinerStats.data?.already_optimized_count ?? 0)} needed no changes`
                : "No completed file outcomes yet",
          }
        : metric,
    ),
  };

  const moduleCards = [refinerCardForDashboard, prunerCard];
  const modulesNeedingAttentionTotal = moduleCards.filter((m) =>
    moduleNeedsAttention(m.status),
  ).length;
  const activeModuleCount = moduleCards.filter(
    (m) => m.status === "Active",
  ).length;
  const workerIssues = (dash.data.system.worker_health ?? []).filter(
    (row) => row.status === "degraded",
  );
  const attentionItems: AttentionItem[] = [
    ...moduleCards
      .filter((m) => moduleNeedsAttention(m.status))
      .map((m) => ({
        key: `module-${m.key}`,
        title: m.name,
        detail: m.summary,
        actionTo: m.actionTo,
        actionLabel: m.actionLabel,
      })),
    ...workerIssues.map((row) => ({
      key: `worker-${row.module}`,
      title: `${row.module[0].toUpperCase()}${row.module.slice(1)} workers`,
      detail: row.detail,
      actionTo:
        row.module === "pruner" ? "/pruner?tab=jobs" : "/refiner?tab=jobs",
      actionLabel: "Open jobs",
    })),
  ];
  const activeItems = moduleCards
    .filter((m) => m.status === "Active")
    .map((m) => `${m.name}: ${m.summary}`);
  const overallStatus =
    !dash.data.system.healthy ||
    modulesNeedingAttentionTotal > 0 ||
    workerIssues.length > 0
      ? "Review needed"
      : activeModuleCount > 0
        ? "Active"
        : "Healthy";
  const moduleAttentionNames = moduleCards
    .filter((m) => moduleNeedsAttention(m.status))
    .map((m) => m.name);
  const workerIssueNames = workerIssues.map(
    (row) => `${row.module[0].toUpperCase()}${row.module.slice(1)} workers`,
  );
  const overallStatusDetail =
    operationalModules.length > 0
      ? moduleAttentionNames.length > 0 && workerIssueNames.length > 0
        ? `Needs attention: ${moduleAttentionNames.join(", ")}. Worker issues: ${workerIssueNames.join(", ")}.`
        : moduleAttentionNames.length > 0
          ? `Needs attention: ${moduleAttentionNames.join(", ")}.`
          : workerIssueNames.length > 0
            ? `Worker issues: ${workerIssueNames.join(", ")}.`
            : activeItems.length > 0
              ? `Active: ${moduleCards
                  .filter((m) => m.status === "Active")
                  .map((m) => m.name)
                  .join(", ")}.`
              : "No module or worker issues detected."
      : moduleAttentionNames.length > 0 && workerIssueNames.length > 0
        ? `Needs setup: ${moduleAttentionNames.join(", ")}. Worker issues: ${workerIssueNames.join(", ")}.`
        : moduleAttentionNames.length > 0
          ? `Needs setup: ${moduleAttentionNames.join(", ")}.`
          : workerIssueNames.length > 0
            ? `Worker issues: ${workerIssueNames.join(", ")}.`
            : activeItems.length > 0
              ? `Active: ${moduleCards
                  .filter((m) => m.status === "Active")
                  .map((m) => m.name)
                  .join(", ")}.`
              : "No module or worker issues detected.";

  const refinerDashboardJobs: DashboardJobRow[] = (
    refinerJobs.data?.jobs ?? []
  ).filter((job) => isDashboardVisibleRefinerJob(job.job_kind));
  const globalJobs: GlobalJobRow[] = [
    ...(refinerDashboardJobs.slice(0, 4).map((job) => ({
      key: `refiner-${job.id}`,
      module: "Refiner",
      status: jobStatusLabel(job.status),
      title: refinerJobTitle(job.job_kind),
      detail:
        job.operator_message?.trim() ||
        readableLegacyJobMessage(
          "Refiner",
          refinerJobTitle(job.job_kind),
          job.status,
          job.last_error,
        ),
      nextAction:
        job.next_action?.trim() ||
        "Open Refiner Jobs for the explanation and the next action.",
      technicalDetail: job.technical_detail ?? undefined,
      actionTo: "/refiner?tab=jobs",
      actionLabel: "Open Refiner jobs",
      updatedAt: job.updated_at,
    })) ?? []),
    ...(prunerJobs.data?.jobs.slice(0, 4).map((job) => ({
      key: `pruner-${job.id}`,
      module: "Pruner",
      status: jobStatusLabel(job.status),
      title: prunerJobTitle(job.job_kind),
      detail:
        job.operator_message?.trim() ||
        readableLegacyJobMessage(
          "Pruner",
          prunerJobTitle(job.job_kind),
          job.status,
          job.last_error,
        ),
      nextAction:
        job.next_action?.trim() ||
        "Open Pruner Jobs for the explanation and the next action.",
      technicalDetail: job.technical_detail ?? undefined,
      actionTo: "/pruner?tab=jobs",
      actionLabel: "Open Pruner jobs",
      updatedAt: job.updated_at,
    })) ?? []),
  ]
    .sort((a, b) => b.updatedAt.localeCompare(a.updatedAt))
    .slice(0, 10);
  const liveProgressItems = recentItems
    .filter(
      (item) =>
        item.event_type === REFINER_FILE_PROCESSING_PROGRESS_EVENT &&
        Boolean(item.detail),
    )
    .slice(0, 4);
  const activeGlobalJobs = globalJobs
    .filter((job) => job.status === "Running" || job.status === "Queued")
    .slice(0, 4);
  const recentSignals = recentItems
    .filter(
      (item) => item.event_type !== REFINER_FILE_PROCESSING_PROGRESS_EVENT,
    )
    .slice(0, 5);
  const activeJobCount = operationalModules.reduce(
    (total, module) => total + module.active_job_count,
    0,
  );
  const queuedJobCount = operationalModules.reduce(
    (total, module) => total + module.queued_job_count,
    0,
  );
  const processingPaused = suitePause.data?.paused === true;
  const queuedMetricLabel = processingPaused
    ? "Jobs held by pause"
    : "Background jobs queued";
  const queuedMetricDetail =
    queuedJobCount === 0
      ? "No background work is waiting"
      : processingPaused
        ? "Includes maintenance and media work; Resume releases them"
        : "Includes maintenance and media work";
  const liveNow = activeJobCount > 0 || liveProgressItems.length > 0;
  const eventsLast24h = dash.data.activity_summary.events_last_24h ?? 0;

  return (
    <div className="mm-page" data-testid="dashboard-page">
      <header className="mm-page__intro mm-dashboard-heading">
        <div>
          <p className="mm-page__eyebrow">Operations</p>
          <h1 className="mm-page__title">Dashboard</h1>
          <p className="mm-page__lead">
            Watch files move through MediaMop now. Activity keeps the durable
            history after the work is finished.
          </p>
        </div>
        <div
          className={`mm-dashboard-live-chip ${liveNow ? "mm-dashboard-live-chip--active" : ""}`}
          role="status"
          aria-live="polite"
        >
          <span className="mm-dashboard-live-chip__pulse" aria-hidden="true" />
          <span>
            <strong>{liveNow ? "Processing live" : "Live connection"}</strong>
            <small>Updates automatically</small>
          </span>
        </div>
      </header>

      {dash.data.incident_count > 0 ? (
        <section
          className="mm-dashboard-incident"
          data-testid="dashboard-incident-banner"
          role="status"
        >
          <div className="min-w-0">
            <p className="mm-dashboard-incident__eyebrow">Operator attention</p>
            <p className="mm-dashboard-incident__message">
              {formatCount(dash.data.incident_count)} issue
              {dash.data.incident_count === 1 ? " needs" : "s need"} action.
              Open the linked module to see the exact reason and next step.
            </p>
            <p className="mm-dashboard-incident__hint">
              Once finished jobs have been reviewed, clear this history from
              Settings → General.
            </p>
          </div>
          <div className="flex shrink-0 flex-wrap justify-end gap-2">
            <Link
              to={attentionItems[0]?.actionTo ?? "/activity"}
              className={mmActionButtonClass({ variant: "secondary" })}
            >
              {attentionItems[0]?.actionLabel ?? "Open review"}
            </Link>
            <Link
              to="/settings?tab=general#history-reset"
              className={mmActionButtonClass({ variant: "tertiary" })}
              title="Clear completed and failed job history after reviewing it"
            >
              Clear finished history
            </Link>
          </div>
        </section>
      ) : null}

      <section
        className="mm-dashboard-status-strip"
        data-testid="dashboard-status-strip"
      >
        <MetricCard
          label="Processing now"
          value={formatCount(activeJobCount)}
          detail={liveNow ? "Work is moving" : "Waiting for eligible files"}
        />
        <MetricCard
          label={queuedMetricLabel}
          value={formatCount(queuedJobCount)}
          detail={queuedMetricDetail}
        />
        <MetricCard
          label="Activity · 24h"
          value={formatCount(eventsLast24h)}
          detail="Live operational events"
        />
        <MetricCard
          label="System state"
          value={overallStatus}
          detail={overallStatusDetail}
        />
      </section>

      <section className="mm-dashboard-live-grid">
        <article
          className={`mm-dashboard-live-stage ${liveNow ? "mm-dashboard-live-stage--active" : ""}`}
          data-testid="dashboard-active-work"
          aria-live="polite"
        >
          <div className="mm-dashboard-panel-heading">
            <div>
              <p className="mm-dashboard-panel-heading__eyebrow">
                Live operations
              </p>
              <h2>{liveNow ? "Work in motion" : "Ready for the next file"}</h2>
              <p>
                {liveNow
                  ? `${formatCount(activeJobCount)} active and ${formatCount(queuedJobCount)} waiting across MediaMop.`
                  : processingPaused && queuedJobCount > 0
                    ? `${formatCount(queuedJobCount)} background job${queuedJobCount === 1 ? " is" : "s are"} safely held by the pause. This can include cleanup and other maintenance, not just media files.`
                    : "The workers are connected and will appear here as soon as processing starts."}
              </p>
            </div>
            <Link to="/refiner?tab=files&status=processing">
              Open workbench
            </Link>
          </div>

          <div className="mm-dashboard-live-stage__body">
            {liveProgressItems.length > 0 ? (
              liveProgressItems.map((item) => (
                <div key={item.id} className="mm-dashboard-progress-card">
                  <RefinerFileProcessingProgressDetail
                    detail={item.detail ?? ""}
                  />
                </div>
              ))
            ) : activeGlobalJobs.length > 0 ? (
              activeGlobalJobs.map((job) => (
                <div key={job.key} className="mm-dashboard-generic-job">
                  <span
                    className="mm-dashboard-generic-job__pulse"
                    aria-hidden="true"
                  />
                  <div>
                    <p>{job.detail}</p>
                    <small>{job.nextAction}</small>
                  </div>
                </div>
              ))
            ) : (
              <div className="mm-dashboard-idle-state">
                <span
                  className="mm-dashboard-idle-state__radar"
                  aria-hidden="true"
                />
                <div>
                  <strong>No active media work</strong>
                  <p>
                    New Refiner and Pruner work will surface here automatically.
                  </p>
                </div>
              </div>
            )}
          </div>

          <div className="mm-dashboard-flow" aria-label="Current work flow">
            <div className={activeJobCount > 0 ? "is-active" : ""}>
              <span>Processing</span>
              <strong>{formatCount(activeJobCount)}</strong>
            </div>
            <i aria-hidden="true" />
            <div className={queuedJobCount > 0 ? "is-active" : ""}>
              <span>{processingPaused ? "Held by pause" : "Queued jobs"}</span>
              <strong>{formatCount(queuedJobCount)}</strong>
            </div>
            <i aria-hidden="true" />
            <div>
              <span>Updates today</span>
              <strong>{formatCount(eventsLast24h)}</strong>
            </div>
          </div>
        </article>

        <article
          className="mm-dashboard-action-queue"
          data-testid="dashboard-needs-attention"
        >
          <div className="mm-dashboard-panel-heading">
            <div>
              <p className="mm-dashboard-panel-heading__eyebrow">
                Action queue
              </p>
              <h2>
                {attentionItems.length > 0
                  ? "Your next decisions"
                  : "All clear"}
              </h2>
              <p>
                {attentionItems.length > 0
                  ? "Only items that need a person appear here."
                  : "MediaMop does not need anything from you right now."}
              </p>
            </div>
            <span className="mm-dashboard-action-count">
              {formatCount(attentionItems.length)}
            </span>
          </div>
          <div className="mm-dashboard-action-queue__body">
            {attentionItems.length > 0 ? (
              attentionItems.map((item) => (
                <Link
                  key={item.key}
                  to={item.actionTo}
                  className="mm-dashboard-action-item"
                >
                  <span>
                    <strong>{item.title}</strong>
                    <small>{item.detail}</small>
                  </span>
                  <b>{item.actionLabel} →</b>
                </Link>
              ))
            ) : (
              <div className="mm-dashboard-all-clear">
                <span aria-hidden="true">✓</span>
                <p>Nothing needs review or configuration.</p>
              </div>
            )}
          </div>
        </article>
      </section>

      <section
        // Two modules, so two columns. This was three when Subber was one of them (#331)
        // and was left behind when it went, so Refiner and Pruner sat in two thirds of the
        // row with an empty column beside them. Two also lines the cards up with the
        // Needs attention / Recent activity pair below, which is already xl:grid-cols-2.
        className="mt-5 grid gap-4 xl:grid-cols-2"
        data-testid="dashboard-module-cards"
      >
        {moduleCards.map((card) => (
          <ModuleCard key={card.key} card={card} />
        ))}
      </section>

      <section className="mm-dashboard-signal-stream">
        <div className="mm-dashboard-panel-heading">
          <div>
            <p className="mm-dashboard-panel-heading__eyebrow">
              Recent activity
            </p>
            <h2>What just changed</h2>
            <p>
              A concise live pulse. Use Activity for the searchable audit trail.
            </p>
          </div>
          <Link to="/activity">Open activity history</Link>
        </div>
        {recentSignals.length > 0 ? (
          <ol>
            {recentSignals.map((item) => (
              <LiveSignal key={item.id} item={item} fmt={fmt} />
            ))}
          </ol>
        ) : (
          <p className="mm-dashboard-signal-stream__empty">
            The next completed action or system event will appear here.
          </p>
        )}
      </section>

      <section
        className="mm-card mm-dash-card mt-6"
        data-testid="dashboard-global-jobs"
      >
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2 className="mm-card__title">Background work</h2>
            <p className="mt-1 text-sm text-[var(--mm-text2)]">
              The latest queued and completed work across Refiner and Pruner.
              Anything requiring you includes a plain-language next step.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Link
              to="/refiner?tab=jobs"
              className={mmActionButtonClass({ variant: "tertiary" })}
            >
              Refiner jobs
            </Link>
            <Link
              to="/pruner?tab=jobs"
              className={mmActionButtonClass({ variant: "tertiary" })}
            >
              Pruner jobs
            </Link>
          </div>
        </div>
        <div className="mm-card__body space-y-3">
          {globalJobs.length === 0 ? (
            <p className="text-sm text-[var(--mm-text2)]">
              No recent jobs are recorded.
            </p>
          ) : (
            globalJobs.map((job) => (
              <article
                key={job.key}
                className="rounded-lg border border-[var(--mm-border)] bg-black/10 p-3"
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="space-y-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--mm-gold)]">
                        {job.module}
                      </span>
                      <span className="rounded-full border border-[var(--mm-border)] bg-[var(--mm-card-bg)] px-2 py-0.5 text-xs text-[var(--mm-text2)]">
                        {job.status}
                      </span>
                    </div>
                    <h3 className="text-sm font-semibold text-[var(--mm-text1)]">
                      {job.title}
                    </h3>
                    <p className="break-words text-sm text-[var(--mm-text2)] [overflow-wrap:anywhere]">
                      {job.detail}
                    </p>
                    <p className="mt-2 text-xs text-[var(--mm-text3)]">
                      <span className="font-semibold text-[var(--mm-text2)]">
                        Next step:
                      </span>{" "}
                      {job.nextAction}
                    </p>
                    {job.technicalDetail ? (
                      <details className="mt-2 text-xs text-[var(--mm-text3)]">
                        <summary className="cursor-pointer select-none">
                          Technical detail
                        </summary>
                        <pre className="mt-2 max-h-32 overflow-auto whitespace-pre-wrap break-words rounded border border-[var(--mm-border)] bg-black/10 p-2 [overflow-wrap:anywhere]">
                          {job.technicalDetail}
                        </pre>
                      </details>
                    ) : null}
                    <Link
                      to={job.actionTo}
                      className="mt-2 inline-flex text-xs font-semibold text-[var(--mm-accent-bright)] underline underline-offset-2"
                    >
                      {job.actionLabel}
                    </Link>
                  </div>
                  <time className="text-sm text-[var(--mm-text3)]">
                    {fmt(job.updatedAt)}
                  </time>
                </div>
              </article>
            ))
          )}
        </div>
      </section>
    </div>
  );
}
