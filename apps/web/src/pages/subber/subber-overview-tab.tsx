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
import {
  isHttpErrorFromApi,
  isLikelyNetworkFailure,
} from "../../lib/api/error-guards";
import {
  useSubberOverviewQuery,
  useSubberProvidersQuery,
  useSubberSettingsQuery,
} from "../../lib/subber/subber-queries";
function formatWhen(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.valueOf())) return "—";
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(d);
}

type AttentionTarget = "settings" | "tv" | "movies";

type SubberOverviewNavTab = "settings" | "tv" | "movies" | "schedule" | "jobs";

const SUBBER_NEXT_STEPS_BODY =
  "Use Settings to connect OpenSubtitles, Sonarr, and Radarr. Check TV and Movies to see your library and search for missing subtitles. Use Schedule to automate searches and Jobs for recent activity.";

function SubberOverviewNextSteps({
  onOpenTab,
}: {
  onOpenTab?: (tab: SubberOverviewNavTab) => void;
}) {
  return (
    <MmOverviewSection
      headingId="subber-overview-next-steps-heading"
      heading="Next steps"
      data-testid="subber-overview-next-steps"
      data-overview-order="3"
    >
      <div className="mm-bubble-stack">
        <p className="leading-relaxed">{SUBBER_NEXT_STEPS_BODY}</p>
        {onOpenTab ? (
          <div className="flex flex-wrap gap-2.5 border-t border-[var(--mm-border)] pt-4">
            <MmNextStepsButton
              label="Settings"
              onClick={() => onOpenTab("settings")}
            />
            <MmNextStepsButton label="TV" onClick={() => onOpenTab("tv")} />
            <MmNextStepsButton
              label="Movies"
              onClick={() => onOpenTab("movies")}
            />
            <MmNextStepsButton
              label="Schedule"
              onClick={() => onOpenTab("schedule")}
            />
            <MmNextStepsButton label="Jobs" onClick={() => onOpenTab("jobs")} />
          </div>
        ) : null}
      </div>
    </MmOverviewSection>
  );
}

function buildSubberNeedsAttention(args: {
  settings: NonNullable<ReturnType<typeof useSubberSettingsQuery>["data"]>;
  providers: NonNullable<ReturnType<typeof useSubberProvidersQuery>["data"]>;
  stats: NonNullable<ReturnType<typeof useSubberOverviewQuery>["data"]>;
}): { text: string; target?: AttentionTarget }[] {
  const { settings: s, providers: plist, stats: st } = args;
  const items: { text: string; target?: AttentionTarget }[] = [];

  if (!s.opensubtitles_password_set || !s.opensubtitles_api_key_set) {
    items.push({
      text: "Configure OpenSubtitles in Settings to start downloading subtitles.",
      target: "settings",
    });
  }

  const enabledCount = plist.filter((p) => p.enabled).length;
  if (plist.length > 0 && enabledCount === 0) {
    items.push({
      text: "No subtitle providers are enabled — enable at least one in Settings.",
      target: "settings",
    });
  }

  const sonConnected =
    Boolean(s.sonarr_base_url?.trim()) && Boolean(s.sonarr_api_key_set);
  if (!sonConnected) {
    items.push({
      text: "Connect Sonarr in Settings to track your TV library.",
      target: "settings",
    });
  }
  const radConnected =
    Boolean(s.radarr_base_url?.trim()) && Boolean(s.radarr_api_key_set);
  if (!radConnected) {
    items.push({
      text: "Connect Radarr in Settings to track your Movies library.",
      target: "settings",
    });
  }

  if (sonConnected && st.tv_tracked === 0) {
    items.push({
      text: "TV library not synced — click Sync from Sonarr in Settings.",
      target: "settings",
    });
  }
  if (radConnected && st.movies_tracked === 0) {
    items.push({
      text: "Movies library not synced — click Sync from Radarr in Settings.",
      target: "settings",
    });
  }

  if (st.tv_missing > 0) {
    items.push({
      text:
        st.tv_missing === 1
          ? "One TV track still needs subtitles."
          : `${st.tv_missing} TV tracks still need subtitles.`,
      target: "tv",
    });
  }
  if (st.movies_missing > 0) {
    items.push({
      text:
        st.movies_missing === 1
          ? "One movie still needs subtitles."
          : `${st.movies_missing} movies still need subtitles.`,
      target: "movies",
    });
  }

  return items.slice(0, 8);
}

function SubberOverviewLoadError({ err }: { err: unknown }) {
  return (
    <div className="mm-page__intro" data-testid="subber-overview-load-error">
      <p className="mm-page__lead">
        {isLikelyNetworkFailure(err)
          ? "Could not reach the MediaMop API. Check that the backend is running."
          : isHttpErrorFromApi(err)
            ? "The server refused this request. Sign in again or check API logs."
            : "Could not load Subber overview."}
      </p>
      {err instanceof Error ? (
        <p className="mm-page__lead font-mono text-sm text-[var(--mm-text3)]">
          {err.message}
        </p>
      ) : null}
    </div>
  );
}

export function SubberOverviewTab({
  onOpenTab,
}: {
  onOpenTab?: (tab: SubberOverviewNavTab) => void;
} = {}) {
  const settingsQ = useSubberSettingsQuery();
  const providersQ = useSubberProvidersQuery();
  const overviewQ = useSubberOverviewQuery();

  const blocking = settingsQ.isError
    ? settingsQ.error
    : providersQ.isError
      ? providersQ.error
      : overviewQ.isError
        ? overviewQ.error
        : null;

  if (blocking) {
    return <SubberOverviewLoadError err={blocking} />;
  }

  if (settingsQ.isPending || providersQ.isPending || overviewQ.isPending) {
    return <PageLoading label="Loading Subber overview" />;
  }

  if (!settingsQ.data || !providersQ.data || !overviewQ.data) {
    return <PageLoading label="Loading Subber overview" />;
  }

  const s = settingsQ.data;
  const plist = providersQ.data;
  const st = overviewQ.data;

  const sonConnected = Boolean(
    s.sonarr_base_url?.trim() && s.sonarr_api_key_set,
  );
  const radConnected = Boolean(
    s.radarr_base_url?.trim() && s.radarr_api_key_set,
  );
  const enabledProviders = plist.filter((p) => p.enabled).length;
  const providerTotal = plist.length;
  const enabledProviderList = plist.filter((p) => p.enabled);

  const attentionItems = buildSubberNeedsAttention({
    settings: s,
    providers: plist,
    stats: st,
  });

  const providersGlanceBody = (
    <div className="space-y-1.5">
      {enabledProviderList.length > 0 ? (
        enabledProviderList.map((p) => (
          <p key={p.provider_key} className="text-[var(--mm-text1)]">
            {p.display_name}
          </p>
        ))
      ) : (
        <p className="text-[var(--mm-text3)]">No providers enabled</p>
      )}
      <p>
        <span className="text-[var(--mm-text3)]">Enabled:</span>{" "}
        <span className="font-medium text-[var(--mm-text1)]">
          {enabledProviders} of {providerTotal}
        </span>
      </p>
    </div>
  );

  const sonarrBody = (
    <div className="space-y-1.5">
      <p>
        <span className="text-[var(--mm-text3)]">Status:</span>{" "}
        <span className="font-medium text-[var(--mm-text1)]">
          {sonConnected ? "Credentials saved" : "Not configured"}
        </span>
      </p>
      <p>
        <span className="text-[var(--mm-text3)]">TV tracked:</span>{" "}
        <span className="font-medium text-[var(--mm-text1)]">
          {st.tv_tracked} episodes
        </span>
      </p>
      <p>
        <span className="text-[var(--mm-text3)]">Last sync:</span>{" "}
        <span className="font-medium text-[var(--mm-text1)]">
          {formatWhen(s.tv_last_scheduled_scan_enqueued_at)}
        </span>
      </p>
    </div>
  );

  const radarrBody = (
    <div className="space-y-1.5">
      <p>
        <span className="text-[var(--mm-text3)]">Status:</span>{" "}
        <span className="font-medium text-[var(--mm-text1)]">
          {radConnected ? "Credentials saved" : "Not configured"}
        </span>
      </p>
      <p>
        <span className="text-[var(--mm-text3)]">Movies tracked:</span>{" "}
        <span className="font-medium text-[var(--mm-text1)]">
          {st.movies_tracked} movies
        </span>
      </p>
      <p>
        <span className="text-[var(--mm-text3)]">Last sync:</span>{" "}
        <span className="font-medium text-[var(--mm-text1)]">
          {formatWhen(s.movies_last_scheduled_scan_enqueued_at)}
        </span>
      </p>
    </div>
  );

  const last30Body = (
    <div>
      <MmStatTileRow>
        <MmStatTile label="Downloaded" value={st.subtitles_downloaded} />
        <MmStatTile label="Searches" value={st.searches_last_30_days} />
        <MmStatTile label="Not found" value={st.not_found_last_30_days} />
      </MmStatTileRow>
      <MmStatCaption>
        {st.upgrades_last_30_days === 1
          ? "1 upgrade"
          : `${st.upgrades_last_30_days} upgrades`}{" "}
        downloaded · last 30 days
      </MmStatCaption>
    </div>
  );

  return (
    <div
      data-testid="subber-overview-tab"
      className="mm-bubble-stack w-full min-w-0"
    >
      <MmOverviewSection
        headingId="subber-overview-at-a-glance-heading"
        heading="At a glance"
        data-testid="subber-overview-at-a-glance"
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
          <MmAtGlanceCard
            glanceOrder="2"
            title="Sonarr"
            body={sonarrBody}
            gridClassName="lg:col-span-4"
            footer={
              onOpenTab ? (
                <MmNextStepsButton
                  label="Settings"
                  onClick={() => onOpenTab("settings")}
                />
              ) : undefined
            }
          />
          <MmAtGlanceCard
            glanceOrder="3"
            title="Radarr"
            body={radarrBody}
            gridClassName="lg:col-span-4"
            footer={
              onOpenTab ? (
                <MmNextStepsButton
                  label="Settings"
                  onClick={() => onOpenTab("settings")}
                />
              ) : undefined
            }
          />
          <MmAtGlanceCard
            glanceOrder="4"
            title="Providers"
            body={providersGlanceBody}
            gridClassName="sm:col-span-2 lg:col-span-12"
            footer={
              onOpenTab ? (
                <MmNextStepsButton
                  label="Open Settings"
                  onClick={() => onOpenTab("settings")}
                />
              ) : undefined
            }
          />
        </MmAtGlanceGrid>
      </MmOverviewSection>

      <MmOverviewSection
        headingId="subber-overview-needs-attention-heading"
        heading="Needs attention"
        data-testid="subber-overview-needs-attention"
        data-overview-order="2"
      >
        <MmNeedsAttentionList
          items={attentionItems.map((row) => row.text)}
          actions={
            onOpenTab && attentionItems.length > 0 ? (
              <MmNextStepsButton
                label="Open Settings"
                onClick={() => onOpenTab("settings")}
              />
            ) : undefined
          }
        />
      </MmOverviewSection>

      <SubberOverviewNextSteps onOpenTab={onOpenTab} />
    </div>
  );
}
