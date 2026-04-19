import { PageLoading } from "../../components/shared/page-loading";
import {
  MmAtGlanceCard,
  MmAtGlanceGrid,
  MmNeedsAttentionList,
  MmNextStepsButton,
  MmOverviewSection,
  MmStatCaption,
  MmStatTile,
  MmStatTileRow,
} from "../../components/overview/mm-overview-cards";
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
      <MmStatTileRow>
        <MmStatTile label="Sonarr" value={sonarrSearches} />
        <MmStatTile label="Radarr" value={radarrSearches} />
        <MmStatTile label="Failed" value={failedJobs} />
      </MmStatTileRow>
      <MmStatCaption>Missing and upgrade searches combined · last 30 days</MmStatCaption>
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
    <MmOverviewSection
      headingId="fetcher-overview-at-a-glance-heading"
      heading="At a glance"
      data-testid="fetcher-overview-at-a-glance"
      data-overview-order="1"
    >
      <MmAtGlanceGrid>
        <MmAtGlanceCard glanceOrder="1" title="Last 30 days" body={last30Body} />
        <MmAtGlanceCard
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
        <MmAtGlanceCard
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
      </MmAtGlanceGrid>
    </MmOverviewSection>
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
  const actionTargets = NEEDS_ATTENTION_ACTION_ORDER.filter((t) => raw.some((row) => row.target === t));

  return (
    <MmOverviewSection
      headingId="fetcher-overview-needs-attention-heading"
      heading="Needs attention"
      data-testid="fetcher-overview-needs-attention"
      data-overview-order="2"
    >
      <MmNeedsAttentionList
        items={raw.map((row) => row.text)}
        emptyMessage="No action needed right now"
        actions={
          onOpenSection && actionTargets.length > 0 ? (
            <>
              {actionTargets.map((target) => (
                <MmNextStepsButton key={target} label={needsAttentionActionLabel(target)} onClick={() => onOpenSection(target)} />
              ))}
            </>
          ) : undefined
        }
      />
    </MmOverviewSection>
  );
}

const NEXT_STEPS_BODY =
  "Use Connections to set up Sonarr and Radarr, Sonarr (TV) and Radarr (Movies) to configure search settings, Failed imports to manage import cleanup, and Activity for a full history.";

function FetcherOverviewNextSteps({ onOpenSection }: { onOpenSection?: (target: FetcherOverviewOpenSection) => void }) {
  return (
    <MmOverviewSection
      headingId="fetcher-overview-next-steps-heading"
      heading="Next steps"
      data-testid="fetcher-overview-next-steps"
      data-overview-order="3"
    >
      <div className="space-y-5">
        <p className="leading-relaxed">{NEXT_STEPS_BODY}</p>
        {onOpenSection ? (
          <div className="flex flex-wrap gap-2.5 border-t border-[var(--mm-border)] pt-4">
            <MmNextStepsButton label="Connections" onClick={() => onOpenSection("connections")} />
            <MmNextStepsButton label={FETCHER_TAB_SONARR_LABEL} onClick={() => onOpenSection("sonarr")} />
            <MmNextStepsButton label={FETCHER_TAB_RADARR_LABEL} onClick={() => onOpenSection("radarr")} />
            <MmNextStepsButton label="Failed imports" onClick={() => onOpenSection("failed-imports")} />
          </div>
        ) : null}
      </div>
    </MmOverviewSection>
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
