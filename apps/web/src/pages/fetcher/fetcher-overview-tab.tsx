import { PageLoading } from "../../components/shared/page-loading";
import { OverviewAtGlanceCard } from "../../components/overview/overview-at-glance-card";
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
  FetcherFailedImportQueueAttentionSnapshot,
} from "../../lib/fetcher/failed-imports/types";
import { mmActionButtonClass } from "../../lib/ui/mm-control-roles";
import {
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

function onOff(enabled: boolean): string {
  return enabled ? "On" : "Off";
}

function FetcherOverviewLast30Tiles({
  sonarrSearches,
  radarrSearches,
  failedJobs,
}: {
  sonarrSearches: number;
  radarrSearches: number;
  failedJobs: number;
}) {
  return (
    <div>
      <div className="grid grid-cols-3 gap-2 sm:gap-3">
        <div className="rounded-md bg-black/15 px-2 py-3 text-center sm:px-3">
          <span className="block text-[0.65rem] font-semibold uppercase tracking-wide text-[var(--mm-text3)]">Sonarr</span>
          <span className="mt-1 block text-2xl font-bold tabular-nums leading-none text-[var(--mm-text1)]">{sonarrSearches}</span>
        </div>
        <div className="rounded-md bg-black/15 px-2 py-3 text-center sm:px-3">
          <span className="block text-[0.65rem] font-semibold uppercase tracking-wide text-[var(--mm-text3)]">Radarr</span>
          <span className="mt-1 block text-2xl font-bold tabular-nums leading-none text-[var(--mm-text1)]">{radarrSearches}</span>
        </div>
        <div className="rounded-md bg-black/15 px-2 py-3 text-center sm:px-3">
          <span className="block text-[0.65rem] font-semibold uppercase tracking-wide text-[var(--mm-text3)]">Failed</span>
          <span className="mt-1 block text-2xl font-bold tabular-nums leading-none text-[var(--mm-text1)]">{failedJobs}</span>
        </div>
      </div>
      <p className="mt-4 text-[0.7rem] leading-snug text-[var(--mm-text3)]">
        Missing and upgrade searches combined · last 30 days
      </p>
    </div>
  );
}

function FetcherOverviewAtAGlance({
  arr,
  policy,
  attention,
  onOpenSection,
}: {
  arr: FetcherArrOperatorSettingsOut;
  policy: FetcherFailedImportCleanupPolicyOut;
  attention: FetcherFailedImportQueueAttentionSnapshot;
  onOpenSection?: (target: FetcherOverviewOpenSection) => void;
}) {
  const statsQ = useFetcherOverviewStatsQuery();

  const last30Body =
    statsQ.isPending ? (
      <p className="text-[var(--mm-text3)]">Loading…</p>
    ) : statsQ.isError ? (
      <p className="text-red-400">{(statsQ.error as Error).message}</p>
    ) : statsQ.data ? (
      <FetcherOverviewLast30Tiles
        sonarrSearches={statsQ.data.sonarr_missing_searches + statsQ.data.sonarr_upgrade_searches}
        radarrSearches={statsQ.data.radarr_missing_searches + statsQ.data.radarr_upgrade_searches}
        failedJobs={statsQ.data.failed_jobs}
      />
    ) : (
      <p className="text-[var(--mm-text3)]">—</p>
    );

  const connBody = (
    <div className="space-y-4">
      <div className="space-y-2">
        <p className="text-xs font-semibold uppercase tracking-wide text-[var(--mm-text3)]">Sonarr</p>
        {arr.sonarr_server_configured ? (
          <div className="space-y-1.5">
            <p className="font-medium text-[var(--mm-text1)]">Connected</p>
            <p>
              <span className="text-[var(--mm-text3)]">Searches:</span>{" "}
              <span className="font-medium text-[var(--mm-text1)]">{onOff(arr.sonarr_missing.enabled)}</span>
            </p>
            <p>
              <span className="text-[var(--mm-text3)]">Upgrades:</span>{" "}
              <span className="font-medium text-[var(--mm-text1)]">{onOff(arr.sonarr_upgrade.enabled)}</span>
            </p>
          </div>
        ) : (
          <p className="font-medium text-[var(--mm-text1)]">Not set up yet</p>
        )}
      </div>
      <div className="border-t border-[var(--mm-border)] pt-4">
        <div className="space-y-2">
          <p className="text-xs font-semibold uppercase tracking-wide text-[var(--mm-text3)]">Radarr</p>
          {arr.radarr_server_configured ? (
            <div className="space-y-1.5">
              <p className="font-medium text-[var(--mm-text1)]">Connected</p>
              <p>
                <span className="text-[var(--mm-text3)]">Searches:</span>{" "}
                <span className="font-medium text-[var(--mm-text1)]">{onOff(arr.radarr_missing.enabled)}</span>
              </p>
              <p>
                <span className="text-[var(--mm-text3)]">Upgrades:</span>{" "}
                <span className="font-medium text-[var(--mm-text1)]">{onOff(arr.radarr_upgrade.enabled)}</span>
              </p>
            </div>
          ) : (
            <p className="font-medium text-[var(--mm-text1)]">Not set up yet</p>
          )}
        </div>
      </div>
    </div>
  );

  const tvN = attention.tv_shows.needs_attention_count;
  const movN = attention.movies.needs_attention_count;
  const tvNeeds =
    arr.sonarr_server_configured && tvN !== null && tvN > 0 ? (
      <p className="text-sm font-medium text-amber-500/95">
        {tvN === 1 ? "1 Sonarr item needs attention" : `${tvN} Sonarr items need attention`}
      </p>
    ) : null;
  const movNeeds =
    arr.radarr_server_configured && movN !== null && movN > 0 ? (
      <p className="text-sm font-medium text-amber-500/95">
        {movN === 1 ? "1 Radarr item needs attention" : `${movN} Radarr items need attention`}
      </p>
    ) : null;
  const anyNeedsLine = Boolean(tvNeeds || movNeeds);

  const fiBody = (
    <div className="space-y-4">
      <p>
        <span className="text-[var(--mm-text3)]">Sonarr (TV):</span>{" "}
        <span className="font-medium text-[var(--mm-text1)]">{atGlanceFailedImportCleanupSummary(policy.tv_shows)}</span>
      </p>
      <p>
        <span className="text-[var(--mm-text3)]">Radarr (Movies):</span>{" "}
        <span className="font-medium text-[var(--mm-text1)]">{atGlanceFailedImportCleanupSummary(policy.movies)}</span>
      </p>
      <div className="space-y-2 border-t border-[var(--mm-border)] pt-3">
        <p className="text-xs font-semibold uppercase tracking-wide text-[var(--mm-text3)]">Needs attention</p>
        {anyNeedsLine ? (
          <div className="space-y-1">
            {tvNeeds}
            {movNeeds}
          </div>
        ) : (
          <p className="text-sm text-[var(--mm-text1)]">No items need attention</p>
        )}
      </div>
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
      <div className="mm-card__body mt-5 grid grid-cols-1 gap-4 sm:gap-x-5 sm:gap-y-5 lg:grid-cols-3 lg:gap-x-5 lg:gap-y-5">
        <OverviewAtGlanceCard glanceOrder="1" title="Last 30 days" body={last30Body} />
        <OverviewAtGlanceCard
          glanceOrder="2"
          title="Connections"
          body={connBody}
          footer={
            onOpenSection ? (
              <button
                type="button"
                className={mmActionButtonClass({ variant: "secondary" })}
                onClick={() => onOpenSection("connections")}
              >
                Open Connections
              </button>
            ) : undefined
          }
        />
        <OverviewAtGlanceCard
          glanceOrder="3"
          title="Failed imports"
          body={fiBody}
          footer={
            onOpenSection ? (
              <button
                type="button"
                className={mmActionButtonClass({ variant: "secondary" })}
                onClick={() => onOpenSection("failed-imports")}
              >
                Open Failed imports
              </button>
            ) : undefined
          }
        />
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
      <div className="mm-card__body mt-5">
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

const NEXT_STEPS_BODY =
  "Use Connections to set up Sonarr and Radarr, Sonarr (TV) and Radarr (Movies) to configure search settings, Failed imports to manage import cleanup, and Activity for a full history.";

function FetcherOverviewNextSteps({ onOpenSection }: { onOpenSection?: (target: FetcherOverviewOpenSection) => void }) {
  return (
    <section
      className="mm-card mm-dash-card mm-fetcher-module-surface"
      aria-labelledby="fetcher-overview-next-steps-heading"
      data-testid="fetcher-overview-next-steps"
      data-overview-order="3"
    >
      <h2 id="fetcher-overview-next-steps-heading" className="mm-card__title text-lg">
        Next steps
      </h2>
      <div className="mm-card__body mt-5 space-y-5">
        <p className="leading-relaxed">{NEXT_STEPS_BODY}</p>
        {onOpenSection ? (
          <div className="flex flex-wrap gap-2.5 border-t border-[var(--mm-border)] pt-4">
            <button type="button" className={fetcherMenuButtonClass({ variant: "secondary" })} onClick={() => onOpenSection("connections")}>
              Connections
            </button>
            <button type="button" className={fetcherMenuButtonClass({ variant: "secondary" })} onClick={() => onOpenSection("sonarr")}>
              {FETCHER_TAB_SONARR_LABEL}
            </button>
            <button type="button" className={fetcherMenuButtonClass({ variant: "secondary" })} onClick={() => onOpenSection("radarr")}>
              {FETCHER_TAB_RADARR_LABEL}
            </button>
            <button type="button" className={fetcherMenuButtonClass({ variant: "secondary" })} onClick={() => onOpenSection("failed-imports")}>
              Failed imports
            </button>
          </div>
        ) : null}
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

/** Overview tab — At a glance → Needs attention → Next steps. */
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
      <FetcherOverviewAtAGlance
        arr={arr.data}
        policy={cleanupPolicy.data}
        attention={attention.data}
        onOpenSection={onOpenSection}
      />
      <FetcherOverviewNeedsAttention arr={arr.data} attention={attention.data} onOpenSection={onOpenSection} />
      <FetcherOverviewNextSteps onOpenSection={onOpenSection} />
    </div>
  );
}
