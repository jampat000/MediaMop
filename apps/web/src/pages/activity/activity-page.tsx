import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { FileStoryPanel } from "../../components/refiner/file-story-panel";
import { PageLoading } from "../../components/shared/page-loading";
import {
  REFINER_FILE_PROCESSING_PROGRESS_EVENT,
  REFINER_FILE_REMUX_PASS_COMPLETED_EVENT,
  RefinerFileProcessingProgressDetail,
  RefinerFileRemuxPassActivityDetail,
} from "../../lib/activity/refiner-file-remux-pass-detail";
import {
  activityRecentKey,
  useActivityRecentQuery,
} from "../../lib/activity/queries";
import { useActivityStreamInvalidation } from "../../lib/activity/use-activity-stream-invalidation";
import {
  ACTIVITY_RESULT_LABELS,
  ACTIVITY_TRIGGER_LABELS,
  activityTriggerLabel,
  summarizeRun,
} from "../../lib/activity/activity-runs";
import type {
  ActivityEventItem,
  ActivityFileHistoryPreview,
  ActivityRecentResponse,
} from "../../lib/api/types";
import {
  fetchActivityExport,
  fetchActivityFileHistoryPreview,
  fetchActivityRecent,
  removeActivityFileHistory,
} from "../../lib/api/activity-api";
import { useMeQuery } from "../../lib/auth/queries";
import { fetchRefinerFiles } from "../../lib/refiner/files-api";
import { useRefinerFileLog } from "../../lib/refiner/files-queries";
import { useRefinerLibrariesQuery } from "../../lib/refiner/libraries-queries";
import { useSuiteOperationalHistoryResetMutation } from "../../lib/suite/queries";
import { fetchSuiteOperationalHistoryPreview } from "../../lib/suite/suite-settings-api";
import type { SuiteOperationalHistoryResetOut } from "../../lib/suite/types";
import {
  isHttpErrorFromApi,
  isLikelyNetworkFailure,
} from "../../lib/api/error-guards";
import { useAppDateFormatter } from "../../lib/ui/mm-format-date";
import { mmActionButtonClass } from "../../lib/ui/mm-control-roles";
import {
  ClearAllHistoryDialog,
  RemoveFileHistoryDialog,
} from "./activity-history-dialogs";

type ActivityModuleFilter = "all" | "refiner" | "system";
type ActivityTone = "info" | "success" | "warning" | "error";

type ActivityDisplay = {
  title: string;
  summary: string;
  detail: string | null;
  chip: string;
  tone: ActivityTone;
  compact: boolean;
};

type ActivityFiltersState = {
  module: ActivityModuleFilter;
  eventType: string;
  search: string;
  from: string;
  to: string;
  trigger: string;
  result: string;
  libraryId: string;
  file: string;
};

const EMPTY_FILTERS: ActivityFiltersState = {
  module: "all",
  eventType: "",
  search: "",
  from: "",
  to: "",
  trigger: "",
  result: "",
  libraryId: "",
  file: "",
};

type ActivityEventOption = {
  value: string;
  label: string;
};

type ParsedDetail = Record<string, unknown>;

const MODULE_OPTIONS: Array<{ value: ActivityModuleFilter; label: string }> = [
  { value: "all", label: "All modules" },
  { value: "refiner", label: "Refiner" },
  { value: "system", label: "System" },
];

const EVENT_LABELS: Record<string, string> = {
  "auth.login_succeeded": "Sign-in finished",
  "auth.login_failed": "Sign-in failed",
  "auth.logout": "Sign-out finished",
  "auth.bootstrap_succeeded": "First admin created",
  "auth.bootstrap_denied": "First-time setup blocked",
  "auth.password_changed": "Password changed",
  "auth.username_changed": "Username changed",
  "system.reconciliation.repair": "System repair finished",
  "arr_library.connection_test_succeeded": "Connection check finished",
  "arr_library.connection_test_failed": "Connection check failed",
  "refiner.supplied_payload_evaluation_completed":
    "Manual queue check finished",
  "refiner.candidate_gate_completed": "Queue check finished",
  "refiner.file_processing_progress": "File processing",
  "refiner.file_remux_pass_completed": "File processing finished",
  "refiner.work_temp_stale_sweep_completed": "Temporary files cleanup finished",
  "refiner.failure_cleanup_sweep_completed": "Failed-remux cleanup finished",
};

function compactActivityTitle(text: string, maxLength = 92): string {
  const normalized = text.trim();
  if (normalized.length <= maxLength) {
    return normalized;
  }
  const tail = Math.max(14, Math.min(28, maxLength - 24));
  const head = Math.max(20, maxLength - tail - 3);
  return `${normalized.slice(0, head).trimEnd()}...${normalized.slice(-tail).trimStart()}`;
}

function eventOptionLabel(eventType: string): string {
  return (
    EVENT_LABELS[eventType] ??
    eventType.split(".").slice(-1)[0].replaceAll("_", " ")
  );
}

function titleCase(value: string): string {
  return value ? value[0].toUpperCase() + value.slice(1) : value;
}

/** A local date and time in the shape a datetime-local input holds. */
function toLocalInput(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

/** Yesterday 18:00 to today 08:00, local time: when overnight scheduled work runs. */
function lastNightRange(now: Date): { from: string; to: string } {
  const from = new Date(now);
  from.setDate(from.getDate() - 1);
  from.setHours(18, 0, 0, 0);
  const to = new Date(now);
  to.setHours(8, 0, 0, 0);
  return { from: toLocalInput(from), to: toLocalInput(to) };
}

function last24HoursRange(now: Date): { from: string; to: string } {
  return {
    from: toLocalInput(new Date(now.getTime() - 24 * 60 * 60 * 1000)),
    to: "",
  };
}

function plural(count: number, one: string, many: string): string {
  return `${count} ${count === 1 ? one : many}`;
}

function fileNameOf(path: string): string {
  return path.split(/[\\/]/).filter(Boolean).at(-1) ?? path;
}

function localInputToIso(value: string): string | undefined {
  if (!value.trim()) return undefined;
  const parsed = new Date(value);
  return Number.isNaN(parsed.valueOf()) ? undefined : parsed.toISOString();
}

function parseDetail(detail: string | null | undefined): ParsedDetail | null {
  if (!detail?.trim().startsWith("{")) return null;
  try {
    const parsed = JSON.parse(detail) as unknown;
    return parsed && typeof parsed === "object"
      ? (parsed as ParsedDetail)
      : null;
  } catch {
    return null;
  }
}

function asString(value: unknown): string | null {
  if (value == null) return null;
  const text = String(value).trim();
  return text ? text : null;
}

function asNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (
    typeof value === "string" &&
    value.trim() !== "" &&
    Number.isFinite(Number(value))
  )
    return Number(value);
  return null;
}

function asBoolean(value: unknown): boolean | null {
  if (typeof value === "boolean") return value;
  if (value === "true") return true;
  if (value === "false") return false;
  return null;
}

function toneClasses(tone: ActivityTone): string {
  switch (tone) {
    case "success":
      return "mm-activity-tone--success";
    case "warning":
      return "mm-activity-tone--warning";
    case "error":
      return "mm-activity-tone--error";
    default:
      return "border-[var(--mm-border)] bg-[var(--mm-card-bg)]";
  }
}

function chipToneClasses(tone: ActivityTone): string {
  switch (tone) {
    case "success":
      return "mm-activity-chip--success";
    case "warning":
      return "mm-activity-chip--warning";
    case "error":
      return "mm-activity-chip--error";
    default:
      return "border-[var(--mm-border)] bg-black/10 text-[var(--mm-text2)]";
  }
}

function normalizeRefinerSummary(
  ev: ActivityEventItem,
): ActivityDisplay | null {
  if (ev.event_type === REFINER_FILE_PROCESSING_PROGRESS_EVENT) {
    const parsed = parseDetail(ev.detail);
    const status = asString(parsed?.status);
    const percent = asNumber(parsed?.percent);
    const name =
      asString(parsed?.relative_media_path)
        ?.split(/[\\/]/)
        .filter(Boolean)
        .at(-1) ?? "file";
    return {
      title:
        status === "finished"
          ? `${name} finished processing`
          : status === "failed"
            ? `${name} could not be processed`
            : `Refiner is processing ${name}`,
      summary:
        percent == null
          ? "Refiner is preparing the cleaned-up file"
          : `Refiner is writing the cleaned-up file (${Math.round(percent)}%)`,
      detail: ev.detail ?? null,
      chip:
        status === "failed"
          ? "Processing stopped"
          : status === "finished"
            ? "Processing finished"
            : "Processing now",
      tone:
        status === "failed"
          ? "error"
          : status === "finished"
            ? "success"
            : "info",
      compact: false,
    };
  }
  if (ev.event_type === REFINER_FILE_REMUX_PASS_COMPLETED_EVENT) {
    const parsed = parseDetail(ev.detail);
    const outcome = asString(parsed?.outcome);
    const remuxNeeded = asBoolean(parsed?.remux_required);
    const passedThrough = asBoolean(parsed?.pass_through_unchanged) === true;
    const fileName =
      asString(parsed?.relative_media_path)
        ?.split(/[\\/]/)
        .filter(Boolean)
        .at(-1) ??
      asString(parsed?.inspected_source_path)
        ?.split(/[\\/]/)
        .filter(Boolean)
        .at(-1) ??
      "File";
    return {
      title: passedThrough
        ? `${fileName} was passed through unchanged`
        : outcome === "live_skipped_not_required"
          ? `No changes needed for ${fileName}`
          : outcome?.startsWith("failed")
            ? `${fileName} could not be processed`
            : `${fileName} was processed successfully`,
      summary: passedThrough
        ? "Refiner rules were bypassed for this file"
        : outcome === "live_skipped_not_required"
          ? "No changes were needed"
          : outcome?.startsWith("failed")
            ? "Refiner could not finish this file"
            : remuxNeeded === false
              ? "The file already fits your Refiner rules"
              : "Refiner finished writing the cleaned-up file",
      detail: ev.detail ?? null,
      chip: passedThrough
        ? "Passed through"
        : outcome === "live_skipped_not_required"
          ? "No changes needed"
          : outcome?.startsWith("failed")
            ? "Processing failed"
            : "File processed",
      tone: ev.detail?.includes('"ok":false') ? "error" : "success",
      compact: false,
    };
  }
  if (ev.event_type === "refiner.supplied_payload_evaluation_completed") {
    return {
      title: "Manual queue check finished",
      summary: "Download queue safety check",
      detail: ev.detail ?? null,
      chip: "Queue check finished",
      tone: "success",
      compact: true,
    };
  }
  if (ev.event_type === "refiner.candidate_gate_completed") {
    return {
      title: "Queue check finished",
      summary: "Download queue safety check",
      detail: ev.detail ?? null,
      chip: "Queue check finished",
      tone: "success",
      compact: true,
    };
  }
  if (ev.event_type === "refiner.work_temp_stale_sweep_completed") {
    return {
      title: "Temporary files cleanup finished",
      summary: "Background cleanup result",
      detail: ev.detail ?? null,
      chip: "Cleanup finished",
      tone: "success",
      compact: true,
    };
  }
  if (ev.event_type === "refiner.failure_cleanup_sweep_completed") {
    return {
      title: "Failed-remux cleanup finished",
      summary: "Background cleanup result",
      detail: ev.detail ?? null,
      chip: "Cleanup finished",
      tone: "success",
      compact: true,
    };
  }
  return null;
}

function normalizeAuthSummary(ev: ActivityEventItem): ActivityDisplay | null {
  if (!ev.module.startsWith("auth") && !ev.module.startsWith("arr_library"))
    return null;
  return {
    title: eventOptionLabel(ev.event_type),
    summary: ev.module.startsWith("arr_library")
      ? "Service connection check"
      : "Account and sign-in activity",
    detail: ev.detail ?? null,
    chip: "System event",
    tone:
      ev.event_type.includes("failed") || ev.event_type.includes("denied")
        ? "warning"
        : ev.event_type.includes("succeeded") ||
            ev.event_type.includes("changed")
          ? "success"
          : "info",
    compact: false,
  };
}

function eventDisplay(ev: ActivityEventItem): ActivityDisplay {
  const refiner = normalizeRefinerSummary(ev);
  if (refiner) return refiner;
  const auth = normalizeAuthSummary(ev);
  if (auth) return auth;

  const lowered = `${ev.title} ${ev.detail ?? ""}`.toLowerCase();
  const tone: ActivityTone = /(error|failed|denied)/.test(lowered)
    ? "error"
    : /(skip|missing|review|warning|not configured|unsupported)/.test(lowered)
      ? "warning"
      : /(completed|finished|saved|updated|started)/.test(lowered)
        ? "success"
        : "info";
  return {
    title: eventOptionLabel(ev.event_type),
    summary: ev.module === "refiner" ? "Refiner activity" : "System event",
    detail: ev.detail ?? null,
    chip: eventOptionLabel(ev.event_type),
    tone,
    compact: Boolean(ev.detail && ev.detail.length > 120),
  };
}

function ActivitySummaryCard({
  label,
  value,
}: {
  label: string;
  value: string;
}) {
  return (
    <section className="rounded-lg border border-[var(--mm-border)] bg-[var(--mm-card-bg)] px-4 py-3">
      <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--mm-text3)]">
        {label}
      </p>
      <p className="mt-1 text-lg font-semibold text-[var(--mm-text1)]">
        {value}
      </p>
    </section>
  );
}

function StructuredActivityDetails({ ev }: { ev: ActivityEventItem }) {
  const parsed = parseDetail(ev.detail);
  if (!parsed) return null;

  if (ev.event_type === "system.reconciliation.repair") {
    return (
      <div className="rounded-md border border-[var(--mm-border)] bg-black/10 p-3">
        <p className="text-sm leading-6 text-[var(--mm-text2)]">{ev.detail}</p>
      </div>
    );
  }

  return null;
}

function ActivityEventDetails({
  ev,
  display,
}: {
  ev: ActivityEventItem;
  display: ActivityDisplay;
}) {
  if (!display.detail) return null;
  if (ev.event_type === REFINER_FILE_PROCESSING_PROGRESS_EVENT) {
    return <RefinerFileProcessingProgressDetail detail={display.detail} />;
  }
  if (ev.event_type === REFINER_FILE_REMUX_PASS_COMPLETED_EVENT) {
    return <RefinerFileRemuxPassActivityDetail detail={display.detail} />;
  }
  const structured = StructuredActivityDetails({ ev });
  if (structured) {
    return structured;
  }
  if (!display.compact) {
    return (
      <p className="text-sm leading-6 text-[var(--mm-text2)]">
        {display.detail}
      </p>
    );
  }
  return (
    <details className="rounded-md border border-[var(--mm-border)] bg-black/10 px-3 py-2">
      <summary className="cursor-pointer text-sm font-medium text-[var(--mm-text2)]">
        Show event detail
      </summary>
      <p className="mt-3 whitespace-pre-wrap text-sm leading-6 text-[var(--mm-text2)]">
        {display.detail}
      </p>
    </details>
  );
}

function collectEventOptions(
  items: ActivityEventItem[],
): ActivityEventOption[] {
  const seen = new Map<string, string>();
  for (const item of items) {
    if (!seen.has(item.event_type)) {
      seen.set(item.event_type, eventOptionLabel(item.event_type));
    }
  }
  return Array.from(seen.entries())
    .map(([value, label]) => ({ value, label }))
    .sort((a, b) => a.label.localeCompare(b.label));
}

type ActivityGroup = {
  kind: "failures" | "run";
  key: string;
  events: ActivityEventItem[];
};

function groupRepeatedFailures(items: ActivityEventItem[]): ActivityGroup[] {
  const groups: ActivityGroup[] = [];
  for (const event of items) {
    const display = eventDisplay(event);
    const isFailure =
      display.tone === "error" || /failed|denied/i.test(event.event_type);
    const previous = groups.at(-1);
    const key = `${event.module}|${event.event_type}|${display.title}`;
    if (isFailure && previous?.key === key) {
      previous.events.push(event);
    } else {
      groups.push({ kind: "failures", key, events: [event] });
    }
  }
  return groups;
}

/**
 * Consecutive entries that share a run collapse under one summary row; everything else keeps
 * the repeated-failure clustering. A run of one entry is shown as that entry.
 */
function groupActivityFeed(items: ActivityEventItem[]): ActivityGroup[] {
  const groups: ActivityGroup[] = [];
  let loose: ActivityEventItem[] = [];
  const flushLoose = () => {
    groups.push(...groupRepeatedFailures(loose));
    loose = [];
  };
  let index = 0;
  while (index < items.length) {
    const runKey = items[index].run_key;
    let end = index + 1;
    if (runKey) {
      while (end < items.length && items[end].run_key === runKey) end += 1;
    }
    if (runKey && end - index > 1) {
      flushLoose();
      groups.push({
        kind: "run",
        key: `run|${runKey}|${items[index].id}`,
        events: items.slice(index, end),
      });
      index = end;
    } else {
      loose.push(items[index]);
      index += 1;
    }
  }
  flushLoose();
  return groups;
}

type FileTarget = { relative_path: string; library_id: number | null };

function ActivityEventRow({
  ev,
  fmt,
  compact = false,
  libraryName,
  onOpenStory,
  onRemoveHistory,
}: {
  ev: ActivityEventItem;
  fmt: (iso: string) => string;
  compact?: boolean;
  libraryName?: string;
  onOpenStory: (ev: ActivityEventItem) => void;
  onRemoveHistory?: (target: FileTarget) => void;
}) {
  const display = eventDisplay(ev);
  const renderedTitle = compactActivityTitle(display.title);
  const triggerLabel = activityTriggerLabel(ev.trigger);
  const path = ev.relative_path;
  return (
    <article
      className={`rounded-xl border px-4 ${compact ? "mm-activity-row--compact py-2.5" : "py-4"} ${toneClasses(display.tone)}`}
      data-testid="activity-row"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1 space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <span className="mm-activity-event-icon" aria-hidden="true">
              {display.tone === "success"
                ? "✓"
                : display.tone === "error"
                  ? "!"
                  : display.tone === "warning"
                    ? "!"
                    : "·"}
            </span>
            <span className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--mm-gold)]">
              {ev.module === "system" ||
              ev.module === "auth" ||
              ev.module === "arr_library"
                ? "System"
                : titleCase(ev.module)}
            </span>
            <span
              className={`rounded-full border px-2.5 py-1 text-xs font-medium ${chipToneClasses(display.tone)}`}
            >
              {display.chip}
            </span>
            {triggerLabel ? (
              <span
                className="rounded-full border border-[var(--mm-border)] bg-black/10 px-2.5 py-1 text-xs text-[var(--mm-text2)]"
                data-testid="activity-trigger-chip"
                title="Why this happened"
              >
                {triggerLabel}
              </span>
            ) : null}
          </div>
          <h2
            className="min-w-0 break-words text-lg font-semibold text-[var(--mm-text1)] [overflow-wrap:anywhere]"
            title={display.title}
          >
            {renderedTitle}
          </h2>
          {!compact ? (
            <p className="break-words text-sm text-[var(--mm-text3)]">
              {display.summary}
            </p>
          ) : null}
          {path ? (
            <div
              className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm"
              data-testid="activity-row-file"
            >
              <span
                className="min-w-0 break-words font-mono text-xs text-[var(--mm-text2)] [overflow-wrap:anywhere]"
                title={path}
              >
                {libraryName ? `${libraryName} · ` : ""}
                {path}
              </span>
              {ev.module === "refiner" ? (
                <button
                  type="button"
                  className="text-xs font-medium text-[var(--mm-gold)] underline-offset-2 hover:underline"
                  onClick={() => onOpenStory(ev)}
                >
                  File story
                </button>
              ) : null}
              {onRemoveHistory ? (
                <button
                  type="button"
                  className="text-xs font-medium text-[var(--mm-text3)] underline-offset-2 hover:text-[var(--mm-text1)] hover:underline"
                  onClick={() =>
                    onRemoveHistory({
                      relative_path: path,
                      library_id: ev.library_id ?? null,
                    })
                  }
                >
                  Remove this file&apos;s history
                </button>
              ) : null}
            </div>
          ) : null}
        </div>
        <time className="text-sm text-[var(--mm-text3)]">
          {fmt(ev.created_at)}
        </time>
      </div>
      {!compact ? (
        <div className="mt-3">
          <ActivityEventDetails ev={ev} display={display} />
        </div>
      ) : null}
    </article>
  );
}

const FIELD_LABEL_CLASS =
  "flex min-w-0 flex-col gap-1 text-xs font-medium uppercase tracking-[0.12em] text-[var(--mm-text3)]";

type ExportFormat = "csv" | "json";

export function ActivityPage() {
  const [filters, setFilters] = useState<ActivityFiltersState>(EMPTY_FILTERS);
  const [applied, setApplied] = useState<ActivityFiltersState>(EMPTY_FILTERS);
  const [olderItems, setOlderItems] = useState<ActivityEventItem[]>([]);
  const [loadingOlder, setLoadingOlder] = useState(false);
  const [olderError, setOlderError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [exporting, setExporting] = useState<ExportFormat | null>(null);
  const [removal, setRemoval] = useState<{
    target: FileTarget;
    preview: ActivityFileHistoryPreview;
  } | null>(null);
  const [removalBusy, setRemovalBusy] = useState(false);
  const [removalError, setRemovalError] = useState<string | null>(null);
  const [clearPreview, setClearPreview] =
    useState<SuiteOperationalHistoryResetOut | null>(null);
  const [clearError, setClearError] = useState<string | null>(null);
  const [storyName, setStoryName] = useState<string | null>(null);
  const [storyLookupError, setStoryLookupError] = useState<string | null>(null);

  const navigate = useNavigate();
  const me = useMeQuery();
  const canRemove = me.data?.role === "operator" || me.data?.role === "admin";
  const libraries = useRefinerLibrariesQuery();
  const fileLog = useRefinerFileLog();
  const resetHistory = useSuiteOperationalHistoryResetMutation();

  const queryFilters = useMemo(() => {
    const libraryId = Number(applied.libraryId);
    return {
      limit: 100,
      module: applied.module === "all" ? undefined : applied.module,
      event_type: applied.eventType || undefined,
      search: applied.search.trim() || undefined,
      date_from: localInputToIso(applied.from),
      date_to: localInputToIso(applied.to),
      trigger: applied.trigger || undefined,
      result: applied.result || undefined,
      library_id:
        applied.libraryId && Number.isFinite(libraryId) ? libraryId : undefined,
      file: applied.file.trim() || undefined,
    };
  }, [applied]);
  const dataKey = JSON.stringify(queryFilters);

  useActivityStreamInvalidation(activityRecentKey);
  const recent = useActivityRecentQuery(queryFilters);
  const fmt = useAppDateFormatter();

  // Live, but calm: fresh entries only land in the list while the reader is at the top with
  // nothing opened and no older pages loaded. Otherwise the list they are reading stays put and a
  // "new entries" button offers them.
  const live = recent.data;
  const [snapshot, setSnapshot] = useState<{
    key: string;
    data: ActivityRecentResponse;
  } | null>(null);
  const [calm, setCalm] = useState(true);
  const feedRef = useRef<HTMLElement | null>(null);
  const olderLoaded = olderItems.length > 0;
  const hasData = Boolean(live);

  useEffect(() => {
    const evaluate = () => {
      const feed = feedRef.current;
      const atTop = !feed || feed.getBoundingClientRect().top >= 0;
      const expanded = Boolean(feed?.querySelector("details[open]"));
      setCalm(atTop && !expanded && !olderLoaded);
    };
    evaluate();
    window.addEventListener("scroll", evaluate, true);
    document.addEventListener("toggle", evaluate, true);
    return () => {
      window.removeEventListener("scroll", evaluate, true);
      document.removeEventListener("toggle", evaluate, true);
    };
  }, [olderLoaded, hasData]);

  useEffect(() => {
    if (!live) return;
    setSnapshot((prev) =>
      prev && prev.key === dataKey && (prev.data === live || !calm)
        ? prev
        : { key: dataKey, data: live },
    );
  }, [live, dataKey, calm]);

  if (recent.isPending) {
    return <PageLoading label="Loading activity" />;
  }

  if (recent.isError) {
    const err = recent.error;
    return (
      <div className="mm-page">
        <header className="mm-page__intro">
          <p className="mm-page__eyebrow">Overview</p>
          <h1 className="mm-page__title">Activity</h1>
          <p className="mm-page__lead">
            {isLikelyNetworkFailure(err)
              ? "Could not reach the MediaMop API."
              : isHttpErrorFromApi(err)
                ? "The server refused this request. Sign in again if needed."
                : "Could not load activity."}
          </p>
        </header>
        {err instanceof Error ? (
          <p className="mm-page__lead font-mono text-sm text-[var(--mm-text3)]">
            {err.message}
          </p>
        ) : null}
      </div>
    );
  }

  const liveData = recent.data;
  const shown = snapshot && snapshot.key === dataKey ? snapshot.data : liveData;
  const latestItems = shown.items ?? [];
  const itemById = new Map<number, ActivityEventItem>();
  for (const event of [...latestItems, ...olderItems])
    itemById.set(event.id, event);
  const items = Array.from(itemById.values()).sort((a, b) => b.id - a.id);
  const matchingTotal = Math.max(Number(shown.total) || 0, items.length);
  const visibleItems = items.slice(0, matchingTotal || items.length);
  const shownMaxId = visibleItems.reduce((max, ev) => Math.max(max, ev.id), 0);
  const pendingCount =
    shown === liveData
      ? 0
      : (liveData.items ?? []).filter((ev) => ev.id > shownMaxId).length;
  const eventOptions = collectEventOptions(visibleItems);
  const libraryNameById = new Map(
    (libraries.data ?? []).map((library) => [library.id, library.name]),
  );
  const filtersActive = Boolean(
    applied.eventType ||
    applied.search.trim() ||
    applied.from ||
    applied.to ||
    applied.trigger ||
    applied.result ||
    applied.libraryId ||
    applied.file.trim() ||
    applied.module !== "all",
  );
  const hasMore =
    Boolean(shown.has_more) || visibleItems.length < matchingTotal;
  const retentionDays = shown.retention_days;
  const filePaths = Array.from(
    new Set(
      visibleItems
        .map((ev) => ev.relative_path)
        .filter((path): path is string => Boolean(path)),
    ),
  );
  const singleFileTarget: FileTarget | null =
    applied.file.trim() && filePaths.length === 1
      ? {
          relative_path: filePaths[0],
          library_id:
            visibleItems.find((ev) => ev.relative_path === filePaths[0])
              ?.library_id ?? null,
        }
      : null;

  function applyFilters(next: ActivityFiltersState) {
    setFilters(next);
    setApplied(next);
    setOlderItems([]);
    setOlderError(null);
  }

  function showNewEntries() {
    setSnapshot({ key: dataKey, data: liveData });
  }

  async function refreshAfterRemoval() {
    setOlderItems([]);
    const refreshed = await recent.refetch();
    if (refreshed.data) setSnapshot({ key: dataKey, data: refreshed.data });
  }

  async function loadOlderActivity() {
    const oldest = visibleItems.at(-1);
    if (!oldest || loadingOlder) return;
    setLoadingOlder(true);
    setOlderError(null);
    try {
      const page = await fetchActivityRecent({
        ...queryFilters,
        before_id: oldest.id,
      });
      setOlderItems((previous) => {
        const merged = new Map(previous.map((item) => [item.id, item]));
        for (const item of page.items ?? []) merged.set(item.id, item);
        return Array.from(merged.values()).sort((a, b) => b.id - a.id);
      });
    } catch {
      setOlderError("Could not load older activity. Try again.");
    } finally {
      setLoadingOlder(false);
    }
  }

  async function exportHistory(format: ExportFormat) {
    setExporting(format);
    setActionError(null);
    try {
      const { limit: _limit, ...exportFilters } = queryFilters;
      void _limit;
      const { blob, filename } = await fetchActivityExport(
        format,
        exportFilters,
      );
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = filename;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setActionError(
        e instanceof Error ? e.message : "Could not export activity.",
      );
    } finally {
      setExporting(null);
    }
  }

  async function openFileStory(ev: ActivityEventItem) {
    const path = ev.relative_path;
    if (!path) return;
    const normalize = (value: string) => value.replaceAll("\\", "/");
    fileLog.reset();
    setStoryLookupError(null);
    try {
      const page = await fetchRefinerFiles({
        library_id: ev.library_id ?? undefined,
        path_contains: path,
        limit: 50,
      });
      const match = page.files.find(
        (file) =>
          normalize(file.relative_path) === normalize(path) &&
          (ev.library_id == null || file.library_id === ev.library_id),
      );
      if (!match) {
        // No tracked file to tell the story of: show the Files screen for that path instead.
        void navigate(`/refiner?tab=files&path=${encodeURIComponent(path)}`);
        return;
      }
      setStoryName(fileNameOf(path));
      fileLog.mutate(match.id);
    } catch (e) {
      setStoryName(fileNameOf(path));
      setStoryLookupError(
        e instanceof Error ? e.message : "Could not find this file.",
      );
    }
  }

  async function startRemoval(target: FileTarget) {
    setActionError(null);
    setRemovalError(null);
    setNotice(null);
    try {
      const preview = await fetchActivityFileHistoryPreview(target);
      setRemoval({ target, preview });
    } catch (e) {
      setActionError(
        e instanceof Error ? e.message : "Could not check this file's history.",
      );
    }
  }

  async function confirmRemoval() {
    if (!removal) return;
    setRemovalBusy(true);
    setRemovalError(null);
    try {
      const out = await removeActivityFileHistory(removal.target);
      setRemoval(null);
      setNotice(
        `Removed ${plural(out.activity_events_deleted, "Activity event", "Activity events")} and ${plural(out.processing_records_deleted, "processing record", "processing records")} about ${out.relative_path}. No media file was touched.`,
      );
      await refreshAfterRemoval();
    } catch (e) {
      setRemovalError(
        e instanceof Error
          ? e.message
          : "Could not remove this file's history.",
      );
    } finally {
      setRemovalBusy(false);
    }
  }

  async function startClearAll() {
    setActionError(null);
    setClearError(null);
    setNotice(null);
    try {
      setClearPreview(await fetchSuiteOperationalHistoryPreview());
    } catch (e) {
      setActionError(
        e instanceof Error
          ? e.message
          : "Could not check what clearing history would remove.",
      );
    }
  }

  async function confirmClearAll(confirm: string) {
    setClearError(null);
    try {
      const out = await resetHistory.mutateAsync(confirm);
      setClearPreview(null);
      setNotice(
        `History cleared. Removed ${plural(out.activity_events_deleted, "Activity event", "Activity events")} and ${plural(out.refiner_jobs_deleted, "finished Refiner job", "finished Refiner jobs")}. No media file was touched.`,
      );
      await refreshAfterRemoval();
    } catch (e) {
      setClearError(
        e instanceof Error ? e.message : "Could not clear history.",
      );
    }
  }

  const rowProps = {
    fmt,
    onOpenStory: (ev: ActivityEventItem) => void openFileStory(ev),
    onRemoveHistory: canRemove
      ? (target: FileTarget) => void startRemoval(target)
      : undefined,
  };
  const libraryNameFor = (ev: ActivityEventItem) =>
    ev.library_id != null ? libraryNameById.get(ev.library_id) : undefined;

  return (
    <div className="mm-page">
      <header className="mm-page__intro">
        <p className="mm-page__eyebrow">Overview</p>
        <h1 className="mm-page__title">Activity</h1>
        <p className="mm-page__subtitle">
          Live activity timeline for MediaMop, newest first.
        </p>
        <p className="mm-page__lead">
          Use this page to understand what just happened across Refiner and the
          platform. It updates live and keeps the language focused on what the
          action means.
        </p>
        {typeof retentionDays === "number" ? (
          <p
            className="mt-2 text-sm text-[var(--mm-text2)]"
            data-testid="activity-retention"
          >
            {retentionDays > 0
              ? `History goes back ${retentionDays} ${retentionDays === 1 ? "day" : "days"}${shown.oldest_event_at ? ` (oldest entry ${fmt(shown.oldest_event_at)})` : ""}.`
              : "History is kept until you clear it."}{" "}
            <Link
              to="/settings#activity-retention"
              className="text-[var(--mm-gold)] underline-offset-2 hover:underline"
            >
              Change how long history is kept
            </Link>
          </p>
        ) : null}
      </header>

      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <ActivitySummaryCard
          label="Showing now"
          value={`${visibleItems.length} ${visibleItems.length === 1 ? "event" : "events"}`}
        />
        <ActivitySummaryCard
          label="Matches in store"
          value={`${matchingTotal} ${matchingTotal === 1 ? "event" : "events"}`}
        />
        <ActivitySummaryCard
          label="System events"
          value={String(shown.system_events ?? 0)}
        />
        <ActivitySummaryCard label="Refresh" value="Live" />
      </section>

      <section className="mm-activity-filters mt-4 rounded-xl border border-[var(--mm-border)] bg-[var(--mm-card-bg)] p-4">
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <label className={FIELD_LABEL_CLASS}>
            Module
            <select
              className="mm-input"
              value={filters.module}
              onChange={(e) =>
                setFilters((prev) => ({
                  ...prev,
                  module: e.target.value as ActivityModuleFilter,
                }))
              }
            >
              {MODULE_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
          <label className={FIELD_LABEL_CLASS}>
            Event
            <select
              className="mm-input"
              value={filters.eventType}
              onChange={(e) =>
                setFilters((prev) => ({ ...prev, eventType: e.target.value }))
              }
            >
              <option value="">All events</option>
              {eventOptions.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
          <label className={FIELD_LABEL_CLASS}>
            Why it happened
            <select
              className="mm-input"
              value={filters.trigger}
              onChange={(e) =>
                setFilters((prev) => ({ ...prev, trigger: e.target.value }))
              }
            >
              <option value="">Any reason</option>
              {Object.entries(ACTIVITY_TRIGGER_LABELS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <label className={FIELD_LABEL_CLASS}>
            Result
            <select
              className="mm-input"
              value={filters.result}
              onChange={(e) =>
                setFilters((prev) => ({ ...prev, result: e.target.value }))
              }
            >
              <option value="">Any result</option>
              {Object.entries(ACTIVITY_RESULT_LABELS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <label className={FIELD_LABEL_CLASS}>
            Refiner library
            <select
              className="mm-input"
              value={filters.libraryId}
              onChange={(e) =>
                setFilters((prev) => ({ ...prev, libraryId: e.target.value }))
              }
            >
              <option value="">All Refiner libraries</option>
              {(libraries.data ?? []).map((library) => (
                <option key={library.id} value={String(library.id)}>
                  {library.name}
                </option>
              ))}
            </select>
          </label>
          <label className={FIELD_LABEL_CLASS}>
            File
            <input
              className="mm-input"
              value={filters.file}
              onChange={(e) =>
                setFilters((prev) => ({ ...prev, file: e.target.value }))
              }
              placeholder="Part of a file path"
            />
          </label>
          <label className={FIELD_LABEL_CLASS}>
            Search
            <input
              className="mm-input"
              value={filters.search}
              onChange={(e) =>
                setFilters((prev) => ({ ...prev, search: e.target.value }))
              }
              placeholder="Search titles and details"
            />
          </label>
          <label className={FIELD_LABEL_CLASS}>
            From
            <input
              type="datetime-local"
              className="mm-input"
              value={filters.from}
              onChange={(e) =>
                setFilters((prev) => ({ ...prev, from: e.target.value }))
              }
            />
          </label>
          <label className={FIELD_LABEL_CLASS}>
            To
            <input
              type="datetime-local"
              className="mm-input"
              value={filters.to}
              onChange={(e) =>
                setFilters((prev) => ({ ...prev, to: e.target.value }))
              }
            />
          </label>
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <button
            type="button"
            className={mmActionButtonClass({ variant: "primary" })}
            onClick={() => applyFilters(filters)}
          >
            Apply filters
          </button>
          <button
            type="button"
            className={mmActionButtonClass({
              variant: "tertiary",
              disabled: !filtersActive,
            })}
            disabled={!filtersActive}
            onClick={() => applyFilters(EMPTY_FILTERS)}
          >
            Clear
          </button>
          <span className="mx-1 text-xs uppercase tracking-[0.12em] text-[var(--mm-text3)]">
            Quick
          </span>
          <button
            type="button"
            className={mmActionButtonClass({ variant: "secondary" })}
            title="Yesterday 18:00 to today 08:00"
            onClick={() =>
              applyFilters({ ...filters, ...lastNightRange(new Date()) })
            }
          >
            Last night
          </button>
          <button
            type="button"
            className={mmActionButtonClass({ variant: "secondary" })}
            onClick={() =>
              applyFilters({ ...filters, ...last24HoursRange(new Date()) })
            }
          >
            Last 24 hours
          </button>
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-2 text-sm text-[var(--mm-text2)]">
          <span>
            Showing {visibleItems.length} of {matchingTotal} matching{" "}
            {matchingTotal === 1 ? "event" : "events"}.
          </span>
          {filtersActive ? (
            <span className="rounded-full border border-[var(--mm-border)] bg-black/10 px-2 py-0.5 text-xs text-[var(--mm-text2)]">
              Filters active
            </span>
          ) : null}
          {hasMore ? (
            <button
              type="button"
              className={mmActionButtonClass({
                variant: "tertiary",
                disabled: loadingOlder,
              })}
              disabled={loadingOlder}
              onClick={() => void loadOlderActivity()}
            >
              {loadingOlder ? "Loading older…" : "Load older activity"}
            </button>
          ) : null}
          {olderError ? (
            <span className="text-[var(--mm-status-failed-text)]" role="alert">
              {olderError}
            </span>
          ) : null}
          <span className="ml-auto flex flex-wrap items-center gap-2">
            <button
              type="button"
              className={mmActionButtonClass({
                variant: "secondary",
                disabled: exporting !== null,
              })}
              disabled={exporting !== null}
              onClick={() => void exportHistory("csv")}
            >
              {exporting === "csv" ? "Exporting…" : "Export CSV"}
            </button>
            <button
              type="button"
              className={mmActionButtonClass({
                variant: "secondary",
                disabled: exporting !== null,
              })}
              disabled={exporting !== null}
              onClick={() => void exportHistory("json")}
            >
              {exporting === "json" ? "Exporting…" : "Export JSON"}
            </button>
            {canRemove ? (
              <button
                type="button"
                className={mmActionButtonClass({ variant: "tertiary" })}
                onClick={() => void startClearAll()}
              >
                Clear all history
              </button>
            ) : null}
          </span>
        </div>
        {actionError ? (
          <p
            className="mt-3 text-sm text-[var(--mm-status-failed-text)]"
            role="alert"
          >
            {actionError}
          </p>
        ) : null}
        {notice ? (
          <p
            className="mt-3 rounded-md border border-[var(--mm-border)] bg-black/10 px-3 py-2 text-sm text-[var(--mm-text1)]"
            role="status"
          >
            {notice}
          </p>
        ) : null}
      </section>

      {applied.file.trim() ? (
        <section
          className="mt-4 flex flex-wrap items-center gap-3 rounded-xl border border-[var(--mm-border)] bg-[var(--mm-card-bg)] px-4 py-3 text-sm text-[var(--mm-text2)]"
          data-testid="activity-file-view"
        >
          <span className="min-w-0 flex-1 break-words [overflow-wrap:anywhere]">
            {singleFileTarget
              ? `Everything MediaMop recorded about ${singleFileTarget.relative_path}, newest first.`
              : `Everything MediaMop recorded about files matching “${applied.file.trim()}”, newest first.`}
          </span>
          {singleFileTarget && canRemove ? (
            <button
              type="button"
              className={mmActionButtonClass({ variant: "tertiary" })}
              onClick={() => void startRemoval(singleFileTarget)}
            >
              Remove this file&apos;s history
            </button>
          ) : null}
        </section>
      ) : null}

      <section
        ref={feedRef}
        className="mt-4 space-y-3"
        data-testid="activity-feed"
      >
        {pendingCount > 0 ? (
          <div className="sticky top-2 z-10 flex justify-center">
            <button
              type="button"
              className={mmActionButtonClass({ variant: "primary" })}
              onClick={showNewEntries}
            >
              {`${pendingCount} new ${pendingCount === 1 ? "entry" : "entries"} — show`}
            </button>
          </div>
        ) : null}
        {visibleItems.length === 0 ? (
          <div className="rounded-lg border border-[var(--mm-border)] bg-[var(--mm-card-bg)] px-4 py-4 text-sm text-[var(--mm-text2)]">
            No activity matched the current filters.
          </div>
        ) : (
          groupActivityFeed(visibleItems).map((group) => {
            if (group.kind === "run") {
              const summary = summarizeRun(group.events);
              return (
                <details
                  key={group.key}
                  className="mm-activity-cluster"
                  data-testid="activity-run"
                >
                  <summary className="mm-activity-cluster__summary">
                    <span
                      className={`mm-activity-event-icon${summary.failed > 0 ? " mm-activity-event-icon--error" : ""}`}
                      aria-hidden="true"
                    >
                      {summary.failed > 0 ? "!" : "✓"}
                    </span>
                    <span className="min-w-0 flex-1">
                      <strong>{summary.headline}</strong>
                      <small>
                        {plural(group.events.length, "entry", "entries")} ·
                        first {fmt(group.events.at(-1)?.created_at ?? "")} ·
                        latest {fmt(group.events[0].created_at)}
                      </small>
                    </span>
                    {summary.failed > 0 ? (
                      <span className="mm-status-badge mm-status-badge--failed">
                        {summary.failed} failed
                      </span>
                    ) : null}
                  </summary>
                  <div className="mm-activity-cluster__events">
                    {group.events.map((ev) => (
                      <ActivityEventRow
                        key={ev.id}
                        ev={ev}
                        compact
                        libraryName={libraryNameFor(ev)}
                        {...rowProps}
                      />
                    ))}
                  </div>
                </details>
              );
            }
            return group.events.length > 1 ? (
              <details
                key={group.key}
                className="mm-activity-cluster"
                data-testid="activity-cluster"
              >
                <summary className="mm-activity-cluster__summary">
                  <span
                    className="mm-activity-event-icon mm-activity-event-icon--error"
                    aria-hidden="true"
                  >
                    !
                  </span>
                  <span className="min-w-0 flex-1">
                    <strong>{group.events.length} repeated failures</strong>
                    <small>
                      {compactActivityTitle(
                        eventDisplay(group.events[0]).title,
                      )}{" "}
                      · first {fmt(group.events.at(-1)?.created_at ?? "")} ·
                      latest {fmt(group.events[0].created_at)}
                    </small>
                  </span>
                  <span className="mm-status-badge mm-status-badge--failed">
                    Review
                  </span>
                </summary>
                <div className="mm-activity-cluster__events">
                  {group.events.map((ev) => (
                    <ActivityEventRow
                      key={ev.id}
                      ev={ev}
                      compact
                      libraryName={libraryNameFor(ev)}
                      {...rowProps}
                    />
                  ))}
                </div>
              </details>
            ) : (
              <ActivityEventRow
                key={group.events[0].id}
                ev={group.events[0]}
                libraryName={libraryNameFor(group.events[0])}
                {...rowProps}
              />
            );
          })
        )}
      </section>

      {removal ? (
        <RemoveFileHistoryDialog
          preview={removal.preview}
          busy={removalBusy}
          error={removalError}
          onCancel={() => setRemoval(null)}
          onConfirm={() => void confirmRemoval()}
        />
      ) : null}
      {clearPreview ? (
        <ClearAllHistoryDialog
          preview={clearPreview}
          busy={resetHistory.isPending}
          error={clearError}
          onCancel={() => setClearPreview(null)}
          onConfirm={(confirm) => void confirmClearAll(confirm)}
        />
      ) : null}
      <FileStoryPanel
        open={storyName !== null}
        fileName={storyName ?? ""}
        log={fileLog.data}
        loading={fileLog.isPending}
        error={
          storyLookupError ?? (fileLog.isError ? fileLog.error.message : null)
        }
        onClose={() => setStoryName(null)}
      />
    </div>
  );
}
