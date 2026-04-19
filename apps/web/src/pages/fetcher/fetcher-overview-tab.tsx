import type { ReactNode } from "react";
import { PageLoading } from "../../components/shared/page-loading";
import { isHttpErrorFromApi, isLikelyNetworkFailure } from "../../lib/api/error-guards";
import { useFetcherArrOperatorSettingsQuery } from "../../lib/fetcher/arr-operator-settings/queries";
import type { FetcherArrOperatorSettingsOut } from "../../lib/fetcher/arr-operator-settings/types";
import {
  useFailedImportCleanupPolicyQuery,
  useFailedImportQueueAttentionSnapshotQuery,
} from "../../lib/fetcher/failed-imports/queries";
import { useFetcherOverviewStatsQuery } from "../../lib/fetcher/queries";
import type {
  FailedImportCleanupPolicyAxis,
  FetcherFailedImportCleanupPolicyOut,
  FetcherFailedImportQueueAttentionAxis,
  FetcherFailedImportQueueAttentionSnapshot,
} from "../../lib/fetcher/failed-imports/types";
import { FetcherCurrentSearchSetupSection } from "./fetcher-automation-summary";
import {
  FETCHER_CONNECTION_PANEL_RADARR,
  FETCHER_CONNECTION_PANEL_SONARR,
  FETCHER_TAB_RADARR_LABEL,
  FETCHER_TAB_SONARR_LABEL,
} from "./fetcher-display-names";
import { fetcherMenuButtonClass } from "./fetcher-menu-button";

export type FetcherOverviewOpenSection = "connections" | "failed-imports" | "sonarr" | "radarr";

function sonarrTvSearchesOn(data: FetcherArrOperatorSettingsOut): boolean {
  return data.sonarr_missing.enabled || data.sonarr_upgrade.enabled;
}

function radarrMovieSearchesOn(data: FetcherArrOperatorSettingsOut): boolean {
  return data.radarr_missing.enabled || data.radarr_upgrade.enabled;
}

function AtGlanceCard({
  title,
  body,
  glanceOrder,
}: {
  title: string;
  body: ReactNode;
  glanceOrder: "1" | "2" | "3" | "4" | "5";
}) {
  return (
    <div
      className="flex h-full flex-col gap-3 rounded-md border border-[var(--mm-border)] bg-[var(--mm-card-bg)] p-5 text-sm"
      data-at-glance-order={glanceOrder}
    >
      <h3 className="text-sm font-semibold text-[var(--mm-text1)]">{title}</h3>
      <div className="min-h-0 flex-1 text-[var(--mm-text2)]">{body}</div>
    </div>
  );
}

const CLEANUP_OPTION_ROWS: { key: keyof FailedImportCleanupPolicyAxis; label: string }[] = [
  { key: "handling_quality_rejection", label: "Quality / not-an-upgrade" },
  { key: "handling_unmatched_manual_import", label: "Unmatched" },
  { key: "handling_sample_release", label: "Sample / junk" },
  { key: "handling_corrupt_import", label: "Corrupt" },
  { key: "handling_failed_download", label: "Download failed" },
  { key: "handling_failed_import", label: "Import failed" },
];

function countEnabledCleanupOptions(axis: FailedImportCleanupPolicyAxis): number {
  return CLEANUP_OPTION_ROWS.reduce((acc, { key }) => acc + (axis[key] !== "leave_alone" ? 1 : 0), 0);
}

function atGlanceFailedImportCleanupSummary(axis: FailedImportCleanupPolicyAxis): string {
  const n = countEnabledCleanupOptions(axis);
  if (n === 0) {
    return "All leave alone";
  }
  if (n === 1) {
    return "1 class with an action";
  }
  return `${n} classes with actions`;
}

function glanceSearchLine(configured: boolean, enabled: boolean): string {
  return configured ? (enabled ? "On" : "Off") : "Not set up yet";
}

function formatLastChecked(iso: string | null): string | null {
  if (!iso) {
    return null;
  }
  const d = new Date(iso);
  if (Number.isNaN(d.valueOf())) {
    return null;
  }
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(d);
}

function FetcherOverviewAtAGlance({
  arr,
  policy,
}: {
  arr: FetcherArrOperatorSettingsOut;
  policy: FetcherFailedImportCleanupPolicyOut;
}) {
  const statsQ = useFetcherOverviewStatsQuery();

  const last30Body =
    statsQ.isPending ? (
      <p className="text-[var(--mm-text3)]">Loading…</p>
    ) : statsQ.isError ? (
      <p className="text-red-400">{(statsQ.error as Error).message}</p>
    ) : statsQ.data ? (
      <div className="space-y-1.5">
        <p>
          <span className="text-[var(--mm-text3)]">Sonarr searches:</span>{" "}
          <span className="font-medium text-[var(--mm-text1)]">
            {statsQ.data.sonarr_missing_searches} missing · {statsQ.data.sonarr_upgrade_searches} upgrades
          </span>
        </p>
        <p>
          <span className="text-[var(--mm-text3)]">Radarr searches:</span>{" "}
          <span className="font-medium text-[var(--mm-text1)]">
            {statsQ.data.radarr_missing_searches} missing · {statsQ.data.radarr_upgrade_searches} upgrades
          </span>
        </p>
        <p>
          <span className="text-[var(--mm-text3)]">Total:</span>{" "}
          <span className="font-medium text-[var(--mm-text1)]">{statsQ.data.total_searches} searches</span>
        </p>
        <p>
          <span className="text-[var(--mm-text3)]">Failed jobs:</span>{" "}
          <span className="font-medium text-[var(--mm-text1)]">
            {statsQ.data.failed_jobs === 0 ? "None" : String(statsQ.data.failed_jobs)}
          </span>
        </p>
      </div>
    ) : (
      <p className="text-[var(--mm-text3)]">—</p>
    );

  const sonarrBody = (
    <div className="space-y-1.5">
      <p>
        <span className="text-[var(--mm-text3)]">TV searches:</span>{" "}
        <span className="font-medium text-[var(--mm-text1)]">
          {glanceSearchLine(arr.sonarr_server_configured, arr.sonarr_missing.enabled)}
        </span>
      </p>
      <p>
        <span className="text-[var(--mm-text3)]">Upgrades:</span>{" "}
        <span className="font-medium text-[var(--mm-text1)]">
          {glanceSearchLine(arr.sonarr_server_configured, arr.sonarr_upgrade.enabled)}
        </span>
      </p>
    </div>
  );

  const radarrBody = (
    <div className="space-y-1.5">
      <p>
        <span className="text-[var(--mm-text3)]">Movie searches:</span>{" "}
        <span className="font-medium text-[var(--mm-text1)]">
          {glanceSearchLine(arr.radarr_server_configured, arr.radarr_missing.enabled)}
        </span>
      </p>
      <p>
        <span className="text-[var(--mm-text3)]">Upgrades:</span>{" "}
        <span className="font-medium text-[var(--mm-text1)]">
          {glanceSearchLine(arr.radarr_server_configured, arr.radarr_upgrade.enabled)}
        </span>
      </p>
    </div>
  );

  const connBody = (
    <div className="space-y-1.5">
      <p>
        <span className="text-[var(--mm-text3)]">{FETCHER_CONNECTION_PANEL_SONARR}:</span>{" "}
        <span className="font-medium text-[var(--mm-text1)]">
          {arr.sonarr_server_configured ? "Connected" : "Not set up yet"}
        </span>
      </p>
      <p>
        <span className="text-[var(--mm-text3)]">{FETCHER_CONNECTION_PANEL_RADARR}:</span>{" "}
        <span className="font-medium text-[var(--mm-text1)]">
          {arr.radarr_server_configured ? "Connected" : "Not set up yet"}
        </span>
      </p>
    </div>
  );

  const fiBody = (
    <div className="space-y-1.5">
      <p>
        <span className="text-[var(--mm-text3)]">Sonarr (TV):</span>{" "}
        <span className="font-medium text-[var(--mm-text1)]">{atGlanceFailedImportCleanupSummary(policy.tv_shows)}</span>
      </p>
      <p>
        <span className="text-[var(--mm-text3)]">Radarr (Movies):</span>{" "}
        <span className="font-medium text-[var(--mm-text1)]">{atGlanceFailedImportCleanupSummary(policy.movies)}</span>
      </p>
    </div>
  );

  return (
    <section
      className="mm-card mm-dash-card mm-fetcher-module-surface"
      aria-labelledby="fetcher-overview-at-a-glance-heading"
      data-testid="fetcher-overview-at-a-glance"
      data-overview-order="1"
    >
      <h2 id="fetcher-overview-at-a-glance-heading" className="mm-card__title text-lg">
        At a glance
      </h2>
      <div className="mm-card__body mt-5 grid gap-4 sm:grid-cols-2 sm:gap-x-5 sm:gap-y-5 xl:grid-cols-5 xl:gap-x-5 xl:gap-y-5">
        <AtGlanceCard glanceOrder="1" title="Last 30 days" body={last30Body} />
        <AtGlanceCard glanceOrder="2" title="Connections" body={connBody} />
        <AtGlanceCard glanceOrder="3" title={FETCHER_CONNECTION_PANEL_SONARR} body={sonarrBody} />
        <AtGlanceCard glanceOrder="4" title={FETCHER_CONNECTION_PANEL_RADARR} body={radarrBody} />
        <AtGlanceCard glanceOrder="5" title="Failed imports" body={fiBody} />
      </div>
    </section>
  );
}

function buildNeedsAttentionItems(
  arr: FetcherArrOperatorSettingsOut,
  attention: FetcherFailedImportQueueAttentionSnapshot,
): { text: string; target?: FetcherOverviewOpenSection }[] {
  const items: { text: string; target?: FetcherOverviewOpenSection }[] = [];

  if (!arr.sonarr_server_configured) {
    items.push({ text: "Connect Sonarr to run TV searches", target: "connections" });
  } else if (!sonarrTvSearchesOn(arr)) {
    items.push({ text: "Turn on TV searches or upgrades for Sonarr", target: "sonarr" });
  }

  if (!arr.radarr_server_configured) {
    items.push({ text: "Connect Radarr to run movie searches", target: "connections" });
  } else if (!radarrMovieSearchesOn(arr)) {
    items.push({ text: "Turn on movie searches or upgrades for Radarr", target: "radarr" });
  }

  if (
    arr.sonarr_server_configured &&
    attention.tv_shows.needs_attention_count !== null &&
    attention.tv_shows.needs_attention_count > 0
  ) {
    items.push({ text: "Sonarr (TV) failed imports need attention", target: "failed-imports" });
  }

  if (
    arr.radarr_server_configured &&
    attention.movies.needs_attention_count !== null &&
    attention.movies.needs_attention_count > 0
  ) {
    items.push({ text: "Radarr (Movies) failed imports need attention", target: "failed-imports" });
  }

  return items.slice(0, 3);
}

const NEEDS_ATTENTION_ACTION_ORDER: FetcherOverviewOpenSection[] = [
  "connections",
  "sonarr",
  "radarr",
  "failed-imports",
];

function needsAttentionActionLabel(target: FetcherOverviewOpenSection): string {
  switch (target) {
    case "connections":
      return "Open Connections";
    case "sonarr":
      return `Open ${FETCHER_TAB_SONARR_LABEL}`;
    case "radarr":
      return `Open ${FETCHER_TAB_RADARR_LABEL}`;
    case "failed-imports":
      return "Open Failed imports";
    default: {
      const _exhaustive: never = target;
      return _exhaustive;
    }
  }
}

function FetcherOverviewNeedsAttention({
  arr,
  attention,
  onOpenSection,
}: {
  arr: FetcherArrOperatorSettingsOut;
  attention: FetcherFailedImportQueueAttentionSnapshot;
  onOpenSection?: (target: FetcherOverviewOpenSection) => void;
}) {
  const raw = buildNeedsAttentionItems(arr, attention);
  const empty = raw.length === 0;
  const actionTargets = NEEDS_ATTENTION_ACTION_ORDER.filter((t) => raw.some((row) => row.target === t));

  return (
    <section
      className="mm-card mm-dash-card mm-fetcher-module-surface"
      aria-labelledby="fetcher-overview-needs-attention-heading"
      data-testid="fetcher-overview-needs-attention"
      data-overview-order="2"
    >
      <h2 id="fetcher-overview-needs-attention-heading" className="mm-card__title text-lg">
        Needs attention
      </h2>
      <div className="mm-card__body mt-5 text-sm text-[var(--mm-text2)]">
        {empty ? (
          <p>No action needed right now</p>
        ) : (
          <>
            <ul className="list-none space-y-3 border-l-2 border-[var(--mm-border)] pl-3.5">
              {raw.map((row, i) => (
                <li key={`${row.text}-${i}`} className="leading-snug text-[var(--mm-text1)]">
                  {row.text}
                </li>
              ))}
            </ul>
            {onOpenSection && actionTargets.length > 0 ? (
              <div className="mt-5 flex flex-wrap gap-2.5 border-t border-[var(--mm-border)] pt-4">
                {actionTargets.map((target) => (
                  <button
                    key={target}
                    type="button"
                    className={fetcherMenuButtonClass({ variant: "secondary" })}
                    onClick={() => onOpenSection(target)}
                  >
                    {needsAttentionActionLabel(target)}
                  </button>
                ))}
              </div>
            ) : null}
          </>
        )}
      </div>
    </section>
  );
}

export const FETCHER_OVERVIEW_FI_NEEDS_ATTENTION_SUBTEXT =
  "Same count as on Failed imports: queue rows that match a known failure class and have a non–leave-alone action saved for that app (not proof that a cleanup run already failed).";

function failedImportAttentionStatusLine(
  configured: boolean,
  cleanupEnabledCount: number,
  axis: FetcherFailedImportQueueAttentionAxis,
): string {
  if (!configured) {
    return "Not set up yet";
  }
  if (axis.needs_attention_count === null) {
    return "Can't check right now";
  }
  const n = axis.needs_attention_count;
  if (n > 0) {
    return n === 1 ? "1 failed import still needs attention" : `${n} failed imports still need attention`;
  }
  if (cleanupEnabledCount === 0) {
    return "No classes configured for queue actions";
  }
  return "No failed imports need attention";
}

function FailedImportAttentionCard({
  title,
  configured,
  axis,
  policyAxis,
}: {
  title: string;
  configured: boolean;
  axis: FetcherFailedImportQueueAttentionAxis;
  policyAxis: FailedImportCleanupPolicyAxis;
}) {
  const enabledLabels = CLEANUP_OPTION_ROWS.filter(({ key }) => policyAxis[key] !== "leave_alone").map(
    (r) => r.label,
  );
  const cleanupEnabledCount = enabledLabels.length;
  const last = formatLastChecked(axis.last_checked_at);
  const statusLine = failedImportAttentionStatusLine(configured, cleanupEnabledCount, axis);

  return (
    <div className="flex h-full min-h-[1px] flex-col rounded-md border border-[var(--mm-border)] bg-[var(--mm-surface2)]/40 p-5 text-sm">
      <h3 className="text-sm font-semibold text-[var(--mm-text1)]">{title}</h3>
      <div className="flex min-h-0 flex-1 flex-col pt-4">
        <div className="shrink-0 space-y-5">
          <div className="space-y-1">
            <p className="text-xs font-medium tracking-wide text-[var(--mm-text3)]">Classes with an action</p>
            {cleanupEnabledCount === 0 ? (
              <p className="text-sm font-semibold text-[var(--mm-text1)]">None</p>
            ) : (
              <ul className="space-y-1.5 text-sm font-semibold text-[var(--mm-text1)]">
                {enabledLabels.map((label) => (
                  <li key={label} className="leading-snug">
                    {label}
                  </li>
                ))}
              </ul>
            )}
          </div>
          <div className="space-y-1">
            <p className="text-xs font-medium tracking-wide text-[var(--mm-text3)]">Status</p>
            <p className="text-sm font-semibold leading-snug text-[var(--mm-text1)]">{statusLine}</p>
          </div>
        </div>
        <div className="mt-5 flex min-h-0 flex-1 flex-col justify-end">
          {last ? (
            <div className="space-y-1 border-t border-[var(--mm-border)]/80 pt-4">
              <p className="text-xs font-medium tracking-wide text-[var(--mm-text3)]">Last checked</p>
              <p className="text-sm font-semibold text-[var(--mm-text1)]">{last}</p>
            </div>
          ) : (
            <div className="min-h-0 flex-1" aria-hidden />
          )}
        </div>
      </div>
    </div>
  );
}

function FetcherOverviewFailedImportsThatNeedAttention({
  arr,
  attention,
  policy,
}: {
  arr: FetcherArrOperatorSettingsOut;
  attention: FetcherFailedImportQueueAttentionSnapshot;
  policy: FetcherFailedImportCleanupPolicyOut;
}) {
  return (
    <section
      className="mm-card mm-dash-card mm-fetcher-module-surface"
      aria-labelledby="fetcher-overview-fi-needs-attention-heading"
      data-testid="fetcher-overview-fi-needs-attention"
      data-overview-order="4"
    >
      <h2 id="fetcher-overview-fi-needs-attention-heading" className="mm-card__title text-lg">
        Failed imports that need attention
      </h2>
      <div className="mm-card__body space-y-3 text-sm">
        <p className="mm-card__body--tight leading-relaxed text-[var(--mm-text3)]">{FETCHER_OVERVIEW_FI_NEEDS_ATTENTION_SUBTEXT}</p>
        <div className="mt-5 grid items-stretch gap-4 md:grid-cols-2 md:gap-x-5 md:gap-y-4">
          <FailedImportAttentionCard
            title={FETCHER_TAB_SONARR_LABEL}
            configured={arr.sonarr_server_configured}
            axis={attention.tv_shows}
            policyAxis={policy.tv_shows}
          />
          <FailedImportAttentionCard
            title={FETCHER_TAB_RADARR_LABEL}
            configured={arr.radarr_server_configured}
            axis={attention.movies}
            policyAxis={policy.movies}
          />
        </div>
      </div>
    </section>
  );
}

function FetcherOverviewLoadError({ err }: { err: unknown }) {
  return (
    <div className="mm-page__intro" data-testid="fetcher-overview-load-error">
      <p className="mm-page__lead">
        {isLikelyNetworkFailure(err)
          ? "Could not reach the MediaMop API. Check that the backend is running."
          : isHttpErrorFromApi(err)
            ? "The server refused this request. Sign in again or check API logs."
            : "Could not load part of the Overview snapshot."}
      </p>
      {err instanceof Error ? (
        <p className="mm-page__lead font-mono text-sm text-[var(--mm-text3)]">{err.message}</p>
      ) : null}
    </div>
  );
}

/** Overview tab — At a glance → Needs attention → Current search setup → Failed imports that need attention. */
export function FetcherOverviewTab({
  onOpenSection,
}: {
  onOpenSection?: (target: FetcherOverviewOpenSection) => void;
} = {}) {
  const arr = useFetcherArrOperatorSettingsQuery();
  const attention = useFailedImportQueueAttentionSnapshotQuery();
  const cleanupPolicy = useFailedImportCleanupPolicyQuery();

  const blocking = arr.isError ? arr.error : attention.isError ? attention.error : cleanupPolicy.isError ? cleanupPolicy.error : null;

  if (blocking) {
    return <FetcherOverviewLoadError err={blocking} />;
  }

  if (arr.isPending || attention.isPending || cleanupPolicy.isPending) {
    return <PageLoading label="Loading Overview" />;
  }

  if (!arr.data || !attention.data || !cleanupPolicy.data) {
    return <PageLoading label="Loading Overview" />;
  }

  return (
    <div data-testid="fetcher-overview-panel" className="space-y-6 sm:space-y-7">
      <FetcherOverviewAtAGlance arr={arr.data} policy={cleanupPolicy.data} />
      <FetcherOverviewNeedsAttention arr={arr.data} attention={attention.data} onOpenSection={onOpenSection} />
      <FetcherCurrentSearchSetupSection arr={arr.data} />
      <FetcherOverviewFailedImportsThatNeedAttention arr={arr.data} attention={attention.data} policy={cleanupPolicy.data} />
    </div>
  );
}
