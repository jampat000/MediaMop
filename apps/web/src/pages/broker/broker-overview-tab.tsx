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
import { useBrokerConnectionQuery, useBrokerIndexersQuery } from "../../lib/broker/broker-queries";
import type { BrokerArrConnection, BrokerIndexer } from "../../lib/broker/broker-api";
import { useAppDateFormatter } from "../../lib/ui/mm-format-date";

export type BrokerOverviewOpenTab = "connections" | "indexers" | "search" | "jobs";

function StatusDot({ tone }: { tone: "ok" | "warn" | "bad" | "muted" }) {
  const cls =
    tone === "ok"
      ? "bg-emerald-500"
      : tone === "warn"
        ? "bg-amber-400"
        : tone === "bad"
          ? "bg-red-500"
          : "bg-[var(--mm-text3)]";
  return <span className={`inline-block h-2 w-2 shrink-0 rounded-full ${cls}`} aria-hidden="true" />;
}

function arrConfigured(c: BrokerArrConnection | undefined): boolean {
  return Boolean(c?.url?.trim());
}

function arrStatusTone(c: BrokerArrConnection | undefined): "ok" | "warn" | "bad" | "muted" {
  if (!arrConfigured(c)) {
    return "muted";
  }
  if (c?.last_sync_ok === false) {
    return "bad";
  }
  if (c?.last_sync_ok === true) {
    return "ok";
  }
  return "warn";
}

function buildNeedsAttention(args: {
  indexers: BrokerIndexer[];
  sonarr: BrokerArrConnection | undefined;
  radarr: BrokerArrConnection | undefined;
}): string[] {
  const { indexers, sonarr, radarr } = args;
  const items: string[] = [];

  const enabledCount = indexers.filter((i) => i.enabled).length;
  if (enabledCount === 0) {
    items.push("No indexers enabled — add and enable at least one");
  }

  if (!arrConfigured(sonarr)) {
    items.push("Sonarr connection not configured");
  }
  if (!arrConfigured(radarr)) {
    items.push("Radarr connection not configured");
  }

  if (arrConfigured(sonarr) && sonarr?.last_sync_ok === false) {
    const err = (sonarr.last_sync_error ?? "").trim();
    items.push(err ? `Sonarr sync failed: ${err}` : "Sonarr sync failed");
  }
  if (arrConfigured(radarr) && radarr?.last_sync_ok === false) {
    const err = (radarr.last_sync_error ?? "").trim();
    items.push(err ? `Radarr sync failed: ${err}` : "Radarr sync failed");
  }

  const failing = indexers.filter((i) => i.enabled && i.last_test_ok === false).length;
  if (failing > 0) {
    items.push(`${failing} indexer(s) failing health check`);
  }

  return items;
}

export function BrokerOverviewTab({ onOpenTab }: { onOpenTab: (tab: BrokerOverviewOpenTab) => void }) {
  const ix = useBrokerIndexersQuery();
  const son = useBrokerConnectionQuery("sonarr");
  const rad = useBrokerConnectionQuery("radarr");
  const fmt = useAppDateFormatter();

  if (ix.isPending || son.isPending || rad.isPending) {
    return <PageLoading />;
  }

  if (ix.isError || son.isError || rad.isError) {
    const err = (ix.error ?? son.error ?? rad.error) as Error;
    return (
      <p className="text-sm text-red-400" data-testid="broker-overview-tab">
        {err.message}
      </p>
    );
  }

  const indexers = ix.data ?? [];
  const sonarr = son.data;
  const radarr = rad.data;

  const enabled = indexers.filter((i) => i.enabled);
  const torrentN = enabled.filter((i) => i.protocol === "torrent").length;
  const usenetN = enabled.filter((i) => i.protocol === "usenet").length;

  const needs = buildNeedsAttention({ indexers, sonarr, radarr });

  return (
    <div className="space-y-8" data-testid="broker-overview-tab">
      <MmOverviewSection
        id="broker-overview-at-a-glance"
        headingId="broker-overview-at-a-glance-heading"
        heading="At a glance"
        data-overview-order="1"
      >
        <MmAtGlanceGrid className="grid grid-cols-1 gap-4 sm:gap-x-5 sm:gap-y-5 lg:grid-cols-2">
          <MmAtGlanceCard
            title="Indexers"
            glanceOrder="1"
            emphasis
            data-testid="broker-overview-indexers-glance"
            body={
              <div>
                <MmStatTileRow>
                  <MmStatTile label="Enabled" value={enabled.length} />
                  <MmStatTile label="Torrent" value={torrentN} />
                  <MmStatTile label="Usenet" value={usenetN} />
                </MmStatTileRow>
                <MmStatCaption>Active indexers across all protocols</MmStatCaption>
              </div>
            }
          />
          <MmAtGlanceCard
            title="Connections"
            glanceOrder="2"
            body={
              <div className="space-y-5">
                <div className="space-y-2">
                  <p className="text-xs font-semibold uppercase tracking-wide text-[var(--mm-text3)]">Sonarr</p>
                  <div className="flex items-center gap-2">
                    <StatusDot tone={arrStatusTone(sonarr)} />
                    <span className="font-medium text-[var(--mm-text1)]">
                      {arrConfigured(sonarr) ? "Connected" : "Not configured"}
                    </span>
                  </div>
                  <p className="text-xs text-[var(--mm-text2)]">
                    Last synced:{" "}
                    <span className="font-medium text-[var(--mm-text1)]">
                      {sonarr?.last_synced_at ? fmt(sonarr.last_synced_at) : "Never"}
                    </span>
                  </p>
                </div>
                <div className="border-t border-[var(--mm-border)] pt-4">
                  <div className="space-y-2">
                    <p className="text-xs font-semibold uppercase tracking-wide text-[var(--mm-text3)]">Radarr</p>
                    <div className="flex items-center gap-2">
                      <StatusDot tone={arrStatusTone(radarr)} />
                      <span className="font-medium text-[var(--mm-text1)]">
                        {arrConfigured(radarr) ? "Connected" : "Not configured"}
                      </span>
                    </div>
                    <p className="text-xs text-[var(--mm-text2)]">
                      Last synced:{" "}
                      <span className="font-medium text-[var(--mm-text1)]">
                        {radarr?.last_synced_at ? fmt(radarr.last_synced_at) : "Never"}
                      </span>
                    </p>
                  </div>
                </div>
              </div>
            }
          />
        </MmAtGlanceGrid>
      </MmOverviewSection>

      <MmOverviewSection
        headingId="broker-overview-needs-attention-heading"
        heading="Needs attention"
        data-testid="broker-overview-needs-attention"
        data-overview-order="2"
      >
        <MmNeedsAttentionList items={needs} />
      </MmOverviewSection>

      <MmOverviewSection
        headingId="broker-overview-next-steps-heading"
        heading="Next steps"
        data-testid="broker-overview-next-steps"
        data-overview-order="3"
      >
        <div className="space-y-5">
          <p className="leading-relaxed text-[var(--mm-text2)]">
            Add indexers, connect Sonarr and Radarr, then try a federated search across everything Broker knows
            about.
          </p>
          <div className="flex flex-wrap gap-2.5 border-t border-[var(--mm-border)] pt-4">
            <MmNextStepsButton label="Add indexers" onClick={() => onOpenTab("indexers")} />
            <MmNextStepsButton label="Configure Sonarr" onClick={() => onOpenTab("connections")} />
            <MmNextStepsButton label="Configure Radarr" onClick={() => onOpenTab("connections")} />
            <MmNextStepsButton label="Search now" onClick={() => onOpenTab("search")} />
          </div>
        </div>
      </MmOverviewSection>
    </div>
  );
}
