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
import {
  isHttpErrorFromApi,
  isLikelyNetworkFailure,
} from "../../lib/api/error-guards";
import { useRefinerJobsInspectionQuery } from "../../lib/refiner/jobs-inspection/queries";
import {
  REFINER_MEDIA_TYPE_LABELS,
  type RefinerLibrary,
  type RefinerRuleSet,
} from "../../lib/refiner/libraries-api";
import {
  useRefinerLibrariesQuery,
  useRefinerRuleSetsQuery,
} from "../../lib/refiner/libraries-queries";
import {
  useRefinerOperatorSettingsQuery,
  useRefinerOverviewStatsQuery,
} from "../../lib/refiner/queries";
import { refinerStreamLanguageLabel } from "../../lib/refiner/stream-language-options";
import { mmActionButtonClass } from "../../lib/ui/mm-control-roles";

export type RefinerOverviewOpenTab =
  "libraries" | "audio-subtitles" | "jobs" | "schedules";

function ruleSetGlanceBody(rem: RefinerRuleSet): ReactNode {
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
      ? "Preferred languages only"
      : rem.audio_preference_mode === "quality_all_languages"
        ? "Best quality in any language"
        : "Preferred languages, then quality";

  const sub =
    rem.subtitle_mode === "remove_all"
      ? "Remove all subtitles"
      : rem.subtitle_mode === "keep_all"
        ? "Keep all subtitles"
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

function hasFolder(value: string | null | undefined): boolean {
  return Boolean((value ?? "").trim());
}

function scanIntervalLabel(seconds: number): string {
  if (seconds % 3600 === 0) {
    const hours = seconds / 3600;
    return hours === 1 ? "every hour" : `every ${hours} hours`;
  }
  if (seconds % 60 === 0) {
    const minutes = seconds / 60;
    return minutes === 1 ? "every minute" : `every ${minutes} minutes`;
  }
  return `every ${seconds} seconds`;
}

function buildNeedsAttention(args: {
  failedCount: number;
  libraries: RefinerLibrary[];
}): { text: string; target?: RefinerOverviewOpenTab }[] {
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
  if (args.libraries.length === 0) {
    items.push({
      text: "No Refiner libraries yet — add one under Libraries before scans or passes can run.",
      target: "libraries",
    });
  } else {
    const missing = args.libraries.filter(
      (library) => library.enabled && !hasFolder(library.watched_folder),
    );
    if (missing.length === 1) {
      items.push({
        text: `${missing[0].name} has no watched folder — add one under Libraries before it can be scanned.`,
        target: "libraries",
      });
    } else if (missing.length > 1) {
      items.push({
        text: `${missing.length} libraries have no watched folder (${missing
          .map((library) => library.name)
          .join(", ")}) — add them under Libraries before they can be scanned.`,
        target: "libraries",
      });
    }
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

const NEEDS_ATTENTION_ORDER: RefinerOverviewOpenTab[] = [
  "libraries",
  "audio-subtitles",
  "schedules",
  "jobs",
];

function RefinerOverviewNeedsAttention({
  items,
  onOpenTab,
}: {
  items: { text: string; target?: RefinerOverviewOpenTab }[];
  onOpenTab?: (t: RefinerOverviewOpenTab) => void;
}) {
  const actionTargets = NEEDS_ATTENTION_ORDER.filter((t) =>
    items.some((row) => row.target === t),
  );

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

function RefinerGuidedSetup({
  onOpenTab,
}: {
  onOpenTab?: (tab: RefinerOverviewOpenTab) => void;
}) {
  return (
    <MmOverviewSection
      headingId="refiner-guided-setup-heading"
      heading="Set up Refiner"
      data-testid="refiner-guided-setup"
    >
      <p className="max-w-2xl leading-relaxed">
        Refiner has no watched folder yet. Complete this checklist before
        expecting processing activity; the history figures above remain
        historical only.
      </p>
      <ol className="mt-4 grid gap-2 text-sm text-[var(--mm-text2)] sm:grid-cols-3">
        <li className="mm-setup-step">
          <span>1</span>
          <strong>Choose a library</strong>
          <small>Pick TV, Movies, or both.</small>
        </li>
        <li className="mm-setup-step">
          <span>2</span>
          <strong>Set a watched folder</strong>
          <small>Use a local, Docker, or UNC path.</small>
        </li>
        <li className="mm-setup-step">
          <span>3</span>
          <strong>Review the first scan</strong>
          <small>Start with the safety defaults.</small>
        </li>
      </ol>
      {onOpenTab ? (
        <div className="mt-4 border-t border-[var(--mm-border)] pt-4">
          <button
            type="button"
            className={mmActionButtonClass({ variant: "secondary" })}
            onClick={() => onOpenTab("libraries")}
          >
            Configure libraries
          </button>
        </div>
      ) : null}
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
  const librariesQuery = useRefinerLibrariesQuery();
  const operatorSettings = useRefinerOperatorSettingsQuery();
  const ruleSets = useRefinerRuleSetsQuery();
  const overviewStats = useRefinerOverviewStatsQuery();
  const pending = useRefinerJobsInspectionQuery("pending");
  const leased = useRefinerJobsInspectionQuery("leased");
  const failed = useRefinerJobsInspectionQuery("failed");

  const blocking = librariesQuery.isError
    ? librariesQuery.error
    : operatorSettings.isError
      ? operatorSettings.error
      : null;

  if (blocking) {
    return <RefinerOverviewLoadError err={blocking} />;
  }

  if (librariesQuery.isPending || operatorSettings.isPending) {
    return <PageLoading label="Loading Refiner overview" />;
  }

  if (!librariesQuery.data || !operatorSettings.data) {
    return <PageLoading label="Loading Refiner overview" />;
  }

  const libraries = [...librariesQuery.data].sort(
    (x, y) => x.display_order - y.display_order,
  );
  const watchedSet = libraries.some((library) =>
    hasFolder(library.watched_folder),
  );

  const pendingN = pending.data?.jobs.length ?? 0;
  const leasedN = leased.data?.jobs.length ?? 0;
  const failedN = failed.data?.jobs.length ?? 0;
  const failedReady = !failed.isPending && !failed.isError;

  const workerBody = (
    <div className="space-y-2.5">
      <p className="font-medium text-[var(--mm-text1)]">
        Up to {operatorSettings.data.max_concurrent_files} file
        {operatorSettings.data.max_concurrent_files === 1 ? "" : "s"} at once
      </p>
      <dl className="grid gap-2 text-sm text-[var(--mm-text3)] sm:grid-cols-2">
        <div>
          <dt>Minimum unchanged age</dt>
          <dd className="font-medium text-[var(--mm-text1)]">
            {operatorSettings.data.min_file_age_seconds} seconds
          </dd>
        </div>
      </dl>
    </div>
  );

  const foldersBody =
    libraries.length === 0 ? (
      <p className="text-[var(--mm-text3)]">No libraries yet.</p>
    ) : (
      <ul
        className="grid grid-cols-1 gap-4 sm:grid-cols-2 sm:gap-x-6"
        data-testid="refiner-overview-libraries"
      >
        {libraries.map((library) => (
          <li
            key={library.id}
            className="min-w-0 space-y-2"
            data-testid="refiner-overview-library"
          >
            <p className="text-[0.65rem] font-semibold uppercase tracking-wide text-[var(--mm-text3)]">
              {library.name} · {REFINER_MEDIA_TYPE_LABELS[library.media_type]}
              {library.enabled ? "" : " · Off"}
            </p>
            <p>
              <span className="text-[var(--mm-text3)]">Watched · </span>
              <span className="font-medium text-[var(--mm-text1)]">
                {hasFolder(library.watched_folder) ? "Set" : "Not set"}
              </span>
            </p>
            <p>
              <span className="text-[var(--mm-text3)]">Output · </span>
              <span className="font-medium text-[var(--mm-text1)]">
                {hasFolder(library.output_folder) ? "Set" : "Not set"}
              </span>
            </p>
            <p>
              <span className="text-[var(--mm-text3)]">Checked · </span>
              <span className="font-medium text-[var(--mm-text1)]">
                {scanIntervalLabel(library.scan_interval_seconds)}
              </span>
            </p>
          </li>
        ))}
      </ul>
    );

  const queueBody = (
    <div className="space-y-1.5">
      <p>
        <span className="text-[var(--mm-text3)]">Waiting:</span>{" "}
        <span className="font-medium text-[var(--mm-text1)]">
          {pendingN === 0 ? "None" : `${pendingN} job(s)`}
        </span>
      </p>
      <p>
        <span className="text-[var(--mm-text3)]">Running:</span>{" "}
        <span className="font-medium text-[var(--mm-text1)]">
          {leasedN === 0 ? "None" : `${leasedN} job(s)`}
        </span>
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

  const ruleSetById = new Map(
    (ruleSets.data ?? []).map((ruleSet) => [ruleSet.id, ruleSet]),
  );
  const remuxBody =
    libraries.length === 0 ? (
      <p className="text-[var(--mm-text3)]">No libraries yet.</p>
    ) : ruleSets.isPending ? (
      <p className="text-[var(--mm-text3)]">Loading…</p>
    ) : ruleSets.isError ? (
      <p className="text-[var(--mm-text3)]">Could not load rule sets.</p>
    ) : (
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 sm:gap-x-5 lg:gap-x-6 lg:gap-y-1">
        {libraries.map((library) => {
          const ruleSet =
            library.rule_set_id === null
              ? undefined
              : ruleSetById.get(library.rule_set_id);
          return (
            <div key={library.id} className="min-w-0 space-y-2 lg:space-y-2.5">
              <p className="text-[0.65rem] font-semibold uppercase tracking-wide text-[var(--mm-text3)] lg:text-xs">
                {library.name}
              </p>
              <p>
                <span className="text-[var(--mm-text3)]">Rule set:</span>{" "}
                <span className="font-medium text-[var(--mm-text1)]">
                  {ruleSet
                    ? ruleSet.name
                    : `${REFINER_MEDIA_TYPE_LABELS[library.media_type]} defaults`}
                </span>
              </p>
              {ruleSet ? ruleSetGlanceBody(ruleSet) : null}
            </div>
          );
        })}
      </div>
    );
  const statsBody =
    overviewStats.isPending || overviewStats.isError || !overviewStats.data ? (
      <p className="text-[var(--mm-text3)]">Loading…</p>
    ) : (
      <div>
        <MmStatTileRow>
          <MmStatTile
            label="Completed jobs"
            value={overviewStats.data.files_processed}
          />
          <MmStatTile
            label="Failed jobs"
            value={overviewStats.data.files_failed}
          />
          <MmStatTile
            label="Success"
            value={`${overviewStats.data.success_rate_percent}%`}
          />
        </MmStatTileRow>
        <MmStatCaption>
          Completed and terminal-failed remux jobs during this period.
        </MmStatCaption>
      </div>
    );

  const attentionItems = buildNeedsAttention({
    failedCount: failedReady ? failedN : 0,
    libraries,
  });

  return (
    <div
      data-testid="refiner-overview-panel"
      className="mm-bubble-stack w-full min-w-0"
    >
      <MmOverviewSection
        headingId="refiner-overview-at-a-glance-heading"
        heading="At a glance"
        data-testid="refiner-overview-at-a-glance"
      >
        <MmAtGlanceGrid className="grid grid-cols-1 gap-4 sm:grid-cols-2 sm:gap-x-5 sm:gap-y-5 lg:grid-cols-12 lg:gap-x-5 lg:gap-y-6">
          <MmAtGlanceCard
            glanceOrder="1"
            title="30-day results"
            emphasis
            body={statsBody}
            data-testid="refiner-overview-last-30-days"
            gridClassName="sm:col-span-2 lg:col-span-12"
          />
          <MmAtGlanceCard
            glanceOrder="2"
            title="Libraries"
            body={foldersBody}
            gridClassName="lg:col-span-6"
          />
          <MmAtGlanceCard
            glanceOrder="3"
            title="Job queue"
            body={queueBody}
            gridClassName="lg:col-span-6"
          />
          <MmAtGlanceCard
            glanceOrder="4"
            title="Throughput & safety"
            body={workerBody}
            gridClassName="sm:col-span-2 lg:col-span-6"
            size="large"
            footer={
              onOpenTab ? (
                <button
                  type="button"
                  className={mmActionButtonClass({ variant: "secondary" })}
                  onClick={() => onOpenTab("schedules")}
                >
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

      {!watchedSet ? <RefinerGuidedSetup onOpenTab={onOpenTab} /> : null}

      <RefinerOverviewNeedsAttention
        items={attentionItems}
        onOpenTab={onOpenTab}
      />

      <MmOverviewSection
        headingId="refiner-overview-next-heading"
        heading="Next steps"
        data-testid="refiner-overview-go-deeper"
      >
        <div className="mm-bubble-stack">
          <p className="leading-relaxed">
            Finished work is summarized on Activity. Use Libraries for paths,
            folder timers, and minimum file age. Use Schedules for optional hour
            limits and to run library scans on demand. Use Audio & subtitles for
            defaults, and Jobs for the queue on this server.
          </p>
          {onOpenTab ? (
            <div className="flex flex-wrap gap-2.5 border-t border-[var(--mm-border)] pt-4">
              <button
                type="button"
                className={mmActionButtonClass({ variant: "secondary" })}
                onClick={() => onOpenTab("libraries")}
              >
                Libraries
              </button>
              <button
                type="button"
                className={mmActionButtonClass({ variant: "secondary" })}
                onClick={() => onOpenTab("audio-subtitles")}
              >
                Audio & subtitles
              </button>
              <button
                type="button"
                className={mmActionButtonClass({ variant: "secondary" })}
                onClick={() => onOpenTab("schedules")}
              >
                Schedules
              </button>
              <button
                type="button"
                className={mmActionButtonClass({ variant: "secondary" })}
                onClick={() => onOpenTab("jobs")}
              >
                Jobs
              </button>
            </div>
          ) : null}
        </div>
      </MmOverviewSection>
    </div>
  );
}
