import type { CSSProperties } from "react";
import { MmOverviewSection } from "../../components/overview/mm-overview-cards";
import { PageLoading } from "../../components/shared/page-loading";
import { QuietSection } from "../../components/shared/quiet-section";
import {
  isHttpErrorFromApi,
  isLikelyNetworkFailure,
} from "../../lib/api/error-guards";
import {
  PROCESSING_FILE_STATUS_LABELS,
  type ProcessingFileStatus,
} from "../../lib/processing/files-api";
import { useProcessingFilesQuery } from "../../lib/processing/files-queries";
import { useProcessingJobsInspectionQuery } from "../../lib/processing/jobs-inspection/queries";
import {
  PROCESSING_MEDIA_TYPE_LABELS,
  processingMediaTypeBadge,
  type ProcessingLibrary,
  type ProcessingRuleSet,
} from "../../lib/processing/libraries-api";
import { formatBytes } from "../../lib/processing/library-api";
import {
  useProcessingLibrariesQuery,
  useProcessingRuleSetsQuery,
} from "../../lib/processing/libraries-queries";
import {
  useProcessingOperatorSettingsQuery,
  useProcessingOverviewStatsQuery,
} from "../../lib/processing/queries";
import { processingStreamLanguageLabel } from "../../lib/processing/stream-language-options";
import { mmActionButtonClass } from "../../lib/ui/mm-control-roles";

export type ProcessingOverviewOpenTab =
  "libraries" | "audio-subtitles" | "jobs" | "schedules" | "files";

type AttentionItem = { text: string; target: ProcessingOverviewOpenTab };

/** The pipeline, left to right, as the lead band draws it. Each stage is one real
 *  file status, so clicking it can open Files filtered to exactly that status. */
const FLOW_STAGES: {
  status: ProcessingFileStatus;
  hint: string;
  live?: boolean;
}[] = [
  { status: "unprocessed", hint: "Found in a watched folder" },
  { status: "on_hold", hint: "Held until it can run" },
  { status: "processing", hint: "Being rewritten now", live: true },
  { status: "processed", hint: "Handed back clean" },
  { status: "skipped", hint: "Nothing to change" },
  { status: "processing_failed", hint: "Waiting for review" },
];

function ruleSetSummary(rem: ProcessingRuleSet): string {
  const languages = [
    rem.primary_audio_lang,
    rem.secondary_audio_lang,
    rem.tertiary_audio_lang,
  ]
    .filter((code) => (code ?? "").trim())
    .map((code) => processingStreamLanguageLabel(code))
    .filter((label) => label && label !== "—");

  const selection =
    rem.audio_preference_mode === "preferred_langs_strict"
      ? "preferred languages only"
      : rem.audio_preference_mode === "quality_all_languages"
        ? "best quality in any language"
        : "preferred languages, then quality";

  const subtitles =
    rem.subtitle_mode === "remove_all"
      ? "Remove all subtitles"
      : rem.subtitle_mode === "keep_all"
        ? "Keep all subtitles"
        : `Keep subtitles: ${(rem.subtitle_langs_csv ?? "").trim() || "—"}`;

  const audio = languages.length
    ? `${languages.join(" · ")} (${selection})`
    : `Audio: ${selection}`;
  return `${audio}. ${subtitles}.`;
}

function hasFolder(value: string | null | undefined): boolean {
  return Boolean((value ?? "").trim());
}

function scanIntervalLabel(seconds: number): string {
  if (seconds % 3600 === 0) {
    const hours = seconds / 3600;
    return hours === 1 ? "Every hour" : `Every ${hours} hours`;
  }
  if (seconds % 60 === 0) {
    const minutes = seconds / 60;
    return minutes === 1 ? "Every minute" : `Every ${minutes} minutes`;
  }
  return `Every ${seconds} seconds`;
}

function buildAttention(args: {
  failedCount: number;
  libraries: ProcessingLibrary[];
}): AttentionItem[] {
  const items: AttentionItem[] = [];
  if (args.failedCount > 0) {
    items.push({
      text:
        args.failedCount === 1
          ? "One job failed and is waiting for review."
          : `${args.failedCount} jobs failed and are waiting for review.`,
      target: "jobs",
    });
  }
  const missing = args.libraries.filter(
    (library) => library.enabled && !hasFolder(library.watched_folder),
  );
  if (missing.length === 1) {
    items.push({
      text: `${missing[0].name} has no watched folder, so it cannot be scanned yet.`,
      target: "libraries",
    });
  } else if (missing.length > 1) {
    items.push({
      text: `${missing.length} libraries have no watched folder (${missing
        .map((library) => library.name)
        .join(", ")}), so they cannot be scanned yet.`,
      target: "libraries",
    });
  }
  const noOutput = args.libraries.filter(
    (library) =>
      library.enabled &&
      hasFolder(library.watched_folder) &&
      !hasFolder(library.output_folder),
  );
  if (noOutput.length > 0) {
    items.push({
      text: `${noOutput.map((library) => library.name).join(", ")} ${
        noOutput.length === 1 ? "has" : "have"
      } a watched folder but no output folder.`,
      target: "libraries",
    });
  }
  return items;
}

function openLabel(target: ProcessingOverviewOpenTab): string {
  switch (target) {
    case "libraries":
      return "Open Libraries";
    case "audio-subtitles":
      return "Open Audio & subtitles";
    case "jobs":
      return "Open Jobs";
    case "schedules":
      return "Open Schedules";
    case "files":
      return "Open Files";
    default: {
      const unreachable: never = target;
      return unreachable;
    }
  }
}

function SetupChecklist({
  libraries,
  onOpenTab,
}: {
  libraries: ProcessingLibrary[];
  onOpenTab?: (tab: ProcessingOverviewOpenTab) => void;
}) {
  const steps: { title: string; hint: string; done: boolean }[] = [
    {
      title: "Add a library",
      hint: "One per kind of media, such as Movies or TV.",
      done: libraries.length > 0,
    },
    {
      title: "Set its watched folder",
      hint: "Where your downloader finishes files. Local, Docker or UNC paths all work.",
      done: libraries.some((library) => hasFolder(library.watched_folder)),
    },
    {
      title: "Set its output folder",
      hint: "Where cleaned files go for your media manager to import.",
      done: libraries.some(
        (library) =>
          hasFolder(library.watched_folder) && hasFolder(library.output_folder),
      ),
    },
  ];
  return (
    <MmOverviewSection
      headingId="processing-guided-setup-heading"
      heading="Get started"
      data-testid="processing-guided-setup"
    >
      <p className="mm-proc-panel__lead">
        Weir has no folder to watch yet. Three steps and it starts cleaning new
        downloads.
      </p>
      <ol className="mm-proc-steps">
        {steps.map((step, index) => (
          <li
            key={step.title}
            className={`mm-proc-step${step.done ? " mm-proc-step--done" : ""}`}
          >
            <span className="mm-proc-step__marker" aria-hidden="true">
              {step.done ? "✓" : index + 1}
            </span>
            <span className="mm-proc-step__text">
              <strong>
                {step.title}
                {step.done ? <span className="sr-only"> (done)</span> : null}
              </strong>
              <small>{step.hint}</small>
            </span>
          </li>
        ))}
      </ol>
      {onOpenTab ? (
        <div className="mm-proc-panel__actions">
          <button
            type="button"
            className={mmActionButtonClass({ variant: "primary" })}
            onClick={() => onOpenTab("libraries")}
          >
            Set up libraries
          </button>
        </div>
      ) : null}
    </MmOverviewSection>
  );
}

/** Something blocking, above the lead band: sentences, not a card. */
function AttentionList({
  items,
  onOpenTab,
}: {
  items: AttentionItem[];
  onOpenTab?: (tab: ProcessingOverviewOpenTab) => void;
}) {
  return (
    <ul
      className="mm-interrupt"
      data-testid="processing-overview-needs-attention"
    >
      {items.map((item) => (
        <li key={item.text} className="mm-interrupt__item">
          <span className="mm-interrupt__text">{item.text}</span>
          {onOpenTab ? (
            <button
              type="button"
              className="mm-quiet-link"
              onClick={() => onOpenTab(item.target)}
            >
              {openLabel(item.target)} →
            </button>
          ) : null}
        </li>
      ))}
    </ul>
  );
}

/** The lead: six pipeline stages. In a row each is as wide as the number of files in it;
 *  too narrow for that and the primitive restacks them into a labelled list by itself. */
function FlowBand({
  counts,
  onOpenFiles,
}: {
  counts: Record<string, number>;
  onOpenFiles?: (status: ProcessingFileStatus) => void;
}) {
  const stages = FLOW_STAGES.map((stage) => ({
    ...stage,
    label: PROCESSING_FILE_STATUS_LABELS[stage.status],
    count: counts[stage.status] ?? 0,
  }));
  const total = stages.reduce((sum, stage) => sum + stage.count, 0);
  return (
    <div className="mm-lead-band" data-testid="processing-overview-flow">
      {stages.map((stage) => {
        const live = Boolean(stage.live) && stage.count > 0;
        const modifier =
          stage.count === 0
            ? " mm-lead-band__segment--empty"
            : live
              ? " mm-lead-band__segment--live"
              : "";
        // Share of the band: the count itself, floored so an empty stage still
        // reads as a stage. Weights are unitless, so the band never over-fits.
        const share = total === 0 ? 1 : Math.max(stage.count, total * 0.06);
        return (
          <button
            key={stage.status}
            type="button"
            className={`mm-lead-band__segment${modifier}`}
            style={{ "--mm-flow-share": share } as CSSProperties}
            onClick={() => onOpenFiles?.(stage.status)}
            data-testid="processing-overview-flow-stage"
          >
            <span className="mm-lead-band__label">
              {stage.label}
              {live ? (
                <i className="mm-lead-band__pulse" aria-hidden="true" />
              ) : null}
            </span>
            <span className="mm-lead-band__value">
              {stage.count.toLocaleString()}
            </span>
            <span className="mm-lead-band__hint">{stage.hint}</span>
            <span className="mm-lead-band__go" aria-hidden="true">
              Filter →
            </span>
          </button>
        );
      })}
    </div>
  );
}

function ProcessingOverviewLoadError({ err }: { err: unknown }) {
  return (
    <div
      className="mm-page__intro"
      data-testid="processing-overview-load-error"
    >
      <p className="mm-page__lead">
        {isLikelyNetworkFailure(err)
          ? "Could not reach the Weir server. Check that it is running."
          : isHttpErrorFromApi(err)
            ? "The server refused this request. Sign in again or check the logs."
            : "Could not load part of the overview."}
      </p>
    </div>
  );
}

/** Processing Overview: the pipeline across the top, the month's one number, then
 *  every library, quietly. See docs/design/content-language.md. */
export function ProcessingOverviewTab({
  onOpenTab,
}: {
  onOpenTab?: (
    t: ProcessingOverviewOpenTab,
    status?: ProcessingFileStatus,
  ) => void;
} = {}) {
  const librariesQuery = useProcessingLibrariesQuery();
  const operatorSettings = useProcessingOperatorSettingsQuery();
  const ruleSets = useProcessingRuleSetsQuery();
  const overviewStats = useProcessingOverviewStatsQuery();
  const files = useProcessingFilesQuery({ limit: 1 });
  const failed = useProcessingJobsInspectionQuery("failed");

  const blocking = librariesQuery.isError
    ? librariesQuery.error
    : operatorSettings.isError
      ? operatorSettings.error
      : null;

  if (blocking) {
    return <ProcessingOverviewLoadError err={blocking} />;
  }

  if (!librariesQuery.data || !operatorSettings.data) {
    return <PageLoading label="Loading overview" />;
  }

  const settings = operatorSettings.data;
  const libraries = [...librariesQuery.data].sort(
    (x, y) => x.display_order - y.display_order,
  );
  const watchedSet = libraries.some((library) =>
    hasFolder(library.watched_folder),
  );
  const failedReady = !failed.isPending && !failed.isError;
  const failedN = failed.data?.jobs.length ?? 0;
  const attention = buildAttention({
    failedCount: failedReady ? failedN : 0,
    libraries,
  });

  const stats = overviewStats.data;
  const finished = stats ? stats.files_processed + stats.files_failed : 0;
  const counts = files.data?.status_counts ?? {};
  const inHand = Object.values(counts).reduce((sum, n) => sum + n, 0);
  const shownInBand = FLOW_STAGES.reduce(
    (sum, stage) => sum + (counts[stage.status] ?? 0),
    0,
  );
  const elsewhere = inHand - shownInBand;

  const ruleSetById = new Map(
    (ruleSets.data ?? []).map((ruleSet) => [ruleSet.id, ruleSet]),
  );

  const flowSummary = () => {
    if ((counts.processing_failed ?? 0) > 0) {
      return `${counts.processing_failed} ${counts.processing_failed === 1 ? "file needs" : "files need"} review.`;
    }
    if ((counts.processing ?? 0) > 0) {
      return `${counts.processing} being rewritten right now.`;
    }
    if ((counts.unprocessed ?? 0) > 0) {
      return `${counts.unprocessed} waiting for the next slot.`;
    }
    return "Nothing is stuck.";
  };

  return (
    <div
      data-testid="processing-overview-panel"
      className="mm-quiet-stack min-w-0"
    >
      {!watchedSet ? (
        <SetupChecklist libraries={libraries} onOpenTab={onOpenTab} />
      ) : (
        <div className="mm-lead">
          {attention.length > 0 ? (
            <AttentionList items={attention} onOpenTab={onOpenTab} />
          ) : null}

          {files.isPending || files.isError || inHand === 0 ? (
            <p
              className="mm-quiet-note"
              data-testid="processing-overview-flow-empty"
            >
              {files.isPending
                ? "Counting the files Weir has in hand…"
                : files.isError
                  ? "Could not count the files Weir has in hand. The Files tab still works."
                  : "Weir has no files in hand yet. Nothing has landed in a watched folder since the last scan."}
            </p>
          ) : (
            <FlowBand
              counts={counts}
              onOpenFiles={
                onOpenTab ? (status) => onOpenTab("files", status) : undefined
              }
            />
          )}

          <p
            className="mm-lead-caption"
            data-testid="processing-overview-flow-caption"
          >
            <span>
              Click a stage to open Files filtered to it. A file is picked up
              once it has not changed for {settings.min_file_age_seconds}{" "}
              seconds. Up to {settings.max_concurrent_files} at once.
            </span>
            <span>
              {flowSummary()}
              {elsewhere > 0
                ? ` ${elsewhere} more in states the band does not show.`
                : ""}
            </span>
          </p>

          <div
            className="mm-figure-row"
            data-testid="processing-overview-last-30-days"
          >
            <section className="mm-figure mm-figure--hero">
              <div className="mm-figure__eyebrow">
                <span>Processed</span>
                <span>Last 30 days</span>
              </div>
              <div className="mm-figure__value">
                {stats ? stats.files_processed.toLocaleString() : "…"}
                <span className="mm-figure__unit">files handed back</span>
              </div>
              {stats ? (
                <div className="mm-figure__foot">
                  <div>
                    <span className="mm-figure__foot-value">
                      {stats.output_written_count.toLocaleString()}
                    </span>
                    <span className="mm-figure__foot-label">Rewritten</span>
                  </div>
                  <div>
                    <span className="mm-figure__foot-value">
                      {stats.already_optimized_count.toLocaleString()}
                    </span>
                    <span className="mm-figure__foot-label">Already right</span>
                  </div>
                </div>
              ) : null}
            </section>

            <section className="mm-figure">
              <div className="mm-figure__eyebrow">
                <span>Success rate</span>
              </div>
              <div className="mm-figure__value">
                {!stats
                  ? "…"
                  : finished === 0
                    ? "—"
                    : `${stats.success_rate_percent}%`}
              </div>
              {stats && finished > 0 ? (
                <div
                  className="mm-figure__meter"
                  aria-hidden="true"
                  style={
                    {
                      "--mm-meter-fill": `${stats.success_rate_percent}%`,
                    } as CSSProperties
                  }
                />
              ) : null}
              <p className="mm-figure__note">
                {!stats
                  ? "Last 30 days"
                  : finished === 0
                    ? "No finished jobs yet"
                    : `${finished.toLocaleString()} finished · ${stats.files_failed.toLocaleString()} failed`}
              </p>
            </section>

            <section className="mm-figure">
              <div className="mm-figure__eyebrow">
                <span>Reclaimed</span>
              </div>
              <div className="mm-figure__value">
                {stats ? formatBytes(stats.net_space_saved_bytes) : "…"}
              </div>
              <p className="mm-figure__note">
                Net space saved by removed tracks, last 30 days
              </p>
            </section>
          </div>
        </div>
      )}

      <QuietSection
        headingId="processing-overview-libraries-heading"
        heading="Libraries"
        data-testid="processing-overview-audio-subtitles-glance"
        aside={
          onOpenTab ? (
            <>
              <button
                type="button"
                className="mm-quiet-link"
                onClick={() => onOpenTab("libraries")}
              >
                Open Libraries →
              </button>
              <button
                type="button"
                className="mm-quiet-link"
                onClick={() => onOpenTab("audio-subtitles")}
              >
                Open Audio &amp; subtitles →
              </button>
              <button
                type="button"
                className="mm-quiet-link"
                onClick={() => onOpenTab("schedules")}
              >
                Schedules →
              </button>
              <button
                type="button"
                className="mm-quiet-link"
                onClick={() => onOpenTab("jobs")}
              >
                Jobs →
              </button>
            </>
          ) : null
        }
      >
        {libraries.length === 0 ? (
          <p className="mm-quiet-note">No libraries yet.</p>
        ) : (
          <div className="mm-quiet-table-wrap">
            <table
              className="mm-quiet-table"
              data-testid="processing-overview-libraries"
            >
              <thead>
                <tr>
                  <th scope="col">Library</th>
                  <th scope="col">Watched folder</th>
                  <th scope="col">Output folder</th>
                  <th scope="col">Checks</th>
                  <th scope="col">Audio &amp; subtitles</th>
                </tr>
              </thead>
              <tbody>
                {libraries.map((library) => {
                  const badge = processingMediaTypeBadge(library);
                  const ruleSet =
                    library.rule_set_id === null
                      ? undefined
                      : ruleSetById.get(library.rule_set_id);
                  return (
                    <tr
                      key={library.id}
                      data-testid="processing-overview-library"
                    >
                      <th scope="row" className="mm-quiet-table__name">
                        <span>{library.name}</span>
                        {badge ? (
                          <span className="mm-quiet-badge">{badge}</span>
                        ) : null}
                        {library.enabled ? null : (
                          <span className="mm-quiet-badge mm-quiet-badge--off">
                            Off
                          </span>
                        )}
                      </th>
                      <td data-label="Watched folder">
                        <FolderState set={hasFolder(library.watched_folder)} />
                      </td>
                      <td data-label="Output folder">
                        <FolderState set={hasFolder(library.output_folder)} />
                      </td>
                      <td data-label="Checks">
                        {scanIntervalLabel(library.scan_interval_seconds)}
                      </td>
                      <td data-label="Audio & subtitles">
                        {ruleSets.isPending ? (
                          "…"
                        ) : ruleSet ? (
                          <span>
                            <span className="mm-quiet-table__strong">
                              {ruleSet.name}
                            </span>
                            <span className="mm-quiet-table__sub">
                              {ruleSetSummary(ruleSet)}
                            </span>
                          </span>
                        ) : (
                          <span className="mm-quiet-table__strong">
                            {PROCESSING_MEDIA_TYPE_LABELS[library.media_type]}{" "}
                            defaults
                          </span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </QuietSection>
    </div>
  );
}

function FolderState({ set }: { set: boolean }) {
  return set ? (
    <span className="mm-quiet-state mm-quiet-state--ok">Set</span>
  ) : (
    <span className="mm-quiet-state mm-quiet-state--missing">Not set</span>
  );
}
