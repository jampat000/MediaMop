import { useMemo, useState } from "react";
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
import type { ActivityEventItem } from "../../lib/api/types";
import { fetchActivityRecent } from "../../lib/api/activity-api";
import {
  isHttpErrorFromApi,
  isLikelyNetworkFailure,
} from "../../lib/api/error-guards";
import { useAppDateFormatter } from "../../lib/ui/mm-format-date";
import { mmActionButtonClass } from "../../lib/ui/mm-control-roles";

type ActivityModuleFilter = "all" | "refiner" | "pruner" | "system";
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
};

type ActivityEventOption = {
  value: string;
  label: string;
};

type ParsedDetail = Record<string, unknown>;

const MODULE_OPTIONS: Array<{ value: ActivityModuleFilter; label: string }> = [
  { value: "all", label: "All modules" },
  { value: "refiner", label: "Refiner" },
  { value: "pruner", label: "Pruner" },
  { value: "system", label: "System" },
];

const EVENT_LABELS: Record<string, string> = {
  "auth.login_succeeded": "Sign-in finished",
  "auth.login_failed": "Sign-in failed",
  "auth.logout": "Sign-out finished",
  "auth.bootstrap_succeeded": "First admin created",
  "auth.bootstrap_denied": "First-time setup blocked",
  "auth.password_changed": "Password changed",
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
  "pruner.connection_test_succeeded": "Connection check finished",
  "pruner.connection_test_failed": "Connection check failed",
  "pruner.preview_succeeded": "Preview finished",
  "pruner.preview_unsupported": "Preview finished",
  "pruner.preview_failed": "Preview finished",
  "pruner.apply_library_removal_completed": "Cleanup finished",
  "pruner.apply_library_removal_failed": "Cleanup finished",
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

function asStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value
    .map((item) => asString(item))
    .filter((item): item is string => Boolean(item));
}

function scopeLabel(raw: string | null): string {
  if (!raw) return "Library";
  return raw === "movies" ? "Movies" : raw === "tv" ? "TV" : titleCase(raw);
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

function normalizePrunerSummary(ev: ActivityEventItem): ActivityDisplay | null {
  const parsed = parseDetail(ev.detail);
  const error = asString(parsed?.error);

  if (
    ev.event_type === "pruner.preview_succeeded" ||
    ev.event_type === "pruner.preview_unsupported" ||
    ev.event_type === "pruner.preview_failed"
  ) {
    return {
      title: "Preview finished",
      summary: "Cleanup preview result",
      detail: error ?? ev.detail ?? null,
      chip:
        ev.event_type === "pruner.preview_unsupported"
          ? "Preview unsupported"
          : ev.event_type === "pruner.preview_failed"
            ? "Preview failed"
            : "Preview complete",
      tone:
        ev.event_type === "pruner.preview_failed"
          ? "error"
          : ev.event_type === "pruner.preview_unsupported"
            ? "warning"
            : "success",
      compact: true,
    };
  }

  if (
    ev.event_type === "pruner.apply_library_removal_completed" ||
    ev.event_type === "pruner.apply_library_removal_failed"
  ) {
    return {
      title: "Cleanup finished",
      summary: "Cleanup run result",
      detail: error ?? ev.detail ?? null,
      chip:
        ev.event_type === "pruner.apply_library_removal_failed"
          ? "Cleanup failed"
          : "Cleanup complete",
      tone:
        ev.event_type === "pruner.apply_library_removal_failed"
          ? "error"
          : "success",
      compact: true,
    };
  }

  if (
    ev.event_type === "pruner.connection_test_succeeded" ||
    ev.event_type === "pruner.connection_test_failed"
  ) {
    return {
      title: "Media server connection check",
      summary: "Media server connection check",
      detail: ev.detail ?? null,
      chip:
        ev.event_type === "pruner.connection_test_failed"
          ? "Connection failed"
          : "Connection checked",
      tone:
        ev.event_type === "pruner.connection_test_failed"
          ? "warning"
          : "success",
      compact: false,
    };
  }

  return null;
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
      title:
        outcome === "live_skipped_not_required"
          ? `No changes needed for ${fileName}`
          : outcome?.startsWith("failed")
            ? `${fileName} could not be processed`
            : `${fileName} was processed successfully`,
      summary:
        outcome === "live_skipped_not_required"
          ? "No changes were needed"
          : outcome?.startsWith("failed")
            ? "Refiner could not finish this file"
            : remuxNeeded === false
              ? "The file already fits your Refiner rules"
              : "Refiner finished writing the cleaned-up file",
      detail: ev.detail ?? null,
      chip:
        outcome === "live_skipped_not_required"
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
  const pruner = normalizePrunerSummary(ev);
  if (pruner) return pruner;
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
    summary:
      ev.module === "refiner"
        ? "Refiner activity"
        : ev.module === "pruner"
          ? "Pruner activity"
          : "System event",
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

function StructuredMetric({
  label,
  value,
}: {
  label: string;
  value: string | number;
}) {
  return (
    <div className="rounded-md border border-[var(--mm-border)] bg-black/10 px-3 py-2">
      <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--mm-text3)]">
        {label}
      </p>
      <p className="mt-1 text-sm font-semibold text-[var(--mm-text1)]">
        {value}
      </p>
    </div>
  );
}

function ChipsRow({ label, items }: { label: string; items: string[] }) {
  if (items.length === 0) return null;
  return (
    <div className="space-y-2">
      <p className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--mm-text3)]">
        {label}
      </p>
      <div className="flex flex-wrap gap-2">
        {items.map((item) => (
          <span
            key={`${label}-${item}`}
            className="rounded-full border border-[var(--mm-border)] bg-black/10 px-2.5 py-1 text-xs text-[var(--mm-text2)]"
          >
            {item}
          </span>
        ))}
      </div>
    </div>
  );
}

function StructuredActivityDetails({ ev }: { ev: ActivityEventItem }) {
  const parsed = parseDetail(ev.detail);
  if (!parsed) return null;

  if (
    ev.event_type === "pruner.preview_succeeded" ||
    ev.event_type === "pruner.preview_unsupported" ||
    ev.event_type === "pruner.preview_failed"
  ) {
    const filters = [
      ...asStringArray(parsed.preview_include_genres),
      ...asStringArray(parsed.preview_include_people),
      ...asStringArray(parsed.preview_include_studios),
      ...asStringArray(parsed.preview_include_collections),
    ];
    return (
      <div className="space-y-3 rounded-md border border-[var(--mm-border)] bg-black/10 p-3">
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <StructuredMetric
            label="Candidates"
            value={asNumber(parsed.candidate_count) ?? 0}
          />
          <StructuredMetric
            label="Trigger"
            value={asString(parsed.trigger) ?? "Manual"}
          />
          <StructuredMetric
            label="Scope"
            value={scopeLabel(asString(parsed.media_scope))}
          />
          <StructuredMetric
            label="Rule"
            value={asString(parsed.rule_family_id) ?? "General preview"}
          />
        </div>
        {filters.length > 0 ? (
          <details className="rounded-md border border-[var(--mm-border)] bg-black/10 px-3 py-2">
            <summary className="cursor-pointer text-sm font-medium text-[var(--mm-text2)]">
              Show preview filters
            </summary>
            <div className="mt-3">
              <ChipsRow label="Applied filters" items={filters} />
            </div>
          </details>
        ) : null}
        {asString(parsed.error) ? (
          <p className="text-sm text-red-200">{asString(parsed.error)}</p>
        ) : null}
        {asString(parsed.unsupported_detail) ? (
          <p className="text-sm text-amber-100">
            {asString(parsed.unsupported_detail)}
          </p>
        ) : null}
      </div>
    );
  }

  if (
    ev.event_type === "pruner.apply_library_removal_completed" ||
    ev.event_type === "pruner.apply_library_removal_failed"
  ) {
    return (
      <div className="space-y-3 rounded-md border border-[var(--mm-border)] bg-black/10 p-3">
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <StructuredMetric
            label="Removed"
            value={asNumber(parsed.removed) ?? 0}
          />
          <StructuredMetric
            label="Skipped"
            value={asNumber(parsed.skipped) ?? 0}
          />
          <StructuredMetric
            label="Failed"
            value={asNumber(parsed.failed) ?? 0}
          />
          <StructuredMetric
            label="Action"
            value={asString(parsed.action) ?? "Delete"}
          />
        </div>
        {asString(parsed.note) ? (
          <p className="text-sm text-[var(--mm-text2)]">
            {asString(parsed.note)}
          </p>
        ) : null}
      </div>
    );
  }

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
      groups.push({ key, events: [event] });
    }
  }
  return groups;
}

function ActivityEventRow({
  ev,
  fmt,
  compact = false,
}: {
  ev: ActivityEventItem;
  fmt: (iso: string) => string;
  compact?: boolean;
}) {
  const display = eventDisplay(ev);
  const renderedTitle = compactActivityTitle(display.title);
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

export function ActivityPage() {
  const [filters, setFilters] = useState<ActivityFiltersState>({
    module: "all",
    eventType: "",
    search: "",
    from: "",
    to: "",
  });
  const [applied, setApplied] = useState<ActivityFiltersState>({
    module: "all",
    eventType: "",
    search: "",
    from: "",
    to: "",
  });
  const [olderItems, setOlderItems] = useState<ActivityEventItem[]>([]);
  const [loadingOlder, setLoadingOlder] = useState(false);
  const [olderError, setOlderError] = useState<string | null>(null);

  const queryFilters = useMemo(
    () => ({
      limit: 100,
      module: applied.module === "all" ? undefined : applied.module,
      event_type: applied.eventType || undefined,
      search: applied.search.trim() || undefined,
      date_from: localInputToIso(applied.from),
      date_to: localInputToIso(applied.to),
    }),
    [applied],
  );

  useActivityStreamInvalidation(activityRecentKey);
  const recent = useActivityRecentQuery(queryFilters);
  const fmt = useAppDateFormatter();

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

  const latestItems = recent.data.items ?? [];
  const itemById = new Map<number, ActivityEventItem>();
  for (const event of [...latestItems, ...olderItems])
    itemById.set(event.id, event);
  const items = Array.from(itemById.values()).sort((a, b) => b.id - a.id);
  const matchingTotal = Math.max(Number(recent.data.total) || 0, items.length);
  const visibleItems = items.slice(0, matchingTotal || items.length);
  const eventOptions = collectEventOptions(visibleItems);
  const filtersActive = Boolean(
    applied.eventType ||
    applied.search.trim() ||
    applied.from ||
    applied.to ||
    applied.module !== "all",
  );
  const hasMore =
    Boolean(recent.data.has_more) || visibleItems.length < matchingTotal;

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

  return (
    <div className="mm-page">
      <header className="mm-page__intro">
        <p className="mm-page__eyebrow">Overview</p>
        <h1 className="mm-page__title">Activity</h1>
        <p className="mm-page__subtitle">
          Live activity timeline for MediaMop, newest first.
        </p>
        <p className="mm-page__lead">
          Use this page to understand what just happened across Refiner, Pruner,
          and the platform. It updates live and keeps the language focused on
          what the action means.
        </p>
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
          value={String(recent.data.system_events ?? 0)}
        />
        <ActivitySummaryCard label="Refresh" value="Live" />
      </section>

      <section className="mm-activity-filters mt-4 rounded-xl border border-[var(--mm-border)] bg-[var(--mm-card-bg)] p-4">
        <div className="grid gap-3 lg:grid-cols-[220px_1fr_1fr_1fr_auto_auto]">
          <label className="flex flex-col gap-1 text-xs font-medium uppercase tracking-[0.12em] text-[var(--mm-text3)]">
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
          <label className="flex flex-col gap-1 text-xs font-medium uppercase tracking-[0.12em] text-[var(--mm-text3)]">
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
          <label className="flex flex-col gap-1 text-xs font-medium uppercase tracking-[0.12em] text-[var(--mm-text3)]">
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
          <label className="flex flex-col gap-1 text-xs font-medium uppercase tracking-[0.12em] text-[var(--mm-text3)]">
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
          <label className="flex flex-col gap-1 text-xs font-medium uppercase tracking-[0.12em] text-[var(--mm-text3)]">
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
          <div className="flex items-end gap-2">
            <button
              type="button"
              className={mmActionButtonClass({ variant: "primary" })}
              onClick={() => {
                setApplied(filters);
                setOlderItems([]);
                setOlderError(null);
              }}
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
              onClick={() => {
                const reset = {
                  module: "all",
                  eventType: "",
                  search: "",
                  from: "",
                  to: "",
                } as ActivityFiltersState;
                setFilters(reset);
                setApplied(reset);
                setOlderItems([]);
                setOlderError(null);
              }}
            >
              Clear
            </button>
          </div>
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
        </div>
      </section>

      <section className="mt-4 space-y-3" data-testid="activity-feed">
        {visibleItems.length === 0 ? (
          <div className="rounded-lg border border-[var(--mm-border)] bg-[var(--mm-card-bg)] px-4 py-4 text-sm text-[var(--mm-text2)]">
            No activity matched the current filters.
          </div>
        ) : (
          groupRepeatedFailures(visibleItems).map((group) =>
            group.events.length > 1 ? (
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
                    <ActivityEventRow key={ev.id} ev={ev} fmt={fmt} compact />
                  ))}
                </div>
              </details>
            ) : (
              <ActivityEventRow
                key={group.events[0].id}
                ev={group.events[0]}
                fmt={fmt}
              />
            ),
          )
        )}
      </section>
    </div>
  );
}
