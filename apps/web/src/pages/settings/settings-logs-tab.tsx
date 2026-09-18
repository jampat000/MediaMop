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
  logLevelToneClass,
  renderLogTechnicalDetails,
  requestIssueSummary,
  SettingsFactTable,
  SettingsQuietSection,
  type LogLevelFilter,
  type SettingsFact,
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

  // Five coequal counters, not one magnitude that carries the tab: on a healthy
  // install the number worth reading is the one that is usually zero, so none of
  // these earns a hero tile. See docs/design/content-language.md, rule 2.
  const logCounts: SettingsFact[] = [
    {
      label: "Showing now",
      value: `${logsQ.data?.items.length ?? 0} events`,
    },
    {
      label: "Matching events",
      value: `${logsQ.data?.total ?? 0} events`,
    },
    {
      label: "Errors",
      value: String(logsQ.data?.counts.error ?? 0),
      toneClass:
        (logsQ.data?.counts.error ?? 0) > 0 ? "mm-status-text--failed" : "",
    },
    {
      label: "Warnings",
      value: String(logsQ.data?.counts.warning ?? 0),
      toneClass:
        (logsQ.data?.counts.warning ?? 0) > 0 ? "mm-status-text--warning" : "",
    },
    {
      label: "Information",
      value: String(logsQ.data?.counts.information ?? 0),
    },
  ];

  const diagnosticFacts: SettingsFact[] = [
    {
      label: "Running for",
      value: runtimeMetrics
        ? formatRuntimeUptime(runtimeMetrics.uptime_seconds)
        : "Loading...",
    },
    {
      label: "Requests handled",
      value: runtimeMetrics
        ? String(runtimeMetrics.total_requests)
        : "Loading...",
    },
    {
      label: "Average response",
      value: runtimeMetrics
        ? formatAverageMs(runtimeMetrics.average_response_ms)
        : "Loading...",
    },
    {
      label: "Logged failures",
      value: runtimeMetrics
        ? String(runtimeMetrics.error_log_count)
        : "Loading...",
    },
    {
      label: "Request issues",
      value: runtimeMetrics ? runtimeRequestIssues.value : "Loading...",
    },
  ];

  return (
    <div data-testid="suite-settings-logs" className="mm-quiet-stack w-full">
      <div className={mmModuleTabBlurbBandClass}>
        <p className={mmModuleTabBlurbTextClass}>
          System event logs from the Weir runtime. Use filters to narrow down
          warnings, failures, and tracebacks. Advanced server diagnostics are
          available here when troubleshooting.
        </p>
      </div>

      <SettingsFactTable
        caption="Log summary"
        facts={logCounts}
        data-testid="suite-settings-log-summary"
      />

      <section className="mm-quiet-section">
        <details className="group">
          <summary className="mm-quiet-section__head cursor-pointer list-none [&::-webkit-details-marker]:hidden">
            <span
              id="suite-settings-diagnostics-heading"
              className="mm-quiet-section__title"
            >
              Server diagnostics
            </span>
            <span className="mm-quiet-section__aside">
              <span className="mm-quiet-link group-open:hidden">Show →</span>
              <span className="mm-quiet-link hidden group-open:inline">
                Hide →
              </span>
            </span>
          </summary>
          <div className="mm-quiet-section__body">
            <p className="mm-quiet-note">
              Advanced counters for troubleshooting. Request issues usually mean
              a browser or API request was rejected or asked for something that
              was not found; they are not the same as application failures.
            </p>
            {metricsQ.isError ? (
              <p
                className="mt-4 text-sm text-[var(--mm-status-failed-text)]"
                role="alert"
              >
                {metricsQ.error instanceof Error
                  ? metricsQ.error.message
                  : "Could not load server diagnostics."}
              </p>
            ) : (
              <div className="mt-4">
                <SettingsFactTable
                  caption="Server runtime counters"
                  facts={diagnosticFacts}
                />
              </div>
            )}
            {runtimeMetrics ? (
              <p className="mt-3 text-xs text-[var(--mm-text3)]">
                {runtimeRequestIssues.detail}
              </p>
            ) : null}
          </div>
        </details>
      </section>

      <SettingsQuietSection
        headingId="suite-settings-logs-filters-heading"
        heading="Search logs"
        aside={
          <>
            <button
              type="button"
              className="mm-quiet-link"
              disabled={logsQ.isFetching}
              onClick={() => void logsQ.refetch()}
            >
              {logsQ.isFetching ? "Refreshing…" : "Refresh →"}
            </button>
            <button
              type="button"
              className="mm-quiet-link"
              disabled={!logSearch.trim() && !logLevel && !tracebacksOnly}
              onClick={() => {
                setLogSearch("");
                setLogLevel("");
                setTracebacksOnly(false);
              }}
            >
              Clear filters →
            </button>
          </>
        }
      >
        <p className="mm-quiet-note">
          Search message text, component names, tracebacks, request IDs, and job
          IDs. This view refreshes while it is open.
        </p>

        <div className="mt-4 grid gap-3 lg:grid-cols-[minmax(0,2fr)_220px_auto]">
          <label className="flex flex-col gap-1 text-xs font-semibold tracking-wide text-[var(--mm-text3)] uppercase">
            Search
            <input
              type="text"
              className={mmEditableTextFieldClass}
              placeholder="Search message, detail, traceback, logger, or source"
              value={logSearch}
              onChange={(e) => setLogSearch(e.target.value)}
            />
          </label>
          <label className="flex flex-col gap-1 text-xs font-semibold tracking-wide text-[var(--mm-text3)] uppercase">
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
          <div className="flex flex-col gap-1 text-xs font-semibold tracking-wide text-[var(--mm-text3)] uppercase">
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
        </div>

        {logSearch.trim() || logLevel || tracebacksOnly ? (
          <div className="mt-3 flex flex-wrap gap-2">
            {logSearch.trim() ? (
              <span className="mm-quiet-badge">Search: {logSearch.trim()}</span>
            ) : null}
            {logLevel ? (
              <span className="mm-quiet-badge">
                Level: {logLevel === "INFO" ? "Information" : logLevel}
              </span>
            ) : null}
            {tracebacksOnly ? (
              <span className="mm-quiet-badge">Tracebacks only</span>
            ) : null}
          </div>
        ) : null}
      </SettingsQuietSection>

      <SettingsQuietSection
        headingId="suite-settings-logs-list-heading"
        heading="System events"
      >
        <p className="mm-quiet-note">
          Recent runtime events, warnings, and failures captured by Weir.
        </p>

        {logsQ.isPending ? (
          <p className="mm-quiet-note mt-4">Loading logs...</p>
        ) : logsQ.isError ? (
          <p
            className="mt-4 text-sm text-[var(--mm-status-failed-text)]"
            role="alert"
          >
            {logsQ.error instanceof Error
              ? logsQ.error.message
              : "Could not load logs."}
          </p>
        ) : (logsQ.data?.items.length ?? 0) === 0 ? (
          <p className="mm-quiet-note mt-4">
            No system events matched the current filters.
          </p>
        ) : (
          <div className="mm-quiet-table-wrap mt-4">
            <table className="mm-quiet-table">
              <thead>
                <tr>
                  <th scope="col">Event</th>
                  <th scope="col">Level</th>
                  <th scope="col">When</th>
                </tr>
              </thead>
              <tbody>
                {logsQ.data?.items.map((entry) => {
                  const technicalDetails = renderLogTechnicalDetails(entry);
                  return (
                    <tr
                      key={`${entry.timestamp}-${entry.level}-${entry.message}`}
                    >
                      <th scope="row" className="mm-quiet-table__name">
                        <span>{entry.message}</span>
                        <span className="mm-quiet-badge">
                          {entry.component}
                        </span>
                        {entry.detail ? (
                          <span className="mm-quiet-table__sub">
                            {entry.detail}
                          </span>
                        ) : null}
                        {technicalDetails}
                      </th>
                      <td
                        data-label="Level"
                        className={logLevelToneClass(entry.level)}
                      >
                        {entry.level === "INFO" ? "Information" : entry.level}
                      </td>
                      <td data-label="When" className="whitespace-nowrap">
                        <time dateTime={entry.timestamp}>
                          {formatDateTime(entry.timestamp)}
                        </time>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </SettingsQuietSection>
    </div>
  );
}
