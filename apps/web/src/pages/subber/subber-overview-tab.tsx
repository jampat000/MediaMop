import type { ReactNode } from "react";
import { PageLoading } from "../../components/shared/page-loading";
import { isHttpErrorFromApi, isLikelyNetworkFailure } from "../../lib/api/error-guards";
import {
  useSubberOverviewQuery,
  useSubberProvidersQuery,
  useSubberSettingsQuery,
} from "../../lib/subber/subber-queries";
import { fetcherMenuButtonClass } from "../fetcher/fetcher-menu-button";

function formatWhen(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.valueOf())) return "—";
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(d);
}

function AtGlanceCard({ title, body, glanceOrder }: { title: string; body: ReactNode; glanceOrder: "1" | "2" | "3" | "4" }) {
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

function StatTile({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-md border border-[var(--mm-border)] bg-black/15 px-3 py-3 text-center sm:px-4">
      <p className="text-[0.65rem] font-semibold uppercase tracking-wide text-[var(--mm-text3)]">{label}</p>
      <p className="mt-1 text-2xl font-bold tabular-nums text-[var(--mm-text1)]">{value}</p>
    </div>
  );
}

type AttentionTarget = "settings" | "tv" | "movies";

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

  const sonConnected = Boolean(s.sonarr_base_url?.trim()) && Boolean(s.sonarr_api_key_set);
  if (!sonConnected) {
    items.push({
      text: "Connect Sonarr in Settings to track your TV library.",
      target: "settings",
    });
  }
  const radConnected = Boolean(s.radarr_base_url?.trim()) && Boolean(s.radarr_api_key_set);
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

const ATTENTION_ACTION_ORDER: AttentionTarget[] = ["settings", "tv", "movies"];

function attentionActionLabel(t: AttentionTarget): string {
  if (t === "settings") return "Open Settings";
  if (t === "tv") return "Open TV";
  return "Open Movies";
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
      {err instanceof Error ? <p className="mm-page__lead font-mono text-sm text-[var(--mm-text3)]">{err.message}</p> : null}
    </div>
  );
}

export function SubberOverviewTab({
  onOpenTab,
}: {
  onOpenTab?: (tab: "tv" | "movies" | "settings") => void;
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

  const osConnected = Boolean(s.opensubtitles_password_set && s.opensubtitles_api_key_set);
  const sonConnected = Boolean(s.sonarr_base_url?.trim() && s.sonarr_api_key_set);
  const radConnected = Boolean(s.radarr_base_url?.trim() && s.radarr_api_key_set);
  const enabledProviders = plist.filter((p) => p.enabled).length;
  const providerTotal = plist.length;

  const attentionItems = buildSubberNeedsAttention({ settings: s, providers: plist, stats: st });
  const emptyAttention = attentionItems.length === 0;
  const actionTargets = ATTENTION_ACTION_ORDER.filter((t) => attentionItems.some((row) => row.target === t));

  const openSubtitlesBody = (
    <div className="space-y-1.5">
      <p>
        <span className="text-[var(--mm-text3)]">Status:</span>{" "}
        <span className="font-medium text-[var(--mm-text1)]">{osConnected ? "Connected" : "Not connected"}</span>
      </p>
      <p>
        <span className="text-[var(--mm-text3)]">Last checked:</span>{" "}
        <span className="font-medium text-[var(--mm-text1)]">—</span>
      </p>
    </div>
  );

  const sonarrBody = (
    <div className="space-y-1.5">
      <p>
        <span className="text-[var(--mm-text3)]">Status:</span>{" "}
        <span className="font-medium text-[var(--mm-text1)]">{sonConnected ? "Connected" : "Not connected"}</span>
      </p>
      <p>
        <span className="text-[var(--mm-text3)]">TV tracked:</span>{" "}
        <span className="font-medium text-[var(--mm-text1)]">{st.tv_tracked} episodes</span>
      </p>
      <p>
        <span className="text-[var(--mm-text3)]">Last sync:</span>{" "}
        <span className="font-medium text-[var(--mm-text1)]">{formatWhen(s.tv_last_scheduled_scan_enqueued_at)}</span>
      </p>
    </div>
  );

  const radarrBody = (
    <div className="space-y-1.5">
      <p>
        <span className="text-[var(--mm-text3)]">Status:</span>{" "}
        <span className="font-medium text-[var(--mm-text1)]">{radConnected ? "Connected" : "Not connected"}</span>
      </p>
      <p>
        <span className="text-[var(--mm-text3)]">Movies tracked:</span>{" "}
        <span className="font-medium text-[var(--mm-text1)]">{st.movies_tracked} movies</span>
      </p>
      <p>
        <span className="text-[var(--mm-text3)]">Last sync:</span>{" "}
        <span className="font-medium text-[var(--mm-text1)]">{formatWhen(s.movies_last_scheduled_scan_enqueued_at)}</span>
      </p>
    </div>
  );

  const providersBody = (
    <div className="space-y-1.5">
      <p>
        <span className="text-[var(--mm-text3)]">Enabled:</span>{" "}
        <span className="font-medium text-[var(--mm-text1)]">
          {enabledProviders} of {providerTotal}
        </span>
      </p>
    </div>
  );

  return (
    <div data-testid="subber-overview-tab" className="space-y-6 sm:space-y-7">
      <section
        className="mm-card mm-dash-card mm-fetcher-module-surface"
        aria-labelledby="subber-overview-at-a-glance-heading"
        data-testid="subber-overview-at-a-glance"
      >
        <h2 id="subber-overview-at-a-glance-heading" className="mm-card__title text-lg">
          At a glance
        </h2>
        <div className="mm-card__body mt-5 grid gap-4 sm:grid-cols-2 sm:gap-x-5 sm:gap-y-5 xl:grid-cols-4 xl:gap-x-5 xl:gap-y-5">
          <AtGlanceCard glanceOrder="1" title="OpenSubtitles" body={openSubtitlesBody} />
          <AtGlanceCard glanceOrder="2" title="Sonarr" body={sonarrBody} />
          <AtGlanceCard glanceOrder="3" title="Radarr" body={radarrBody} />
          <AtGlanceCard glanceOrder="4" title="Providers" body={providersBody} />
        </div>
      </section>

      <section
        className="mm-card mm-dash-card mm-fetcher-module-surface"
        aria-labelledby="subber-overview-needs-attention-heading"
        data-testid="subber-overview-needs-attention"
      >
        <h2 id="subber-overview-needs-attention-heading" className="mm-card__title text-lg">
          Needs attention
        </h2>
        <div className="mm-card__body mt-5 text-sm text-[var(--mm-text2)]">
          {emptyAttention ? (
            <p className="text-[var(--mm-text1)]">Everything looks good.</p>
          ) : (
            <>
              <ul className="list-none space-y-3 border-l-2 border-[var(--mm-border)] pl-3.5">
                {attentionItems.map((row, i) => (
                  <li key={`${row.text}-${i}`} className="leading-snug text-[var(--mm-text1)]">
                    {row.text}
                  </li>
                ))}
              </ul>
              {onOpenTab && actionTargets.length > 0 ? (
                <div className="mt-5 flex flex-wrap gap-2.5 border-t border-[var(--mm-border)] pt-4">
                  {actionTargets.map((target) => (
                    <button
                      key={target}
                      type="button"
                      className={fetcherMenuButtonClass({ variant: "secondary" })}
                      onClick={() => onOpenTab(target)}
                    >
                      {attentionActionLabel(target)}
                    </button>
                  ))}
                </div>
              ) : null}
            </>
          )}
        </div>
      </section>

      <section
        className="mm-card mm-dash-card mm-fetcher-module-surface"
        aria-labelledby="subber-overview-last-30-heading"
        data-testid="subber-overview-last-30"
      >
        <h2 id="subber-overview-last-30-heading" className="mm-card__title text-lg">
          Last 30 days
        </h2>
        <div className="mm-card__body mt-5 space-y-5">
          <div className="grid grid-cols-2 gap-3 sm:gap-4">
            <StatTile label="Subtitles downloaded" value={st.subtitles_downloaded} />
            <StatTile label="Searches run" value={st.searches_last_30_days} />
            <StatTile label="Not found" value={st.not_found_last_30_days} />
            <StatTile label="Upgrades" value={st.upgrades_last_30_days} />
          </div>
          <div className="space-y-1 text-sm text-[var(--mm-text2)]">
            <p>
              <span className="font-medium text-[var(--mm-text1)]">TV:</span> {st.tv_tracked} tracked · {st.tv_found}{" "}
              found · {st.tv_missing} missing
            </p>
            <p>
              <span className="font-medium text-[var(--mm-text1)]">Movies:</span> {st.movies_tracked} tracked ·{" "}
              {st.movies_found} found · {st.movies_missing} missing
            </p>
          </div>
        </div>
      </section>
    </div>
  );
}
