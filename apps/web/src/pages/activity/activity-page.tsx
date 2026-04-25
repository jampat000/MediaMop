import { useMemo, useState } from "react";
import { PageLoading } from "../../components/shared/page-loading";
import {
  REFINER_FILE_PROCESSING_PROGRESS_EVENT,
  REFINER_FILE_REMUX_PASS_COMPLETED_EVENT,
  RefinerFileProcessingProgressDetail,
  RefinerFileRemuxPassActivityDetail,
} from "../../lib/activity/refiner-file-remux-pass-detail";
import { activityRecentKey, useActivityRecentQuery } from "../../lib/activity/queries";
import { useActivityStreamInvalidation } from "../../lib/activity/use-activity-stream-invalidation";
import type { ActivityEventItem } from "../../lib/api/types";
import { isHttpErrorFromApi, isLikelyNetworkFailure } from "../../lib/api/error-guards";
import { useAppDateFormatter } from "../../lib/ui/mm-format-date";
import { mmActionButtonClass } from "../../lib/ui/mm-control-roles";

type ActivityModuleFilter = "all" | "refiner" | "pruner" | "subber" | "system";
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
  { value: "subber", label: "Subber" },
  { value: "system", label: "System" },
];

const EVENT_LABELS: Record<string, string> = {
  "auth.login_succeeded": "Sign-in finished",
  "auth.login_failed": "Sign-in failed",
  "auth.logout": "Sign-out finished",
  "auth.bootstrap_succeeded": "First admin created",
  "auth.bootstrap_denied": "First-time setup blocked",
  "auth.password_changed": "Password changed",
  "arr_library.connection_test_succeeded": "Connection check finished",
  "arr_library.connection_test_failed": "Connection check failed",
  "refiner.supplied_payload_evaluation_completed": "Manual queue check finished",
  "refiner.candidate_gate_completed": "Queue check finished",
  "refiner.watched_folder_remux_scan_dispatch_completed": "Watched-folder scan finished",
  "refiner.file_processing_progress": "File processing",
  "refiner.file_remux_pass_completed": "File processing finished",
  "refiner.work_temp_stale_sweep_completed": "Temporary files cleanup finished",
  "refiner.failure_cleanup_sweep_completed": "Failed-remux cleanup finished",
  "subber.library_scan_enqueued": "Library scan checked",
  "subber.library_sync_completed": "Library sync finished",
  "subber.subtitle_search_completed": "Subtitle search finished",
  "subber.subtitle_upgrade_completed": "Subtitle upgrade finished",
  "subber.webhook_import_enqueued": "Webhook import started",
  "pruner.connection_test_succeeded": "Connection check finished",
  "pruner.connection_test_failed": "Connection check failed",
  "pruner.preview_succeeded": "Preview finished",
  "pruner.preview_unsupported": "Preview finished",
  "pruner.preview_failed": "Preview finished",
  "pruner.apply_library_removal_completed": "Cleanup finished",
  "pruner.apply_library_removal_failed": "Cleanup finished",
};

function eventOptionLabel(eventType: string): string {
  return EVENT_LABELS[eventType] ?? eventType.split(".").slice(-1)[0].replaceAll("_", " ");
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
    return parsed && typeof parsed === "object" ? (parsed as ParsedDetail) : null;
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
  if (typeof value === "string" && value.trim() !== "" && Number.isFinite(Number(value))) return Number(value);
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
      return "border-emerald-500/25 bg-emerald-500/[0.08]";
    case "warning":
      return "border-amber-400/25 bg-amber-400/[0.08]";
    case "error":
      return "border-red-400/30 bg-red-500/[0.10]";
    default:
      return "border-[var(--mm-border)] bg-[var(--mm-card-bg)]";
  }
}

function chipToneClasses(tone: ActivityTone): string {
  switch (tone) {
    case "success":
      return "border-emerald-500/30 bg-emerald-500/10 text-emerald-200";
    case "warning":
      return "border-amber-400/30 bg-amber-400/10 text-amber-100";
    case "error":
      return "border-red-400/35 bg-red-500/10 text-red-100";
    default:
      return "border-[var(--mm-border)] bg-black/10 text-[var(--mm-text2)]";
  }
}

function normalizeSubberSummary(ev: ActivityEventItem): ActivityDisplay | null {
  const parsed = parseDetail(ev.detail);
  const mediaScope = asString(parsed?.media_scope) ?? (/movie/i.test(ev.title) ? "movies" : "tv");
  const prettyScope = scopeLabel(mediaScope);
  const enqueued = asNumber(parsed?.enqueued);
  const reason = asString(parsed?.reason);
  const error = asString(parsed?.error);
  const ok = asBoolean(parsed?.ok);

  if (ev.event_type === "subber.library_scan_enqueued") {
    if (enqueued === 0) {
      return {
        title: `${prettyScope} library scan checked`,
        summary: "Library scan result",
        detail: `No new ${mediaScope === "movies" ? "movies" : "TV items"} needed a subtitle scan.`,
        chip: "Nothing new found",
        tone: "success",
        compact: false,
      };
    }
    return {
      title: `${prettyScope} library scan started`,
      summary: "Library scan result",
      detail:
        enqueued == null
          ? `${prettyScope} items were added to the subtitle scan queue.`
          : `${enqueued} ${mediaScope === "movies" ? "movie" : "TV"} ${enqueued === 1 ? "item was" : "items were"} added to the subtitle scan queue.`,
      chip: "Library scan queued",
      tone: "info",
      compact: false,
    };
  }

  if (ev.event_type === "subber.library_sync_completed") {
    if (reason === "not_configured") {
      return {
        title: `${prettyScope} library sync skipped`,
        summary: "Library sync result",
        detail: `${mediaScope === "movies" ? "Radarr" : "Sonarr"} is not configured yet.`,
        chip: "Library sync skipped",
        tone: "warning",
        compact: false,
      };
    }
    if (error) {
      return {
        title: `${prettyScope} library sync failed`,
        summary: "Library sync result",
        detail: error,
        chip: "Library sync failed",
        tone: "error",
        compact: false,
      };
    }
    return {
      title: `${prettyScope} library sync finished`,
      summary: "Library sync result",
      detail: ev.detail,
      chip: "Library sync completed",
      tone: "success",
      compact: true,
    };
  }

  if (ev.event_type === "subber.subtitle_search_completed") {
    return {
      title: "Subtitle search finished",
      summary: "Subtitle search result",
      detail:
        reason === "search_count"
          ? "This item was skipped because it already reached the search-attempt limit."
          : ok === true
            ? "A subtitle was downloaded for this item."
            : ok === false
              ? "No better subtitle was found for this item."
              : ev.detail,
      chip: ok === true ? "Subtitle downloaded" : "Search complete",
      tone: ok === true ? "success" : reason ? "warning" : "info",
      compact: true,
    };
  }

  if (ev.event_type === "subber.subtitle_upgrade_completed") {
    return {
      title: "Subtitle upgrade finished",
      summary: "Subtitle upgrade result",
      detail: ev.detail,
      chip: "Upgrade complete",
      tone: "success",
      compact: true,
    };
  }

  if (ev.event_type === "subber.webhook_import_enqueued") {
    return {
      title: `${prettyScope} webhook import started`,
      summary: "Webhook import result",
      detail: ev.detail,
      chip: "Webhook import queued",
      tone: "info",
      compact: true,
    };
  }

  return null;
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
      detail: error ?? ev.detail,
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

  if (ev.event_type === "pruner.apply_library_removal_completed" || ev.event_type === "pruner.apply_library_removal_failed") {
    return {
      title: "Cleanup finished",
      summary: "Cleanup run result",
      detail: error ?? ev.detail,
      chip: ev.event_type === "pruner.apply_library_removal_failed" ? "Cleanup failed" : "Cleanup complete",
      tone: ev.event_type === "pruner.apply_library_removal_failed" ? "error" : "success",
      compact: true,
    };
  }

  if (ev.event_type === "pruner.connection_test_succeeded" || ev.event_type === "pruner.connection_test_failed") {
    return {
      title: "Media server connection check",
      summary: "Media server connection check",
      detail: ev.detail,
      chip: ev.event_type === "pruner.connection_test_failed" ? "Connection failed" : "Connection checked",
      tone: ev.event_type === "pruner.connection_test_failed" ? "warning" : "success",
      compact: false,
    };
  }

  return null;
}

function normalizeRefinerSummary(ev: ActivityEventItem): ActivityDisplay | null {
  if (ev.event_type === REFINER_FILE_PROCESSING_PROGRESS_EVENT) {
    const parsed = parseDetail(ev.detail);
    const status = asString(parsed?.status);
    const percent = asNumber(parsed?.percent);
    const name = asString(parsed?.relative_media_path)?.split(/[\\/]/).filter(Boolean).at(-1) ?? "file";
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
      detail: ev.detail,
      chip: status === "failed" ? "Processing stopped" : status === "finished" ? "Processing finished" : "Processing now",
      tone: status === "failed" ? "error" : status === "finished" ? "success" : "info",
      compact: false,
    };
  }
  if (ev.event_type === REFINER_FILE_REMUX_PASS_COMPLETED_EVENT) {
    const parsed = parseDetail(ev.detail);
    const outcome = asString(parsed?.outcome);
    const remuxNeeded = asBoolean(parsed?.remux_required);
    const fileName =
      asString(parsed?.relative_media_path)?.split(/[\\/]/).filter(Boolean).at(-1) ??
      asString(parsed?.inspected_source_path)?.split(/[\\/]/).filter(Boolean).at(-1) ??
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
      detail: ev.detail,
      chip:
        outcome === "live_skipped_not_required"
          ? "No changes needed"
          : outcome?.startsWith("failed")
            ? "Processing failed"
            : "File processed",
      tone: ev.detail?.includes("\"ok\":false") ? "error" : "success",
      compact: false,
    };
  }
  if (ev.event_type === "refiner.supplied_payload_evaluation_completed") {
    return {
      title: "Manual queue check finished",
      summary: "Download queue safety check",
      detail: ev.detail,
      chip: "Queue check finished",
      tone: "success",
      compact: true,
    };
  }
  if (ev.event_type === "refiner.candidate_gate_completed") {
    return {
      title: "Queue check finished",
      summary: "Download queue safety check",
      detail: ev.detail,
      chip: "Queue check finished",
      tone: "success",
      compact: true,
    };
  }
  if (ev.event_type === "refiner.watched_folder_remux_scan_dispatch_completed") {
    const parsed = parseDetail(ev.detail);
    const queued = asNumber(parsed?.remux_jobs_enqueued) ?? 0;
    const seen = asNumber(parsed?.media_candidates_seen) ?? 0;
    const waiting = asNumber(parsed?.verdict_wait_upstream) ?? 0;
    const userMessage = asString(parsed?.user_message);
    const waitingMessage = asString(parsed?.waiting_message);
    const label = asString(parsed?.scan_result_label);
    const paths = asStringArray(parsed?.enqueued_relative_paths_sample);
    const details = [userMessage, waitingMessage, paths.length ? `Added: ${paths.join(", ")}` : null]
      .filter(Boolean)
      .join(" ");
    return {
      title: label ?? "Watched folder checked",
      summary: seen
        ? `${seen} media file${seen === 1 ? "" : "s"} checked`
        : "No media files found",
      detail: details || ev.detail,
      chip: queued
        ? `${queued} added to Refiner`
        : waiting
          ? "Waiting for files"
          : "Folder checked",
      tone: waiting ? "warning" : queued ? "success" : "info",
      compact: false,
    };
  }
  if (ev.event_type === "refiner.work_temp_stale_sweep_completed") {
    return {
      title: "Temporary files cleanup finished",
      summary: "Background cleanup result",
      detail: ev.detail,
      chip: "Cleanup finished",
      tone: "success",
      compact: true,
    };
  }
  if (ev.event_type === "refiner.failure_cleanup_sweep_completed") {
    return {
      title: "Failed-remux cleanup finished",
      summary: "Background cleanup result",
      detail: ev.detail,
      chip: "Cleanup finished",
      tone: "success",
      compact: true,
    };
  }
  return null;
}

function normalizeAuthSummary(ev: ActivityEventItem): ActivityDisplay | null {
  if (!ev.module.startsWith("auth") && !ev.module.startsWith("arr_library")) return null;
  return {
    title: eventOptionLabel(ev.event_type),
    summary: ev.module.startsWith("arr_library") ? "Service connection check" : "Account and sign-in activity",
    detail: ev.detail,
    chip: "System event",
    tone:
      ev.event_type.includes("failed") || ev.event_type.includes("denied")
        ? "warning"
        : ev.event_type.includes("succeeded") || ev.event_type.includes("changed")
          ? "success"
          : "info",
    compact: false,
  };
}

function eventDisplay(ev: ActivityEventItem): ActivityDisplay {
  const refiner = normalizeRefinerSummary(ev);
  if (refiner) return refiner;
  const subber = normalizeSubberSummary(ev);
  if (subber) return subber;
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
          : ev.module === "subber"
            ? "Subber activity"
            : "System event",
    detail: ev.detail,
    chip: eventOptionLabel(ev.event_type),
    tone,
    compact: Boolean(ev.detail && ev.detail.length > 120),
  };
}

function ActivitySummaryCard({ label, value }: { label: string; value: string }) {
  return (
    <section className="rounded-lg border border-[var(--mm-border)] bg-[var(--mm-card-bg)] px-4 py-3">
      <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--mm-text3)]">{label}</p>
      <p className="mt-1 text-lg font-semibold text-[var(--mm-text1)]">{value}</p>
    </section>
  );
}

function StructuredMetric({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-md border border-[var(--mm-border)] bg-black/10 px-3 py-2">
      <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--mm-text3)]">{label}</p>
      <p className="mt-1 text-sm font-semibold text-[var(--mm-text1)]">{value}</p>
    </div>
  );
}

function ChipsRow({ label, items }: { label: string; items: string[] }) {
  if (items.length === 0) return null;
  return (
    <div className="space-y-2">
      <p className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--mm-text3)]">{label}</p>
      <div className="flex flex-wrap gap-2">
        {items.map((item) => (
          <span key={`${label}-${item}`} className="rounded-full border border-[var(--mm-border)] bg-black/10 px-2.5 py-1 text-xs text-[var(--mm-text2)]">
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
          <StructuredMetric label="Candidates" value={asNumber(parsed.candidate_count) ?? 0} />
          <StructuredMetric label="Trigger" value={asString(parsed.trigger) ?? "Manual"} />
          <StructuredMetric label="Scope" value={scopeLabel(asString(parsed.media_scope))} />
          <StructuredMetric label="Rule" value={asString(parsed.rule_family_id) ?? "General preview"} />
        </div>
        {filters.length > 0 ? (
          <details className="rounded-md border border-[var(--mm-border)] bg-black/10 px-3 py-2">
            <summary className="cursor-pointer text-sm font-medium text-[var(--mm-text2)]">Show preview filters</summary>
            <div className="mt-3">
              <ChipsRow label="Applied filters" items={filters} />
            </div>
          </details>
        ) : null}
        {asString(parsed.error) ? <p className="text-sm text-red-200">{asString(parsed.error)}</p> : null}
        {asString(parsed.unsupported_detail) ? <p className="text-sm text-amber-100">{asString(parsed.unsupported_detail)}</p> : null}
      </div>
    );
  }

  if (ev.event_type === "pruner.apply_library_removal_completed" || ev.event_type === "pruner.apply_library_removal_failed") {
    return (
      <div className="space-y-3 rounded-md border border-[var(--mm-border)] bg-black/10 p-3">
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <StructuredMetric label="Removed" value={asNumber(parsed.removed) ?? 0} />
          <StructuredMetric label="Skipped" value={asNumber(parsed.skipped) ?? 0} />
          <StructuredMetric label="Failed" value={asNumber(parsed.failed) ?? 0} />
          <StructuredMetric label="Action" value={asString(parsed.action) ?? "Delete"} />
        </div>
        {asString(parsed.note) ? <p className="text-sm text-[var(--mm-text2)]">{asString(parsed.note)}</p> : null}
      </div>
    );
  }

  if (ev.event_type === "subber.library_sync_completed") {
    const metrics: Array<{ label: string; value: string | number }> = [];
    const movies = asNumber(parsed.movies);
    const series = asNumber(parsed.series);
    const episodes = asNumber(parsed.episodes);
    const found = asNumber(parsed.subtitles_found);
    if (movies != null) metrics.push({ label: "Movies processed", value: movies });
    if (series != null) metrics.push({ label: "Series processed", value: series });
    if (episodes != null) metrics.push({ label: "Episodes with files", value: episodes });
    if (found != null) metrics.push({ label: "Subtitles found", value: found });
    if (metrics.length === 0 && !asString(parsed.error) && !asString(parsed.reason)) return null;
    return (
      <div className="space-y-3 rounded-md border border-[var(--mm-border)] bg-black/10 p-3">
        {metrics.length > 0 ? <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">{metrics.map((row) => <StructuredMetric key={row.label} label={row.label} value={row.value} />)}</div> : null}
        {asString(parsed.reason) ? <p className="text-sm text-amber-100">{asString(parsed.reason)}</p> : null}
        {asString(parsed.error) ? <p className="text-sm text-red-200">{asString(parsed.error)}</p> : null}
      </div>
    );
  }

  if (ev.event_type === "subber.subtitle_search_completed") {
    return (
      <div className="grid gap-3 rounded-md border border-[var(--mm-border)] bg-black/10 p-3 sm:grid-cols-2 xl:grid-cols-3">
        <StructuredMetric label="Scope" value={scopeLabel(asString(parsed.media_scope))} />
        <StructuredMetric label="State ID" value={asNumber(parsed.state_id) ?? "-"} />
        <StructuredMetric
          label="Outcome"
          value={
            asString(parsed.reason) === "search_count"
              ? "Skipped"
              : asBoolean(parsed.ok) === true
                ? "Subtitle downloaded"
                : "No change"
          }
        />
      </div>
    );
  }

  if (ev.event_type === "subber.subtitle_upgrade_completed") {
    return (
      <div className="grid gap-3 rounded-md border border-[var(--mm-border)] bg-black/10 p-3 sm:grid-cols-2">
        <StructuredMetric label="Checked" value={asNumber(parsed.attempted) ?? 0} />
        <StructuredMetric label="Upgraded" value={asNumber(parsed.upgraded) ?? 0} />
      </div>
    );
  }

  if (ev.event_type === "subber.webhook_import_enqueued") {
    return (
      <div className="space-y-3 rounded-md border border-[var(--mm-border)] bg-black/10 p-3">
        <div className="grid gap-3 sm:grid-cols-2">
          <StructuredMetric label="Queued" value={asNumber(parsed.enqueued) ?? 0} />
          <StructuredMetric label="Scope" value={scopeLabel(asString(parsed.media_scope))} />
        </div>
        {asString(parsed.file_path) ? <p className="text-sm text-[var(--mm-text2)] break-all">{asString(parsed.file_path)}</p> : null}
      </div>
    );
  }

  return null;
}

function ActivityEventDetails({ ev, display }: { ev: ActivityEventItem; display: ActivityDisplay }) {
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
    return <p className="text-sm leading-6 text-[var(--mm-text2)]">{display.detail}</p>;
  }
  return (
    <details className="rounded-md border border-[var(--mm-border)] bg-black/10 px-3 py-2">
      <summary className="cursor-pointer text-sm font-medium text-[var(--mm-text2)]">Show event detail</summary>
      <p className="mt-3 whitespace-pre-wrap text-sm leading-6 text-[var(--mm-text2)]">{display.detail}</p>
    </details>
  );
}

function collectEventOptions(items: ActivityEventItem[]): ActivityEventOption[] {
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
          <p className="mm-page__lead font-mono text-sm text-[var(--mm-text3)]">{err.message}</p>
        ) : null}
      </div>
    );
  }

  const items = recent.data.items;
  const eventOptions = collectEventOptions(items);
  const filtersActive = Boolean(applied.eventType || applied.search.trim() || applied.from || applied.to || applied.module !== "all");

  return (
    <div className="mm-page">
      <header className="mm-page__intro">
        <p className="mm-page__eyebrow">Overview</p>
        <h1 className="mm-page__title">Activity</h1>
        <p className="mm-page__subtitle">Live activity timeline for MediaMop, newest first.</p>
        <p className="mm-page__lead">
          Use this page to understand what just happened across Refiner, Pruner, Subber, and the platform. It updates
          live and keeps the language focused on what the action means.
        </p>
      </header>

      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <ActivitySummaryCard label="Showing now" value={`${items.length} events`} />
        <ActivitySummaryCard label="Matches in store" value={`${recent.data.total} events`} />
        <ActivitySummaryCard label="System events" value={String(recent.data.system_events)} />
        <ActivitySummaryCard label="Refresh" value="Live" />
      </section>

      <section className="mt-4 rounded-xl border border-[var(--mm-border)] bg-[var(--mm-card-bg)] p-4">
        <div className="grid gap-3 lg:grid-cols-[220px_1fr_1fr_1fr_auto_auto]">
          <label className="flex flex-col gap-1 text-xs font-medium uppercase tracking-[0.12em] text-[var(--mm-text3)]">
            Module
            <select
              className="mm-input"
              value={filters.module}
              onChange={(e) => setFilters((prev) => ({ ...prev, module: e.target.value as ActivityModuleFilter }))}
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
              onChange={(e) => setFilters((prev) => ({ ...prev, eventType: e.target.value }))}
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
              onChange={(e) => setFilters((prev) => ({ ...prev, search: e.target.value }))}
              placeholder="Search titles and details"
            />
          </label>
          <label className="flex flex-col gap-1 text-xs font-medium uppercase tracking-[0.12em] text-[var(--mm-text3)]">
            From
            <input
              type="datetime-local"
              className="mm-input"
              value={filters.from}
              onChange={(e) => setFilters((prev) => ({ ...prev, from: e.target.value }))}
            />
          </label>
          <label className="flex flex-col gap-1 text-xs font-medium uppercase tracking-[0.12em] text-[var(--mm-text3)]">
            To
            <input
              type="datetime-local"
              className="mm-input"
              value={filters.to}
              onChange={(e) => setFilters((prev) => ({ ...prev, to: e.target.value }))}
            />
          </label>
          <div className="flex items-end gap-2">
            <button
              type="button"
              className={mmActionButtonClass({ variant: "primary" })}
              onClick={() => setApplied(filters)}
            >
              Apply filters
            </button>
            <button
              type="button"
              className={mmActionButtonClass({ variant: "tertiary", disabled: !filtersActive })}
              disabled={!filtersActive}
              onClick={() => {
                const reset = { module: "all", eventType: "", search: "", from: "", to: "" } as ActivityFiltersState;
                setFilters(reset);
                setApplied(reset);
              }}
            >
              Clear
            </button>
          </div>
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-2 text-sm text-[var(--mm-text2)]">
          <span>
            Showing {items.length} of {recent.data.total} matching events.
          </span>
          {filtersActive ? (
            <span className="rounded-full border border-[var(--mm-border)] bg-black/10 px-2 py-0.5 text-xs text-[var(--mm-text2)]">
              Filters active
            </span>
          ) : null}
        </div>
      </section>

      <section className="mt-4 space-y-3" data-testid="activity-feed">
        {items.length === 0 ? (
          <div className="rounded-lg border border-[var(--mm-border)] bg-[var(--mm-card-bg)] px-4 py-4 text-sm text-[var(--mm-text2)]">
            No activity matched the current filters.
          </div>
        ) : (
          items.map((ev) => {
            const display = eventDisplay(ev);
            return (
              <article
                key={ev.id}
                className={`rounded-xl border px-4 py-4 ${toneClasses(display.tone)}`}
                data-testid="activity-row"
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="space-y-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--mm-gold)]">
                        {ev.module === "system" || ev.module === "auth" || ev.module === "arr_library" ? "System" : titleCase(ev.module)}
                      </span>
                      <span className={`rounded-full border px-2.5 py-1 text-xs font-medium ${chipToneClasses(display.tone)}`}>
                        {display.chip}
                      </span>
                    </div>
                    <h2 className="text-lg font-semibold text-[var(--mm-text1)]">{display.title}</h2>
                    <p className="text-sm text-[var(--mm-text3)]">{display.summary}</p>
                  </div>
                  <time className="text-sm text-[var(--mm-text3)]">{fmt(ev.created_at)}</time>
                </div>
                <div className="mt-3">
                  <ActivityEventDetails ev={ev} display={display} />
                </div>
              </article>
            );
          })
        )}
      </section>
    </div>
  );
}
