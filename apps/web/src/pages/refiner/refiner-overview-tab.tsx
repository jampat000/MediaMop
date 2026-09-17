import type { ReactNode } from "react";
import { MmOverviewSection } from "../../components/overview/mm-overview-cards";
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

type AttentionItem = { text: string; target: RefinerOverviewOpenTab };

function ruleSetSummary(rem: RefinerRuleSet): string {
  const languages = [
    rem.primary_audio_lang,
    rem.secondary_audio_lang,
    rem.tertiary_audio_lang,
  ]
    .filter((code) => (code ?? "").trim())
    .map((code) => refinerStreamLanguageLabel(code))
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

/** The type badge only appears when the name does not already say it ("Movies · Movies"). */
function mediaTypeBadge(library: RefinerLibrary): string | null {
  const label = REFINER_MEDIA_TYPE_LABELS[library.media_type];
  const name = library.name.trim().toLowerCase();
  const lower = label.toLowerCase();
  if (!name || lower.includes(name) || name.includes(lower)) return null;
  if (library.media_type === "tv" && /\b(tv|shows?|series)\b/.test(name)) {
    return null;
  }
  return label;
}

function buildAttention(args: {
  failedCount: number;
  libraries: RefinerLibrary[];
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

function openLabel(target: RefinerOverviewOpenTab): string {
  switch (target) {
    case "libraries":
      return "Open Libraries";
    case "audio-subtitles":
      return "Open Audio & subtitles";
    case "jobs":
      return "Open Jobs";
    case "schedules":
      return "Open Schedules";
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
  libraries: RefinerLibrary[];
  onOpenTab?: (tab: RefinerOverviewOpenTab) => void;
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
      headingId="refiner-guided-setup-heading"
      heading="Get started"
      data-testid="refiner-guided-setup"
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

function AttentionPanel({
  items,
  onOpenTab,
}: {
  items: AttentionItem[];
  onOpenTab?: (tab: RefinerOverviewOpenTab) => void;
}) {
  return (
    <MmOverviewSection
      headingId="refiner-overview-needs-attention-heading"
      heading="Needs attention"
      data-testid="refiner-overview-needs-attention"
    >
      <ul className="mm-proc-attention">
        {items.map((item) => (
          <li key={item.text} className="mm-proc-attention__item">
            <span className="mm-proc-attention__icon" aria-hidden="true">
              !
            </span>
            <span className="mm-proc-attention__text">{item.text}</span>
            {onOpenTab ? (
              <button
                type="button"
                className={mmActionButtonClass({ variant: "secondary" })}
                onClick={() => onOpenTab(item.target)}
              >
                {openLabel(item.target)}
              </button>
            ) : null}
          </li>
        ))}
      </ul>
    </MmOverviewSection>
  );
}

function Stat({
  label,
  value,
  hint,
}: {
  label: string;
  value: ReactNode;
  hint?: string;
}) {
  return (
    <div className="mm-proc-stat">
      <dt className="mm-proc-stat__label">{label}</dt>
      <dd className="mm-proc-stat__value">{value}</dd>
      {hint ? <dd className="mm-proc-stat__hint">{hint}</dd> : null}
    </div>
  );
}

function RefinerOverviewLoadError({ err }: { err: unknown }) {
  return (
    <div className="mm-page__intro" data-testid="refiner-overview-load-error">
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

/** Processing Overview: one contextual panel, the numbers, and every library at a glance. */
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
  const count = (value: number | undefined, ready: boolean) =>
    ready && value !== undefined ? value.toLocaleString() : "…";

  const ruleSetById = new Map(
    (ruleSets.data ?? []).map((ruleSet) => [ruleSet.id, ruleSet]),
  );

  return (
    <div
      data-testid="refiner-overview-panel"
      className="mm-bubble-stack w-full min-w-0"
    >
      {!watchedSet ? (
        <SetupChecklist libraries={libraries} onOpenTab={onOpenTab} />
      ) : attention.length > 0 ? (
        <AttentionPanel items={attention} onOpenTab={onOpenTab} />
      ) : null}

      <MmOverviewSection
        headingId="refiner-overview-at-a-glance-heading"
        heading="At a glance"
        data-testid="refiner-overview-at-a-glance"
      >
        <dl
          className="mm-proc-stats"
          data-testid="refiner-overview-last-30-days"
        >
          <Stat
            label="Processed"
            value={count(stats?.files_processed, Boolean(stats))}
            hint="Last 30 days"
          />
          <Stat
            label="Failed"
            value={count(stats?.files_failed, Boolean(stats))}
            hint="Last 30 days"
          />
          <Stat
            label="Success rate"
            value={
              !stats
                ? "…"
                : finished === 0
                  ? "—"
                  : `${stats.success_rate_percent}%`
            }
            hint={
              finished === 0 && stats ? "No finished jobs yet" : "Last 30 days"
            }
          />
          <Stat
            label="Waiting"
            value={count(pending.data?.jobs.length, Boolean(pending.data))}
            hint="In the queue"
          />
          <Stat
            label="Running"
            value={count(leased.data?.jobs.length, Boolean(leased.data))}
            hint={`Up to ${settings.max_concurrent_files} at once`}
          />
        </dl>
        <p className="mm-proc-caption">
          A file is picked up once it has not changed for{" "}
          {settings.min_file_age_seconds} seconds.
        </p>
      </MmOverviewSection>

      <MmOverviewSection
        headingId="refiner-overview-libraries-heading"
        heading="Libraries"
        data-testid="refiner-overview-audio-subtitles-glance"
      >
        {libraries.length === 0 ? (
          <p className="mm-proc-panel__lead">No libraries yet.</p>
        ) : (
          <div className="mm-proc-table-wrap">
            <table
              className="mm-proc-table"
              data-testid="refiner-overview-libraries"
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
                  const badge = mediaTypeBadge(library);
                  const ruleSet =
                    library.rule_set_id === null
                      ? undefined
                      : ruleSetById.get(library.rule_set_id);
                  return (
                    <tr key={library.id} data-testid="refiner-overview-library">
                      <th scope="row" className="mm-proc-table__name">
                        <span>{library.name}</span>
                        {badge ? (
                          <span className="mm-proc-badge">{badge}</span>
                        ) : null}
                        {library.enabled ? null : (
                          <span className="mm-proc-badge mm-proc-badge--off">
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
                            <span className="mm-proc-table__strong">
                              {ruleSet.name}
                            </span>
                            <span className="mm-proc-table__sub">
                              {ruleSetSummary(ruleSet)}
                            </span>
                          </span>
                        ) : (
                          <span className="mm-proc-table__strong">
                            {REFINER_MEDIA_TYPE_LABELS[library.media_type]}{" "}
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
        {onOpenTab ? (
          <div className="mm-proc-panel__actions">
            <button
              type="button"
              className={mmActionButtonClass({ variant: "secondary" })}
              onClick={() => onOpenTab("libraries")}
            >
              Open Libraries
            </button>
            <button
              type="button"
              className={mmActionButtonClass({ variant: "secondary" })}
              onClick={() => onOpenTab("audio-subtitles")}
            >
              Open Audio &amp; subtitles
            </button>
            <button
              type="button"
              className={mmActionButtonClass({ variant: "tertiary" })}
              onClick={() => onOpenTab("schedules")}
            >
              Schedules
            </button>
            <button
              type="button"
              className={mmActionButtonClass({ variant: "tertiary" })}
              onClick={() => onOpenTab("jobs")}
            >
              Jobs
            </button>
          </div>
        ) : null}
      </MmOverviewSection>
    </div>
  );
}

function FolderState({ set }: { set: boolean }) {
  return set ? (
    <span className="mm-proc-state mm-proc-state--ok">Set</span>
  ) : (
    <span className="mm-proc-state mm-proc-state--missing">Not set</span>
  );
}
