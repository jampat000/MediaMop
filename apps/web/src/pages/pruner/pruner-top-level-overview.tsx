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
import type { PrunerServerInstance } from "../../lib/pruner/api";
import {
  usePrunerJobsInspectionQuery,
  usePrunerOverviewStatsQuery,
} from "../../lib/pruner/queries";
import type { ProviderTab, TopTab } from "./pruner-page-types";
import {
  activeRuleCount,
  parseServerInstanceId,
  providerLabel,
} from "./pruner-page-utils";
import { prunerJobKindOperatorLabel } from "./pruner-ui-utils";

function scanOutcomeReadable(o: string | null | undefined): string {
  if (!o) return "\u2014";
  const u = o.toLowerCase();
  if (u === "success") return "Finished OK";
  if (u === "failed") return "Failed";
  if (u === "unsupported") return "Not available";
  return o;
}

function buildPrunerNeedsAttention(
  instances: PrunerServerInstance[],
): { text: string; tab: ProviderTab }[] {
  const items: { text: string; tab: ProviderTab }[] = [];
  if (instances.length === 0) {
    items.push({
      text: "No Emby, Jellyfin, or Plex servers connected \u2014 add one under Emby, Jellyfin, or Plex.",
      tab: "emby",
    });
    return items;
  }
  for (const inst of instances) {
    if (inst.last_connection_test_ok === false) {
      const label = providerLabel(inst.provider as ProviderTab);
      items.push({
        text: `${label} (${inst.display_name}) connection test failed \u2014 check Connection tab.`,
        tab: inst.provider as ProviderTab,
      });
    }
  }
  const allRulesZero = instances.every((inst) =>
    inst.scopes.every((sc) => activeRuleCount(sc) === 0),
  );
  if (allRulesZero) {
    items.push({
      text: "No cleanup rules are enabled \u2014 turn on rules in the Cleanup tab.",
      tab: "emby",
    });
  }
  return items.slice(0, 8);
}

const PRUNER_ATTENTION_TAB_ORDER: ProviderTab[] = ["emby", "jellyfin", "plex"];

function prunerAttentionOpenLabel(tab: ProviderTab): string {
  return `Open ${providerLabel(tab)}`;
}

function PrunerLast30StatsTiles({
  itemsRemoved,
  previewRuns,
  failedApplies,
}: {
  itemsRemoved: number;
  previewRuns: number;
  failedApplies: number;
}) {
  return (
    <div>
      <MmStatTileRow>
        <MmStatTile label="Removed" value={itemsRemoved} />
        <MmStatTile label="Preview" value={previewRuns} />
        <MmStatTile label="Failed" value={failedApplies} />
      </MmStatTileRow>
      <MmStatCaption>Library cleanup activity \u00b7 last 30 days</MmStatCaption>
    </div>
  );
}

const PRUNER_NEXT_STEPS_BODY =
  "Use Emby, Jellyfin, or Plex to connect your media server and configure cleanup rules. Check Jobs for recent activity. Use Schedule for timed scans and optional hour limits.";

function PrunerOverviewNextSteps({ onNavigate }: { onNavigate: (tab: TopTab) => void }) {
  return (
    <MmOverviewSection
      headingId="pruner-overview-next-steps-heading"
      heading="Next steps"
      data-testid="pruner-overview-next-steps"
      data-overview-order="3"
    >
      <div className="mm-bubble-stack">
        <p className="leading-relaxed">{PRUNER_NEXT_STEPS_BODY}</p>
        <div className="flex flex-wrap gap-2.5 border-t border-[var(--mm-border)] pt-4">
          <MmNextStepsButton label="Emby" onClick={() => onNavigate("emby")} />
          <MmNextStepsButton
            label="Jellyfin"
            onClick={() => onNavigate("jellyfin")}
          />
          <MmNextStepsButton label="Plex" onClick={() => onNavigate("plex")} />
          <MmNextStepsButton label="Jobs" onClick={() => onNavigate("jobs")} />
          <MmNextStepsButton
            label="Schedule"
            onClick={() => onNavigate("schedule")}
          />
        </div>
      </div>
    </MmOverviewSection>
  );
}

function PrunerOverviewNeedsAttention({
  items,
  onOpenProviderTab,
}: {
  items: { text: string; tab: ProviderTab }[];
  onOpenProviderTab: (tab: ProviderTab) => void;
}) {
  const actionTabs = PRUNER_ATTENTION_TAB_ORDER.filter((t) =>
    items.some((row) => row.tab === t),
  );
  return (
    <MmOverviewSection
      headingId="pruner-overview-needs-attention-heading"
      heading="Needs attention"
      data-testid="pruner-overview-needs-attention"
      data-overview-order="2"
    >
      <MmNeedsAttentionList
        items={items.map((row) => row.text)}
        actions={
          actionTabs.length > 0 ? (
            <>
              {actionTabs.map((tab) => (
                <MmNextStepsButton
                  key={tab}
                  label={prunerAttentionOpenLabel(tab)}
                  onClick={() => onOpenProviderTab(tab)}
                />
              ))}
            </>
          ) : undefined
        }
      />
    </MmOverviewSection>
  );
}

export function TopLevelOverview({
  instances,
  onOpenProviderTab,
  onNavigateTopTab,
}: {
  instances: PrunerServerInstance[];
  onOpenProviderTab: (tab: ProviderTab) => void;
  onNavigateTopTab: (tab: TopTab) => void;
}) {
  const jobsQ = usePrunerJobsInspectionQuery(50);
  const statsQ = usePrunerOverviewStatsQuery();
  const providers: ProviderTab[] = ["emby", "jellyfin", "plex"];
  const providerCards = providers.map((provider) => {
    const rows = instances.filter((x) => x.provider === provider);
    const first = rows[0];
    const scopeRows = first?.scopes ?? [];
    const activeRules = scopeRows.reduce(
      (acc, scope) => acc + activeRuleCount(scope),
      0,
    );
    const previews = scopeRows.filter((scope) => scope.last_preview_at);
    const latestPreview = previews.sort((a, b) =>
      String(b.last_preview_at ?? "").localeCompare(String(a.last_preview_at ?? "")),
    )[0];
    const providerJobs = jobsQ.data?.jobs?.filter((j) => {
      const sid = parseServerInstanceId(j);
      return sid != null && rows.some((row) => row.id === sid);
    });
    const latestApplyLike =
      providerJobs?.find((j) => String(j.job_kind).toLowerCase().includes("apply")) ??
      providerJobs?.[0];
    return {
      provider,
      first,
      activeRules,
      latestPreview,
      latestJob: latestApplyLike,
    };
  });

  const attentionItems = buildPrunerNeedsAttention(instances);

  const last30Body = statsQ.isPending ? (
    <p className="text-[var(--mm-text3)]">Loading...</p>
  ) : statsQ.isError ? (
    <p className="text-red-400">{(statsQ.error as Error).message}</p>
  ) : statsQ.data ? (
    <PrunerLast30StatsTiles
      itemsRemoved={statsQ.data.items_removed}
      previewRuns={statsQ.data.preview_runs}
      failedApplies={statsQ.data.failed_applies}
    />
  ) : (
    <p className="text-[var(--mm-text3)]">\u2014</p>
  );

  return (
    <section className="mm-bubble-stack" data-testid="pruner-top-overview-tab">
      <MmOverviewSection
        headingId="pruner-overview-at-a-glance-heading"
        heading="At a glance"
        data-testid="pruner-overview-at-a-glance"
        data-overview-order="1"
      >
        <MmAtGlanceGrid className="grid grid-cols-1 gap-4 sm:grid-cols-2 sm:gap-x-5 sm:gap-y-5 lg:grid-cols-12 lg:gap-x-5 lg:gap-y-6">
          <MmAtGlanceCard
            glanceOrder="1"
            title="Last 30 days"
            emphasis
            body={last30Body}
            gridClassName="lg:col-span-4"
          />
          {providerCards.map((card, i) => {
            const order = String(i + 2) as "2" | "3" | "4";
            const providerGridClass =
              i === 2 ? "sm:col-span-2 lg:col-span-12" : "lg:col-span-4";
            const body = card.first ? (
              <div className="space-y-1.5">
                <p>
                  <span className="text-[var(--mm-text3)]">Connection test:</span>{" "}
                  <span className="font-medium text-[var(--mm-text1)]">
                    {card.first.last_connection_test_ok == null
                      ? "Not run yet"
                      : card.first.last_connection_test_ok
                        ? "OK"
                        : "Failed"}
                  </span>
                </p>
                <p>
                  <span className="text-[var(--mm-text3)]">Cleanup rules on:</span>{" "}
                  <span className="font-medium text-[var(--mm-text1)]">
                    {card.activeRules}
                  </span>
                </p>
                <p>
                  <span className="text-[var(--mm-text3)]">Last library scan:</span>{" "}
                  <span className="font-medium text-[var(--mm-text1)]">
                    {card.latestPreview
                      ? `${card.latestPreview.media_scope === "tv" ? "TV" : "Movies"} \u00b7 ${scanOutcomeReadable(card.latestPreview.last_preview_outcome)}`
                      : "\u2014"}
                  </span>
                </p>
                <p>
                  <span className="text-[var(--mm-text3)]">Recent task:</span>{" "}
                  <span className="font-medium text-[var(--mm-text1)]">
                    {card.latestJob
                      ? `${prunerJobKindOperatorLabel(card.latestJob.job_kind)} (${card.latestJob.status})`
                      : "\u2014"}
                  </span>
                </p>
              </div>
            ) : (
              <p className="text-[var(--mm-text2)]">
                No server saved yet. Add the address and key on that provider&apos;s
                Connection tab.
              </p>
            );
            return (
              <MmAtGlanceCard
                key={card.provider}
                glanceOrder={order}
                title={providerLabel(card.provider)}
                body={body}
                gridClassName={providerGridClass}
                footer={
                  card.provider === "emby" ? (
                    <MmNextStepsButton
                      label="Open Emby"
                      onClick={() => onNavigateTopTab("emby")}
                    />
                  ) : card.provider === "jellyfin" ? (
                    <MmNextStepsButton
                      label="Open Jellyfin"
                      onClick={() => onNavigateTopTab("jellyfin")}
                    />
                  ) : (
                    <MmNextStepsButton
                      label="Open Plex"
                      onClick={() => onNavigateTopTab("plex")}
                    />
                  )
                }
              />
            );
          })}
        </MmAtGlanceGrid>
      </MmOverviewSection>

      <PrunerOverviewNeedsAttention
        items={attentionItems}
        onOpenProviderTab={onOpenProviderTab}
      />

      <PrunerOverviewNextSteps onNavigate={onNavigateTopTab} />
    </section>
  );
}
