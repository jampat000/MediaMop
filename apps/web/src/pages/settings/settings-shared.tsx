import type { ReactNode } from "react";
import type { SuiteLogEntry } from "../../lib/suite/types";

export type LogLevelFilter = "" | "INFO" | "WARNING" | "ERROR";

export const SUITE_SETTINGS_DASH_CARD_CLASS =
  "mm-card mm-dash-card flex min-h-0 min-w-0 flex-col gap-5";
export const SUITE_SETTINGS_PREMIUM_PANEL_CLASS =
  "flex min-h-0 min-w-0 flex-col gap-4 rounded-xl border border-[var(--mm-border)] bg-[var(--mm-card-bg)]/80 p-4 shadow-[var(--mm-shadow-card-inner)]";
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

/** Log severity as a colour on the level word. The quiet body has no tinted cards,
 *  so the level itself is what carries the warning. */
export function logLevelToneClass(level: string): string {
  switch (level.toUpperCase()) {
    case "ERROR":
    case "CRITICAL":
      return "mm-status-text--failed";
    case "WARNING":
      return "mm-status-text--warning";
    default:
      return "";
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
    <details className="mt-2">
      <summary className="mm-quiet-link cursor-pointer list-none">
        Technical details →
      </summary>
      <div className="mt-2 space-y-1.5 text-sm text-[var(--mm-text2)]">
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
          // A traceback keeps its edge: the boundary says where the pasted text ends.
          // It is a code block, not a card.
          <pre className="overflow-auto rounded-md border border-[var(--mm-border)] p-3 text-xs leading-5 whitespace-pre-wrap text-[var(--mm-text2)]">
            {entry.traceback}
          </pre>
        ) : null}
      </div>
    </details>
  );
}

/** Rule 3: a heading, its links, a hairline, then the content. Mirrors the shape the
 *  Processing Overview reference uses (docs/design/content-language.md). */
export function SettingsQuietSection({
  headingId,
  heading,
  aside,
  children,
  id,
  "data-testid": dataTestId,
}: {
  headingId: string;
  heading: string;
  aside?: ReactNode;
  children: ReactNode;
  id?: string;
  "data-testid"?: string;
}) {
  return (
    <section
      className="mm-quiet-section"
      aria-labelledby={headingId}
      id={id}
      data-testid={dataTestId}
    >
      <div className="mm-quiet-section__head">
        <h3 id={headingId} className="mm-quiet-section__title">
          {heading}
        </h3>
        {aside ? <div className="mm-quiet-section__aside">{aside}</div> : null}
      </div>
      <div className="mm-quiet-section__body">{children}</div>
    </section>
  );
}

export type SettingsFact = {
  label: string;
  value: string;
  detail?: string;
  /** An existing mm-status-text--* class when the value itself is good or bad news. */
  toneClass?: string;
};

/**
 * Coequal facts, as a borderless label/value row rather than a grid of identical
 * boxes. These are categorical answers to different questions — a policy, a version,
 * a count — so none of them is a hero, and rule 2 does not apply. Below 760px the
 * quiet table stacks each column into its own labelled line by itself.
 */
export function SettingsFactTable({
  facts,
  caption,
  "data-testid": dataTestId,
}: {
  facts: readonly SettingsFact[];
  caption: string;
  "data-testid"?: string;
}) {
  return (
    <div className="mm-quiet-table-wrap">
      <table className="mm-quiet-table" data-testid={dataTestId}>
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr>
            {facts.map((fact) => (
              <th scope="col" key={fact.label}>
                {fact.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          <tr>
            {facts.map((fact) => (
              <td key={fact.label} data-label={fact.label}>
                <span>
                  <span
                    className={`mm-quiet-table__strong${fact.toneClass ? ` ${fact.toneClass}` : ""}`}
                  >
                    {fact.value}
                  </span>
                  {fact.detail ? (
                    <span className="mm-quiet-table__sub">{fact.detail}</span>
                  ) : null}
                </span>
              </td>
            ))}
          </tr>
        </tbody>
      </table>
    </div>
  );
}
