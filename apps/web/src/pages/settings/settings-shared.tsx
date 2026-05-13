import type {
  SuiteLogEntry,
} from "../../lib/suite/types";

export type LogLevelFilter = "" | "INFO" | "WARNING" | "ERROR";

export const SUITE_SETTINGS_DASH_CARD_CLASS =
  "mm-card mm-dash-card flex min-h-0 min-w-0 flex-col gap-5";
export const SUITE_SETTINGS_PREMIUM_PANEL_CLASS =
  "flex min-h-0 min-w-0 flex-col gap-4 rounded-xl border border-[var(--mm-border)] bg-[var(--mm-card-bg)]/80 p-4 shadow-[var(--mm-shadow-card-inner)]";
export const SUITE_SETTINGS_PREMIUM_TILE_CLASS =
  "rounded-xl border border-[var(--mm-border)] bg-[var(--mm-card-bg)]/80 px-4 py-3 shadow-[var(--mm-shadow-card-inner)]";
export const CONFIGURATION_BACKUP_INTERVAL_HOURS = [
  6, 12, 24, 48, 72, 168,
] as const;
export const SUITE_PASSWORD_FIELD_CLASS =
  "mm-input w-full min-w-0 flex-1 text-sm tracking-normal text-[var(--mm-text)]";

export function formatChangePasswordMutationError(err: unknown): string {
  if (err instanceof Error) {
    return err.message;
  }
  if (typeof err === "string") {
    return err;
  }
  return "Could not change password.";
}

export function formatBackupBytes(n: number): string {
  if (n < 1024) {
    return `${n} B`;
  }
  if (n < 1024 * 1024) {
    return `${(n / 1024).toFixed(1)} KB`;
  }
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

export function formatSessionTimeout(minutes: number): string {
  if (minutes % 1440 === 0) {
    const days = minutes / 1440;
    return `${days} day${days === 1 ? "" : "s"}`;
  }
  if (minutes % 60 === 0) {
    const hours = minutes / 60;
    return `${hours} hour${hours === 1 ? "" : "s"}`;
  }
  return `${minutes} minute${minutes === 1 ? "" : "s"}`;
}

export function formatRuntimeUptime(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds <= 0) return "Just started";
  const totalSeconds = Math.max(0, Math.floor(seconds));
  const days = Math.floor(totalSeconds / 86400);
  const hours = Math.floor((totalSeconds % 86400) / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  if (days > 0) return `${days}d ${hours}h`;
  if (hours > 0) return `${hours}h ${minutes}m`;
  return `${minutes}m`;
}

export function formatAverageMs(value: number): string {
  if (!Number.isFinite(value) || value <= 0) return "0 ms";
  return `${value >= 100 ? value.toFixed(0) : value.toFixed(1)} ms`;
}

export function requestIssueSummary(
  statusCounts: Record<string, number> | undefined,
): { value: string; detail: string } {
  const counts = statusCounts ?? {};
  const success = counts["2xx"] ?? 0;
  const redirects = counts["3xx"] ?? 0;
  const rejectedOrMissing = counts["4xx"] ?? 0;
  const serverFailures = counts["5xx"] ?? 0;
  const detail = `Successful ${success} - Redirected ${redirects} - Rejected or not found ${rejectedOrMissing} - Server failures ${serverFailures}`;
  if (serverFailures > 0) {
    return {
      value: `${serverFailures} server ${serverFailures === 1 ? "failure" : "failures"}`,
      detail,
    };
  }
  if (rejectedOrMissing > 0) {
    return {
      value: `${rejectedOrMissing} request ${rejectedOrMissing === 1 ? "issue" : "issues"}`,
      detail,
    };
  }
  return { value: "No request issues", detail };
}

export function logCardTone(level: string): string {
  switch (level.toUpperCase()) {
    case "ERROR":
    case "CRITICAL":
      return "border-red-500/35 bg-red-950/20";
    case "WARNING":
      return "border-amber-400/35 bg-amber-950/20";
    default:
      return "border-[var(--mm-border)] bg-[var(--mm-card-bg)]/50";
  }
}

export function logLevelBadgeTone(level: string): string {
  switch (level.toUpperCase()) {
    case "ERROR":
    case "CRITICAL":
      return "border-red-500/40 bg-red-500/10 text-red-100";
    case "WARNING":
      return "border-amber-400/40 bg-amber-400/10 text-amber-100";
    default:
      return "border-[var(--mm-border)] bg-black/10 text-[var(--mm-text2)]";
  }
}

export function renderLogTechnicalDetails(entry: SuiteLogEntry) {
  if (
    !entry.traceback &&
    !entry.source &&
    !entry.logger &&
    !entry.correlation_id &&
    !entry.job_id
  ) {
    return null;
  }
  return (
    <details className="rounded-md border border-[var(--mm-border)] bg-black/10 px-3 py-2">
      <summary className="cursor-pointer text-sm font-medium text-[var(--mm-text2)]">
        Technical details
      </summary>
      <div className="mt-3 space-y-2 text-sm text-[var(--mm-text2)]">
        {entry.source ? (
          <p>
            <span className="font-medium text-[var(--mm-text1)]">Source:</span>{" "}
            {entry.source}
          </p>
        ) : null}
        {entry.logger ? (
          <p>
            <span className="font-medium text-[var(--mm-text1)]">Logger:</span>{" "}
            {entry.logger}
          </p>
        ) : null}
        {entry.correlation_id ? (
          <p>
            <span className="font-medium text-[var(--mm-text1)]">
              Request ID:
            </span>{" "}
            {entry.correlation_id}
          </p>
        ) : null}
        {entry.job_id ? (
          <p>
            <span className="font-medium text-[var(--mm-text1)]">Job ID:</span>{" "}
            {entry.job_id}
          </p>
        ) : null}
        {entry.traceback ? (
          <pre className="overflow-auto rounded-md border border-[var(--mm-border)] bg-black/20 p-3 text-xs leading-5 text-[var(--mm-text2)] whitespace-pre-wrap">
            {entry.traceback}
          </pre>
        ) : null}
      </div>
    </details>
  );
}

export function SettingsSummaryCard({
  label,
  value,
  detail,
}: {
  label: string;
  value: string;
  detail?: string;
}) {
  return (
    <section className="rounded-lg border border-[var(--mm-border)] bg-[var(--mm-card-bg)] px-4 py-3">
      <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--mm-text3)]">
        {label}
      </p>
      <p className="mt-1 text-lg font-semibold text-[var(--mm-text1)]">
        {value}
      </p>
      {detail ? (
        <p className="mt-1 text-sm text-[var(--mm-text2)]">{detail}</p>
      ) : null}
    </section>
  );
}
