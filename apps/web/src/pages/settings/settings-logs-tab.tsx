import { useState } from "react";
import {
  useSuiteLogsQuery,
  useSuiteMetricsQuery,
} from "../../lib/suite/queries";
import { mmActionButtonClass } from "../../lib/ui/mm-control-roles";
import { mmEditableTextFieldClass } from "../../lib/ui/mm-control-roles";
import {
  mmModuleTabBlurbBandClass,
  mmModuleTabBlurbTextClass,
} from "../../lib/ui/mm-module-tab-blurb";
import { useAppDateFormatter } from "../../lib/ui/mm-format-date";
import {
  formatAverageMs,
  formatRuntimeUptime,
  logCardTone,
  logLevelBadgeTone,
  renderLogTechnicalDetails,
  requestIssueSummary,
  SettingsSummaryCard,
  type LogLevelFilter,
} from "./settings-shared";

export function SettingsLogsTab() {
  const formatDateTime = useAppDateFormatter();
  const [logSearch, setLogSearch] = useState("");
  const [logLevel, setLogLevel] = useState<LogLevelFilter>("");
  const [tracebacksOnly, setTracebacksOnly] = useState(false);

  const logsQ = useSuiteLogsQuery({
    level: logLevel || undefined,
    search: logSearch.trim() || undefined,
    has_exception: tracebacksOnly ? true : undefined,
    limit: 100,
  });
  const metricsQ = useSuiteMetricsQuery();

  const runtimeMetrics = metricsQ.data;
  const runtimeRequestIssues = requestIssueSummary(
    runtimeMetrics?.status_counts,
  );

  return (
    <div data-testid="suite-settings-logs" className="mm-bubble-stack w-full">
      <div className={mmModuleTabBlurbBandClass}>
        <p className={mmModuleTabBlurbTextClass}>
          System event logs from the MediaMop runtime. Use filters to narrow
          down warnings, failures, and tracebacks. Advanced server diagnostics
          are available here when troubleshooting.
        </p>
      </div>

      <section
        className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5"
        aria-label="Log summary"
      >
        <SettingsSummaryCard
          label="Showing now"
          value={`${logsQ.data?.items.length ?? 0} events`}
        />
        <SettingsSummaryCard
          label="Matching events"
          value={`${logsQ.data?.total ?? 0} events`}
        />
        <SettingsSummaryCard
          label="Errors"
          value={String(logsQ.data?.counts.error ?? 0)}
        />
        <SettingsSummaryCard
          label="Warnings"
          value={String(logsQ.data?.counts.warning ?? 0)}
        />
        <SettingsSummaryCard
          label="Information"
          value={String(logsQ.data?.counts.information ?? 0)}
        />
      </section>

      <section
        className="mm-card mm-dash-card w-full"
        aria-labelledby="suite-settings-diagnostics-heading"
      >
        <details>
          <summary
            id="suite-settings-diagnostics-heading"
            className="cursor-pointer text-base font-semibold text-[var(--mm-text1)]"
          >
            Server diagnostics
          </summary>
          <p className="mt-2 text-sm text-[var(--mm-text2)]">
            Advanced counters for troubleshooting. Request issues usually mean a
            browser or API request was rejected or asked for something that was
            not found; they are not the same as application failures.
          </p>
          {metricsQ.isError ? (
            <p
              className="mt-4 rounded-md border border-red-500/40 bg-red-950/25 px-3 py-2 text-sm text-red-200"
              role="alert"
            >
              {metricsQ.error instanceof Error
                ? metricsQ.error.message
                : "Could not load server diagnostics."}
            </p>
          ) : (
            <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-5">
              <SettingsSummaryCard
                label="Running for"
                value={
                  runtimeMetrics
                    ? formatRuntimeUptime(runtimeMetrics.uptime_seconds)
                    : "Loading..."
                }
              />
              <SettingsSummaryCard
                label="Requests handled"
                value={
                  runtimeMetrics
                    ? String(runtimeMetrics.total_requests)
                    : "Loading..."
                }
              />
              <SettingsSummaryCard
                label="Average response"
                value={
                  runtimeMetrics
                    ? formatAverageMs(runtimeMetrics.average_response_ms)
                    : "Loading..."
                }
              />
              <SettingsSummaryCard
                label="Logged failures"
                value={
                  runtimeMetrics
                    ? String(runtimeMetrics.error_log_count)
                    : "Loading..."
                }
              />
              <SettingsSummaryCard
                label="Request issues"
                value={
                  runtimeMetrics ? runtimeRequestIssues.value : "Loading..."
                }
              />
            </div>
          )}
          {runtimeMetrics ? (
            <p className="mt-3 text-xs text-[var(--mm-text3)]">
              {runtimeRequestIssues.detail}
            </p>
          ) : null}
        </details>
      </section>

      <section
        className="mm-card mm-dash-card w-full"
        aria-labelledby="suite-settings-logs-filters-heading"
      >
        <div className="mm-card__body space-y-4">
          <div>
            <h3
              id="suite-settings-logs-filters-heading"
              className="text-base font-semibold text-[var(--mm-text1)]"
            >
              Search logs
            </h3>
            <p className="mt-1 text-sm text-[var(--mm-text2)]">
              Search message text, component names, tracebacks, request IDs, and
              job IDs. This view refreshes while it is open.
            </p>
          </div>

          <div className="grid gap-3 lg:grid-cols-[minmax(0,2fr)_220px_auto_auto]">
            <label className="flex flex-col gap-1 text-xs font-semibold uppercase tracking-wide text-[var(--mm-text3)]">
              Search
              <input
                type="text"
                className={mmEditableTextFieldClass}
                placeholder="Search message, detail, traceback, logger, or source"
                value={logSearch}
                onChange={(e) => setLogSearch(e.target.value)}
              />
            </label>
            <label className="flex flex-col gap-1 text-xs font-semibold uppercase tracking-wide text-[var(--mm-text3)]">
              Level
              <select
                className={mmEditableTextFieldClass}
                value={logLevel}
                onChange={(e) => setLogLevel(e.target.value as LogLevelFilter)}
              >
                <option value="">All levels</option>
                <option value="INFO">Information</option>
                <option value="WARNING">Warnings</option>
                <option value="ERROR">Errors</option>
              </select>
            </label>
            <div className="flex flex-col gap-1 text-xs font-semibold uppercase tracking-wide text-[var(--mm-text3)]">
              <span>Tracebacks only</span>
              <div className="flex gap-2">
                <button
                  type="button"
                  className={mmActionButtonClass({
                    variant: tracebacksOnly ? "primary" : "tertiary",
                  })}
                  onClick={() => setTracebacksOnly(true)}
                >
                  On
                </button>
                <button
                  type="button"
                  className={mmActionButtonClass({
                    variant: !tracebacksOnly ? "primary" : "tertiary",
                  })}
                  onClick={() => setTracebacksOnly(false)}
                >
                  Off
                </button>
              </div>
            </div>
            <div className="flex flex-wrap items-end gap-2">
              <button
                type="button"
                className={mmActionButtonClass({
                  variant: "secondary",
                  disabled: logsQ.isFetching,
                })}
                disabled={logsQ.isFetching}
                onClick={() => void logsQ.refetch()}
              >
                {logsQ.isFetching ? "Refreshing..." : "Refresh"}
              </button>
              <button
                type="button"
                className={mmActionButtonClass({
                  variant: "tertiary",
                  disabled: !logSearch.trim() && !logLevel && !tracebacksOnly,
                })}
                disabled={!logSearch.trim() && !logLevel && !tracebacksOnly}
                onClick={() => {
                  setLogSearch("");
                  setLogLevel("");
                  setTracebacksOnly(false);
                }}
              >
                Clear filters
              </button>
            </div>
          </div>

          {logSearch.trim() || logLevel || tracebacksOnly ? (
            <div className="flex flex-wrap gap-2">
              {logSearch.trim() ? (
                <span className="rounded-full border border-[var(--mm-border)] bg-black/10 px-2.5 py-1 text-xs text-[var(--mm-text2)]">
                  Search: {logSearch.trim()}
                </span>
              ) : null}
              {logLevel ? (
                <span className="rounded-full border border-[var(--mm-border)] bg-black/10 px-2.5 py-1 text-xs text-[var(--mm-text2)]">
                  Level: {logLevel === "INFO" ? "Information" : logLevel}
                </span>
              ) : null}
              {tracebacksOnly ? (
                <span className="rounded-full border border-[var(--mm-border)] bg-black/10 px-2.5 py-1 text-xs text-[var(--mm-text2)]">
                  Tracebacks only
                </span>
              ) : null}
            </div>
          ) : null}
        </div>
      </section>

      <section
        className="mm-card mm-dash-card w-full"
        aria-labelledby="suite-settings-logs-list-heading"
      >
        <div className="mm-card__body space-y-4">
          <div>
            <h3
              id="suite-settings-logs-list-heading"
              className="text-base font-semibold text-[var(--mm-text1)]"
            >
              System events
            </h3>
            <p className="mt-1 text-sm text-[var(--mm-text2)]">
              Recent runtime events, warnings, and failures captured by
              MediaMop.
            </p>
          </div>

          {logsQ.isPending ? (
            <div className="rounded-lg border border-[var(--mm-border)] bg-black/10 px-4 py-4 text-sm text-[var(--mm-text3)]">
              Loading logs...
            </div>
          ) : logsQ.isError ? (
            <div
              className="rounded-lg border border-red-500/40 bg-red-950/25 px-4 py-4 text-sm text-red-200"
              role="alert"
            >
              {logsQ.error instanceof Error
                ? logsQ.error.message
                : "Could not load logs."}
            </div>
          ) : (logsQ.data?.items.length ?? 0) === 0 ? (
            <div className="rounded-lg border border-[var(--mm-border)] bg-black/10 px-4 py-4 text-sm text-[var(--mm-text2)]">
              No system events matched the current filters.
            </div>
          ) : (
            <div className="space-y-3">
              {logsQ.data?.items.map((entry) => {
                const technicalDetails = renderLogTechnicalDetails(entry);
                return (
                  <article
                    key={`${entry.timestamp}-${entry.level}-${entry.message}`}
                    className={`rounded-lg border px-4 py-4 ${logCardTone(entry.level)}`}
                  >
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div className="space-y-2">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--mm-gold)]">
                            {entry.component}
                          </span>
                          <span
                            className={`rounded-full border px-2.5 py-1 text-xs font-medium ${logLevelBadgeTone(entry.level)}`}
                          >
                            {entry.level === "INFO"
                              ? "Information"
                              : entry.level}
                          </span>
                        </div>
                        <h4 className="text-sm font-semibold text-[var(--mm-text1)]">
                          {entry.message}
                        </h4>
                        {entry.detail ? (
                          <p className="text-sm leading-6 text-[var(--mm-text2)]">
                            {entry.detail}
                          </p>
                        ) : null}
                      </div>
                      <time className="text-sm text-[var(--mm-text3)]">
                        {formatDateTime(entry.timestamp)}
                      </time>
                    </div>
                    {technicalDetails ? (
                      <div className="mt-3">{technicalDetails}</div>
                    ) : null}
                  </article>
                );
              })}
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
