import type { ReactNode } from "react";
import {
  MmAtGlanceCard,
  MmAtGlanceGrid,
  MmNeedsAttentionList,
  MmOverviewSection,
  MmStatCaption,
  MmStatTile,
  MmStatTileRow,
} from "../../components/overview/mm-overview-cards";
import { PageLoading } from "../../components/shared/page-loading";
import { isHttpErrorFromApi, isLikelyNetworkFailure } from "../../lib/api/error-guards";
import { useRefinerJobsInspectionQuery } from "../../lib/refiner/jobs-inspection/queries";
import {
  useRefinerOperatorSettingsQuery,
  useRefinerPathSettingsQuery,
  useRefinerOverviewStatsQuery,
  useRefinerRemuxRulesSettingsQuery,
} from "../../lib/refiner/queries";
import { refinerStreamLanguageLabel } from "../../lib/refiner/stream-language-options";
import type { RefinerRemuxRulesScopeSettings } from "../../lib/refiner/types";
import { mmActionButtonClass } from "../../lib/ui/mm-control-roles";

export type RefinerOverviewOpenTab = "libraries" | "audio-subtitles" | "jobs" | "schedules";

function remuxDefaultsGlanceBody(rem: RefinerRemuxRulesScopeSettings): ReactNode {
  const pri = refinerStreamLanguageLabel(rem.primary_audio_lang);
  const sec = (rem.secondary_audio_lang ?? "").trim()
    ? refinerStreamLanguageLabel(rem.secondary_audio_lang)
    : null;
  const ter = (rem.tertiary_audio_lang ?? "").trim()
    ? refinerStreamLanguageLabel(rem.tertiary_audio_lang)
    : null;
  const langBits = [pri, sec, ter].filter((x) => x && x !== "—") as string[];
  const langLine = langBits.length ? langBits.join(" · ") : "—";

  const pol =
    rem.audio_preference_mode === "preferred_langs_strict"
      ? "Strict preferred languages"
      : rem.audio_preference_mode === "quality_all_languages"
        ? "Best quality (all languages)"
        : "Preferred languages, then quality";

  const sub =
    rem.subtitle_mode === "remove_all"
      ? "Remove all subtitles"
      : `Keep selected (${(rem.subtitle_langs_csv ?? "").trim() || "—"})`;

  return (
    <div className="space-y-1.5 lg:space-y-2">
      <p>
        <span className="text-[var(--mm-text3)]">Audio languages:</span>{" "}
        <span className="font-medium text-[var(--mm-text1)]">{langLine}</span>
      </p>
      <p>
        <span className="text-[var(--mm-text3)]">Selection:</span>{" "}
        <span className="font-medium text-[var(--mm-text1)]">{pol}</span>
      </p>
      <p>
        <span className="text-[var(--mm-text3)]">Subtitles:</span>{" "}
        <span className="font-medium text-[var(--mm-text1)]">{sub}</span>
      </p>
    </div>
  );
}

function buildNeedsAttention(args: { failedCount: number; watchedSet: boolean }): { text: string; target?: RefinerOverviewOpenTab }[] {
  const items: { text: string; target?: RefinerOverviewOpenTab }[] = [];
  if (args.failedCount > 0) {
    items.push({
      text:
        args.failedCount === 1
          ? "One job is in the failed list — open Jobs to review."
          : `${args.failedCount} jobs are in the failed list — open Jobs to review.`,
      target: "jobs",
    });
  }
  if (!args.watchedSet) {
    items.push({
      text: "No watched folder yet — add a watched folder under Libraries (TV, Movies, or both) before scans or passes can run.",
      target: "libraries",
    });
  }
  return items.slice(0, 4);
}

function tabActionLabel(id: RefinerOverviewOpenTab): string {
  switch (id) {
    case "libraries":
      return "Open Libraries";
    case "audio-subtitles":
      return "Open Audio & subtitles";
    case "jobs":
      return "Open Jobs";
    case "schedules":
      return "Open Schedules";
    default: {
      const _e: never = id;
      return _e;
    }
  }
}

const NEEDS_ATTENTION_ORDER: RefinerOverviewOpenTab[] = ["libraries", "audio-subtitles", "schedules", "jobs"];

function RefinerOverviewNeedsAttention({
  items,
  onOpenTab,
}: {
  items: { text: string; target?: RefinerOverviewOpenTab }[];
  onOpenTab?: (t: RefinerOverviewOpenTab) => void;
}) {
  const actionTargets = NEEDS_ATTENTION_ORDER.filter((t) => items.some((row) => row.target === t));

  return (
    <MmOverviewSection
      headingId="refiner-overview-needs-attention-heading"
      heading="Needs attention"
      data-testid="refiner-overview-needs-attention"
    >
      <MmNeedsAttentionList
        items={items.map((row) => row.text)}
        emptyMessage="Nothing stands out right now."
        actions={
          onOpenTab && actionTargets.length > 0 ? (
            <>
              {actionTargets.map((target) => (
                <button
                  key={target}
                  type="button"
                  className={mmActionButtonClass({ variant: "secondary" })}
                  onClick={() => onOpenTab(target)}
                >
                  {tabActionLabel(target)}
                </button>
              ))}
            </>
          ) : undefined
        }
      />
    </MmOverviewSection>
  );
}

function RefinerOverviewLoadError({ err }: { err: unknown }) {
  return (
    <div className="mm-page__intro" data-testid="refiner-overview-load-error">
      <p className="mm-page__lead">
        {isLikelyNetworkFailure(err)
          ? "Could not reach the MediaMop API. Check that the backend is running."
          : isHttpErrorFromApi(err)
            ? "The server refused this request. Sign in again or check API logs."
            : "Could not load part of the Refiner overview."}
      </p>
    </div>
  );
}

/** Refiner module Overview — summary, attention, and tab switches only (no settings forms). */
export function RefinerOverviewTab({
  onOpenTab,
}: {
  onOpenTab?: (t: RefinerOverviewOpenTab) => void;
} = {}) {
  const pathSettings = useRefinerPathSettingsQuery();
  const operatorSettings = useRefinerOperatorSettingsQuery();
  const remuxRules = useRefinerRemuxRulesSettingsQuery();
  const overviewStats = useRefinerOverviewStatsQuery();
  const pending = useRefinerJobsInspectionQuery("pending");
  const leased = useRefinerJobsInspectionQuery("leased");
  const failed = useRefinerJobsInspectionQuery("failed");

  const blocking = pathSettings.isError ? pathSettings.error : operatorSettings.isError ? operatorSettings.error : null;

  if (blocking) {
    return <RefinerOverviewLoadError err={blocking} />;
  }

  if (pathSettings.isPending || operatorSettings.isPending) {
    return <PageLoading label="Loading Refiner overview" />;
  }

  if (!pathSettings.data || !operatorSettings.data) {
    return <PageLoading label="Loading Refiner overview" />;
  }

  const watchedSet =
    Boolean((pathSettings.data.refiner_watched_folder ?? "").trim()) ||
    Boolean((pathSettings.data.refiner_tv_watched_folder ?? "").trim());
  const outputSet = Boolean((pathSettings.data.refiner_output_folder ?? "").trim());
  const tvWatchedSet = Boolean((pathSettings.data.refiner_tv_watched_folder ?? "").trim());
  const tvOutputSet = Boolean((pathSettings.data.refiner_tv_output_folder ?? "").trim());

  const pendingN = pending.data?.jobs.length ?? 0;
  const leasedN = leased.data?.jobs.length ?? 0;
  const failedN = failed.data?.jobs.length ?? 0;
  const failedReady = !failed.isPending && !failed.isError;

  const workerBody = (
      <div className="space-y-3 lg:space-y-3.5">
        <p className="font-medium text-[var(--mm-text1)]">
          Up to {operatorSettings.data.max_concurrent_files} file
          {operatorSettings.data.max_concurrent_files === 1 ? "" : "s"} at once
        </p>
        <div className="space-y-2 text-xs leading-relaxed text-[var(--mm-text3)] lg:space-y-2.5 lg:text-sm">
        <p>
          <span className="font-medium text-[var(--mm-text2)]">Folder checks:</span> TV every{" "}
          {pathSettings.data.tv_watched_folder_check_interval_seconds}s · Movies every{" "}
          {pathSettings.data.movie_watched_folder_check_interval_seconds}s (under Libraries). Files must sit unchanged at
          least {operatorSettings.data.min_file_age_seconds}s before watched-folder scans enqueue them. The same minimum also applies when TV season cleanup checks episodes Refiner never finished and Sonarr is not tracking in its queue.
        </p>
      </div>
    </div>
  );

  const foldersBody = (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 sm:gap-x-6">
      <div className="min-w-0 space-y-2">
        <p className="text-[0.65rem] font-semibold uppercase tracking-wide text-[var(--mm-text3)]">TV</p>
        <p>
          <span className="text-[var(--mm-text3)]">Watched · </span>
          <span className="font-medium text-[var(--mm-text1)]">{tvWatchedSet ? "Set" : "Not set"}</span>
        </p>
        <p>
          <span className="text-[var(--mm-text3)]">Output · </span>
          <span className="font-medium text-[var(--mm-text1)]">{tvOutputSet ? "Set" : "Not set"}</span>
        </p>
      </div>
      <div className="min-w-0 space-y-2">
        <p className="text-[0.65rem] font-semibold uppercase tracking-wide text-[var(--mm-text3)]">Movies</p>
        <p>
          <span className="text-[var(--mm-text3)]">Watched · </span>
          <span className="font-medium text-[var(--mm-text1)]">
            {(pathSettings.data.refiner_watched_folder ?? "").trim() ? "Set" : "Not set"}
          </span>
        </p>
        <p>
          <span className="text-[var(--mm-text3)]">Output · </span>
          <span className="font-medium text-[var(--mm-text1)]">{outputSet ? "Set" : "Not set"}</span>
        </p>
      </div>
    </div>
  );

  const queueBody = (
    <div className="space-y-1.5">
      <p>
        <span className="text-[var(--mm-text3)]">Waiting:</span>{" "}
        <span className="font-medium text-[var(--mm-text1)]">{pendingN === 0 ? "None" : `${pendingN} job(s)`}</span>
      </p>
      <p>
        <span className="text-[var(--mm-text3)]">Running:</span>{" "}
        <span className="font-medium text-[var(--mm-text1)]">{leasedN === 0 ? "None" : `${leasedN} job(s)`}</span>
      </p>
      <p>
        <span className="text-[var(--mm-text3)]">Failed list:</span>{" "}
        <span className="font-medium text-[var(--mm-text1)]">
          {failed.isPending
            ? "…"
            : failed.isError
              ? "Can't load right now"
              : failedN === 0
                ? "Empty"
                : `${failedN} in list (up to 50 shown in Jobs)`}
        </span>
      </p>
    </div>
  );


  const remuxBody =
    remuxRules.isPending ? (
      <p className="text-[var(--mm-text3)]">Loading…</p>
    ) : remuxRules.isError ? (
      <p className="text-[var(--mm-text3)]">Could not load defaults.</p>
    ) : remuxRules.data ? (
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 sm:gap-x-5 lg:gap-x-6 lg:gap-y-1">
        <div className="min-w-0 space-y-2 lg:space-y-2.5">
          <p className="text-[0.65rem] font-semibold uppercase tracking-wide text-[var(--mm-text3)] lg:text-xs">TV</p>
          {remuxDefaultsGlanceBody(remuxRules.data.tv)}
        </div>
        <div className="min-w-0 space-y-2 lg:space-y-2.5">
          <p className="text-[0.65rem] font-semibold uppercase tracking-wide text-[var(--mm-text3)] lg:text-xs">
            Movies
          </p>
          {remuxDefaultsGlanceBody(remuxRules.data.movie)}
        </div>
      </div>
    ) : (
      <p className="text-[var(--mm-text3)]">—</p>
    );
  const statsBody =
    overviewStats.isPending || overviewStats.isError || !overviewStats.data ? (
      <p className="text-[var(--mm-text3)]">Loading…</p>
    ) : (
      <div>
        <MmStatTileRow>
          <MmStatTile label="Completed jobs" value={overviewStats.data.files_processed} />
          <MmStatTile label="Failed jobs" value={overviewStats.data.files_failed} />
          <MmStatTile label="Success" value={`${overviewStats.data.success_rate_percent}%`} />
        </MmStatTileRow>
        <MmStatCaption>
          Counts completed and terminal-failed remux jobs in the overview window. Success rate = completed / (completed +
          failed).
        </MmStatCaption>
      </div>
    );

  const attentionItems = buildNeedsAttention({
    failedCount: failedReady ? failedN : 0,
    watchedSet,
  });

  return (
    <div data-testid="refiner-overview-panel" className="mm-bubble-stack w-full min-w-0">
      <MmOverviewSection
        headingId="refiner-overview-at-a-glance-heading"
        heading="At a glance"
        data-testid="refiner-overview-at-a-glance"
      >
        <MmAtGlanceGrid className="grid grid-cols-1 gap-4 sm:grid-cols-2 sm:gap-x-5 sm:gap-y-5 lg:grid-cols-12 lg:gap-x-5 lg:gap-y-6">
          <MmAtGlanceCard
            glanceOrder="1"
            title="Last 30 days"
            emphasis
            body={statsBody}
            data-testid="refiner-overview-last-30-days"
            gridClassName="lg:col-span-4"
          />
          <MmAtGlanceCard glanceOrder="2" title="Libraries" body={foldersBody} gridClassName="lg:col-span-4" />
          <MmAtGlanceCard glanceOrder="3" title="Job queue" body={queueBody} gridClassName="lg:col-span-4" />
          <MmAtGlanceCard
            glanceOrder="4"
            title="Throughput & safety"
            body={workerBody}
            gridClassName="sm:col-span-2 lg:col-span-6"
            size="large"
            footer={
              onOpenTab ? (
                <button type="button" className={mmActionButtonClass({ variant: "secondary" })} onClick={() => onOpenTab("schedules")}>
                  Open Schedules
                </button>
              ) : undefined
            }
          />
          <MmAtGlanceCard
            glanceOrder="5"
            title="Audio & subtitles"
            body={remuxBody}
            gridClassName="sm:col-span-2 lg:col-span-6"
            size="large"
            footer={
              onOpenTab ? (
                <button
                  type="button"
                  className={mmActionButtonClass({ variant: "secondary" })}
                  onClick={() => onOpenTab("audio-subtitles")}
                >
                  Open Audio & subtitles
                </button>
              ) : undefined
            }
            data-testid="refiner-overview-audio-subtitles-glance"
          />
        </MmAtGlanceGrid>
      </MmOverviewSection>

      <RefinerOverviewNeedsAttention items={attentionItems} onOpenTab={onOpenTab} />

      <MmOverviewSection
        headingId="refiner-overview-next-heading"
        heading="Next steps"
        data-testid="refiner-overview-go-deeper"
      >
        <div className="mm-bubble-stack">
          <p className="leading-relaxed">
            Finished work is summarized on Activity. Use Libraries for paths, folder timers, and minimum file age. Use Schedules for optional hour
            limits and to run library scans on demand. Use Audio & subtitles for defaults, and Jobs for the queue on this server.
          </p>
          {onOpenTab ? (
            <div className="flex flex-wrap gap-2.5 border-t border-[var(--mm-border)] pt-4">
              <button type="button" className={mmActionButtonClass({ variant: "secondary" })} onClick={() => onOpenTab("libraries")}>
                Libraries
              </button>
              <button
                type="button"
                className={mmActionButtonClass({ variant: "secondary" })}
                onClick={() => onOpenTab("audio-subtitles")}
              >
                Audio & subtitles
              </button>
              <button type="button" className={mmActionButtonClass({ variant: "secondary" })} onClick={() => onOpenTab("schedules")}>
                Schedules
              </button>
              <button type="button" className={mmActionButtonClass({ variant: "secondary" })} onClick={() => onOpenTab("jobs")}>
                Jobs
              </button>
            </div>
          ) : null}
        </div>
      </MmOverviewSection>
    </div>
  );
}
