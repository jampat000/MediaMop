import { useState } from "react";

import { MmOnOffSwitch } from "../../components/ui/mm-on-off-switch";
import { PageLoading } from "../../components/shared/page-loading";
import { ScheduleGridEditor } from "./schedule-grid-editor";
import { useMeQuery } from "../../lib/auth/queries";
import { useMediaManagerConnectionsQuery } from "../../lib/media-managers/queries";
import {
  REFINER_MEDIA_SCOPE_LABELS,
  type RefinerLibrary,
  type RefinerLibraryWrite,
  type RefinerMediaScope,
} from "../../lib/refiner/libraries-api";
import {
  useCreateRefinerLibrary,
  useDeleteRefinerLibrary,
  useDiscoverRefinerLibraries,
  useImportDiscoveredRefinerLibraries,
  useRefinerLibrariesQuery,
  useRefinerRuleSetsQuery,
  useRefinerLibraryDrift,
  useReorderRefinerLibraries,
  useUnlinkDiscoveredRefinerLibrary,
  useUpdateRefinerLibrary,
} from "../../lib/refiner/libraries-queries";
import {
  mmActionButtonClass,
  mmEditableTextFieldClass,
  mmSelectFieldClass,
} from "../../lib/ui/mm-control-roles";

function canEdit(role: string | undefined): boolean {
  return role === "operator" || role === "admin";
}

const SCOPES: RefinerMediaScope[] = ["movie", "tv"];

type FormState = {
  name: string;
  media_scope: RefinerMediaScope;
  watched_folder: string;
  work_folder: string;
  output_folder: string;
  media_extensions_csv: string;
  exclude_markers_csv: string;
  include_patterns_csv: string;
  exclude_patterns_csv: string;
  min_file_size_mb: string;
  max_file_size_mb: string;
  rejected_file_action: "leave" | "delete_file";
  min_file_age_seconds: string;
  created_after: string;
  created_before: string;
  modified_after: string;
  modified_before: string;
  scan_interval_seconds: string;
  hold_minutes: string;
  file_detection_interval_seconds: string;
  max_concurrent_files: string;
  priority: string;
  sidecar_patterns_csv: string;
  output_collision_policy: string;
  hardware_decode_mode: string;
  hardware_device: string;
  hardware_disabled_vendors_csv: string;
  ffmpeg_strictness: string;
  max_attempts: string;
  retry_backoff_seconds: string;
  exclude_hidden: boolean;
  top_level_only: boolean;
  ignore_size_changes: boolean;
  skip_access_tests: boolean;
  file_system_events_enabled: boolean;
  preserve_original_timestamps: boolean;
  retry_execution_failures: boolean;
  retry_preflight_failures: boolean;
  schedule_grid: string;
  rule_set_id: string;
};

type BooleanFormKey = {
  [Key in keyof FormState]: FormState[Key] extends boolean ? Key : never;
}[keyof FormState];

const EMPTY_FORM: FormState = {
  name: "",
  media_scope: "movie",
  watched_folder: "",
  work_folder: "",
  output_folder: "",
  media_extensions_csv: ".mkv,.mp4,.m4v,.webm,.avi",
  exclude_markers_csv:
    ".sabnzbd,__admin__,_failed_,_unpack_,_repair_,incomplete",
  include_patterns_csv: "",
  exclude_patterns_csv: "",
  min_file_size_mb: "0",
  max_file_size_mb: "0",
  rejected_file_action: "leave",
  min_file_age_seconds: "60",
  created_after: "",
  created_before: "",
  modified_after: "",
  modified_before: "",
  scan_interval_seconds: "300",
  hold_minutes: "0",
  file_detection_interval_seconds: "30",
  max_concurrent_files: "1",
  priority: "0",
  sidecar_patterns_csv: ".srt,.ass,.ssa,.sub,.idx,.vtt,.nfo,.jpg,.png",
  output_collision_policy: "replace",
  hardware_decode_mode: "off",
  hardware_device: "",
  hardware_disabled_vendors_csv: "",
  ffmpeg_strictness: "normal",
  max_attempts: "3",
  retry_backoff_seconds: "300",
  exclude_hidden: true,
  top_level_only: false,
  ignore_size_changes: false,
  skip_access_tests: false,
  file_system_events_enabled: true,
  preserve_original_timestamps: false,
  retry_execution_failures: true,
  retry_preflight_failures: false,
  schedule_grid: "",
  rule_set_id: "",
};

function localDateTimeValue(value: string | null): string {
  if (!value) return "";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "";
  const local = new Date(
    parsed.getTime() - parsed.getTimezoneOffset() * 60_000,
  );
  return local.toISOString().slice(0, 16);
}

function utcDateTimeValue(value: string): string | null {
  if (!value.trim()) return null;
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? null : parsed.toISOString();
}

function formFrom(library: RefinerLibrary): FormState {
  return {
    name: library.name,
    media_scope: library.media_scope,
    watched_folder: library.watched_folder,
    work_folder: library.work_folder,
    output_folder: library.output_folder,
    media_extensions_csv: library.media_extensions_csv,
    exclude_markers_csv: library.exclude_markers_csv,
    include_patterns_csv: library.include_patterns_csv,
    exclude_patterns_csv: library.exclude_patterns_csv,
    min_file_size_mb: String(library.min_file_size_mb),
    max_file_size_mb: String(library.max_file_size_mb),
    rejected_file_action: library.rejected_file_action,
    min_file_age_seconds: String(library.min_file_age_seconds),
    created_after: localDateTimeValue(library.created_after),
    created_before: localDateTimeValue(library.created_before),
    modified_after: localDateTimeValue(library.modified_after),
    modified_before: localDateTimeValue(library.modified_before),
    scan_interval_seconds: String(library.scan_interval_seconds),
    hold_minutes: String(library.hold_minutes),
    file_detection_interval_seconds: String(
      library.file_detection_interval_seconds,
    ),
    max_concurrent_files: String(library.max_concurrent_files),
    priority: String(library.priority),
    sidecar_patterns_csv: library.sidecar_patterns_csv,
    output_collision_policy: library.output_collision_policy,
    hardware_decode_mode: library.hardware_decode_mode,
    hardware_device: library.hardware_device,
    hardware_disabled_vendors_csv: library.hardware_disabled_vendors_csv,
    ffmpeg_strictness: library.ffmpeg_strictness,
    max_attempts: String(library.max_attempts),
    retry_backoff_seconds: String(library.retry_backoff_seconds),
    exclude_hidden: library.exclude_hidden,
    top_level_only: library.top_level_only,
    ignore_size_changes: library.ignore_size_changes,
    skip_access_tests: library.skip_access_tests,
    file_system_events_enabled: library.file_system_events_enabled,
    preserve_original_timestamps: library.preserve_original_timestamps,
    retry_execution_failures: library.retry_execution_failures,
    retry_preflight_failures: library.retry_preflight_failures,
    schedule_grid: library.schedule_grid,
    rule_set_id:
      library.rule_set_id === null ? "" : String(library.rule_set_id),
  };
}

function writeFrom(
  form: FormState,
  library?: RefinerLibrary,
): RefinerLibraryWrite {
  const asNumber = (raw: string, fallback: number) => {
    const n = Number.parseInt(raw, 10);
    return Number.isFinite(n) ? n : fallback;
  };
  return {
    name: form.name.trim(),
    media_scope: form.media_scope,
    enabled: library?.enabled ?? true,
    watched_folder: form.watched_folder.trim(),
    work_folder: form.work_folder.trim(),
    output_folder: form.output_folder.trim(),
    media_extensions_csv: form.media_extensions_csv.trim(),
    exclude_markers_csv: form.exclude_markers_csv.trim(),
    include_patterns_csv: form.include_patterns_csv.trim(),
    exclude_patterns_csv: form.exclude_patterns_csv.trim(),
    min_file_size_mb: asNumber(form.min_file_size_mb, 0),
    max_file_size_mb: asNumber(form.max_file_size_mb, 0),
    rejected_file_action: form.rejected_file_action,
    min_file_age_seconds: asNumber(form.min_file_age_seconds, 60),
    created_after: utcDateTimeValue(form.created_after),
    created_before: utcDateTimeValue(form.created_before),
    modified_after: utcDateTimeValue(form.modified_after),
    modified_before: utcDateTimeValue(form.modified_before),
    scan_interval_seconds: asNumber(form.scan_interval_seconds, 300),
    hold_minutes: asNumber(form.hold_minutes, 0),
    file_detection_interval_seconds: asNumber(
      form.file_detection_interval_seconds,
      30,
    ),
    max_concurrent_files: asNumber(form.max_concurrent_files, 1),
    priority: asNumber(form.priority, 0),
    sidecar_patterns_csv: form.sidecar_patterns_csv.trim(),
    preserve_original_timestamps: form.preserve_original_timestamps,
    output_collision_policy: form.output_collision_policy,
    hardware_decode_mode: form.hardware_decode_mode,
    hardware_device: form.hardware_device.trim(),
    hardware_disabled_vendors_csv: form.hardware_disabled_vendors_csv.trim(),
    ffmpeg_strictness: form.ffmpeg_strictness,
    max_attempts: asNumber(form.max_attempts, 3),
    retry_backoff_seconds: asNumber(form.retry_backoff_seconds, 300),
    retry_execution_failures: form.retry_execution_failures,
    retry_preflight_failures: form.retry_preflight_failures,
    exclude_hidden: form.exclude_hidden,
    top_level_only: form.top_level_only,
    ignore_size_changes: form.ignore_size_changes,
    skip_access_tests: form.skip_access_tests,
    file_system_events_enabled: form.file_system_events_enabled,
    schedule_grid: form.schedule_grid,
    schedule_enabled: library?.schedule_enabled ?? true,
    schedule_hours_limited: library?.schedule_hours_limited ?? false,
    schedule_days: library?.schedule_days ?? "",
    schedule_start: library?.schedule_start ?? "00:00",
    schedule_end: library?.schedule_end ?? "23:59",
    rule_set_id: form.rule_set_id ? Number(form.rule_set_id) : null,
    manager_connection_ids: library?.manager_connection_ids ?? [],
  };
}

function errorText(error: unknown, fallback: string): string {
  if (error && typeof error === "object" && "message" in error) {
    const message = String(
      (error as { message: unknown }).message ?? "",
    ).trim();
    if (message) return message;
  }
  return fallback;
}

function managerCoverageLabel(value: string): string {
  if (value === "connected") return "Connected";
  if (value === "unreachable") return "Unreachable";
  return "No upstream signal";
}

function managerCoverageClass(value: string): string {
  if (value === "connected") {
    return "border-emerald-700/50 bg-emerald-500/10 text-emerald-300";
  }
  if (value === "unreachable") {
    return "border-rose-700/50 bg-rose-500/10 text-rose-300";
  }
  return "border-amber-700/50 bg-amber-500/10 text-amber-300";
}

/**
 * Refiner libraries: add, edit, reorder, enable, remove.
 *
 * Replaces the fixed Movies/TV path form. A library is a row now, so a fourth one is
 * an ordinary thing to have rather than a schema change (ADR-0014).
 */
export function RefinerLibrariesSection() {
  const me = useMeQuery();
  const libraries = useRefinerLibrariesQuery();
  const ruleSets = useRefinerRuleSetsQuery();
  const create = useCreateRefinerLibrary();
  const update = useUpdateRefinerLibrary();
  const remove = useDeleteRefinerLibrary();
  const reorder = useReorderRefinerLibraries();
  const connections = useMediaManagerConnectionsQuery();
  const discover = useDiscoverRefinerLibraries();
  const importDiscovered = useImportDiscoveredRefinerLibraries();
  const drift = useRefinerLibraryDrift();
  const unlinkDiscovered = useUnlinkDiscoveredRefinerLibrary();

  const [adding, setAdding] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [notice, setNotice] = useState<string | null>(null);
  const [selectedConnectionId, setSelectedConnectionId] = useState("");
  const [selectedDiscoveredKeys, setSelectedDiscoveredKeys] = useState<
    string[]
  >([]);

  const editable = canEdit(me.data?.role);
  const rows = libraries.data ?? [];

  if (libraries.isLoading) return <PageLoading label="Loading libraries" />;

  const startAdd = () => {
    setForm(EMPTY_FORM);
    setEditingId(null);
    setAdding(true);
    setNotice(null);
  };

  const startEdit = (library: RefinerLibrary) => {
    setForm(formFrom(library));
    setEditingId(library.id);
    setAdding(false);
    setNotice(null);
  };

  const cancel = () => {
    setAdding(false);
    setEditingId(null);
    setNotice(null);
  };

  const save = async () => {
    setNotice(null);
    try {
      if (editingId !== null) {
        const existing = rows.find((r) => r.id === editingId);
        await update.mutateAsync({
          id: editingId,
          data: writeFrom(form, existing),
        });
      } else {
        await create.mutateAsync(writeFrom(form));
      }
      cancel();
    } catch (error) {
      setNotice(errorText(error, "That library could not be saved."));
    }
  };

  const toggleEnabled = async (library: RefinerLibrary) => {
    setNotice(null);
    try {
      await update.mutateAsync({
        id: library.id,
        data: {
          ...writeFrom(formFrom(library), library),
          enabled: !library.enabled,
        },
      });
    } catch (error) {
      setNotice(errorText(error, "That library could not be changed."));
    }
  };

  const removeLibrary = async (library: RefinerLibrary) => {
    setNotice(null);
    try {
      await remove.mutateAsync(library.id);
    } catch (error) {
      // The refusal reason is the useful part: it says how much work is in flight.
      setNotice(errorText(error, "That library could not be removed."));
    }
  };

  const move = async (library: RefinerLibrary, direction: -1 | 1) => {
    const ordered = [...rows].sort((a, b) => a.display_order - b.display_order);
    const index = ordered.findIndex((r) => r.id === library.id);
    const target = index + direction;
    if (index < 0 || target < 0 || target >= ordered.length) return;
    const swapped = [...ordered];
    [swapped[index], swapped[target]] = [swapped[target], swapped[index]];
    setNotice(null);
    try {
      await reorder.mutateAsync(swapped.map((r) => r.id));
    } catch (error) {
      setNotice(errorText(error, "Libraries could not be reordered."));
    }
  };

  const discoverFromManager = async () => {
    const connectionId = Number.parseInt(selectedConnectionId, 10);
    if (!Number.isFinite(connectionId)) {
      setNotice("Choose a media manager first.");
      return;
    }
    setNotice(null);
    setSelectedDiscoveredKeys([]);
    try {
      await discover.mutateAsync(connectionId);
    } catch (error) {
      setNotice(
        errorText(
          error,
          "MediaMop could not discover libraries from that manager.",
        ),
      );
    }
  };

  const importSelectedLibraries = async () => {
    const connectionId = Number.parseInt(selectedConnectionId, 10);
    if (!Number.isFinite(connectionId) || selectedDiscoveredKeys.length === 0)
      return;
    setNotice(null);
    try {
      const created = await importDiscovered.mutateAsync({
        connectionId,
        keys: selectedDiscoveredKeys,
      });
      setSelectedDiscoveredKeys([]);
      await discover.mutateAsync(connectionId);
      setNotice(
        `${created.length} ${created.length === 1 ? "library was" : "libraries were"} imported. Review its local paths before enabling processing.`,
      );
    } catch (error) {
      setNotice(errorText(error, "Those libraries could not be imported."));
    }
  };

  const compareWithManager = async () => {
    const connectionId = Number.parseInt(selectedConnectionId, 10);
    if (!Number.isFinite(connectionId)) {
      setNotice("Choose a media manager first.");
      return;
    }
    setNotice(null);
    try {
      await drift.mutateAsync(connectionId);
    } catch (error) {
      setNotice(
        errorText(
          error,
          "MediaMop could not compare libraries with that manager.",
        ),
      );
    }
  };

  const unlink = async (library: RefinerLibrary) => {
    setNotice(null);
    try {
      await unlinkDiscovered.mutateAsync(library.id);
      setNotice(
        `${library.name} is now a manual library. Its folders and settings were not changed.`,
      );
    } catch (error) {
      setNotice(errorText(error, "That library could not be unlinked."));
    }
  };

  const field = (
    label: string,
    key: keyof FormState,
    placeholder = "",
    hint?: string,
  ) => (
    <label className="block text-sm" key={key}>
      <span className="text-[var(--mm-text2)]">{label}</span>
      <input
        className={mmEditableTextFieldClass}
        value={String(form[key])}
        placeholder={placeholder}
        onChange={(e) => setForm({ ...form, [key]: e.target.value })}
        disabled={!editable}
      />
      {hint ? (
        <span className="mt-1 block text-xs text-[var(--mm-text3)]">
          {hint}
        </span>
      ) : null}
    </label>
  );

  const toggle = (label: string, key: BooleanFormKey, hint?: string) => (
    <label
      className="flex items-start gap-2 rounded-lg border border-[var(--mm-border)] px-3 py-2 text-sm text-[var(--mm-text2)]"
      key={key}
    >
      <input
        className="mt-0.5"
        type="checkbox"
        checked={form[key]}
        onChange={(event) => setForm({ ...form, [key]: event.target.checked })}
        disabled={!editable}
      />
      <span>
        <span className="block text-[var(--mm-text1)]">{label}</span>
        {hint ? (
          <span className="mt-0.5 block text-xs text-[var(--mm-text3)]">
            {hint}
          </span>
        ) : null}
      </span>
    </label>
  );

  const dateTimeField = (label: string, key: keyof FormState) => (
    <label className="block text-sm" key={key}>
      <span className="text-[var(--mm-text2)]">{label}</span>
      <input
        type="datetime-local"
        className={mmEditableTextFieldClass}
        value={String(form[key])}
        onChange={(event) => setForm({ ...form, [key]: event.target.value })}
        disabled={!editable}
      />
    </label>
  );

  return (
    <div className="space-y-4" data-testid="refiner-libraries-section">
      <div className="flex items-center justify-between gap-3">
        <p className="text-sm text-[var(--mm-text2)]">
          Each library has its own folders, file types and schedule. Add as many
          as you need — a 4K library and a kids library are separate libraries.
        </p>
        {editable ? (
          <button
            type="button"
            className={mmActionButtonClass({ variant: "primary" })}
            onClick={startAdd}
            data-testid="refiner-library-add"
          >
            Add library
          </button>
        ) : null}
      </div>

      {notice ? (
        <p
          className="rounded border border-[var(--mm-border)] px-3 py-2 text-sm text-[var(--mm-text1)]"
          role="status"
          data-testid="refiner-library-notice"
        >
          {notice}
        </p>
      ) : null}

      {editable && (connections.data?.length ?? 0) > 0 ? (
        <section className="space-y-3 rounded-xl border border-[var(--mm-border)] bg-[var(--mm-card-bg)] p-4">
          <div>
            <h3 className="font-medium text-[var(--mm-text1)]">
              Import from a media manager
            </h3>
            <p className="text-sm text-[var(--mm-text3)]">
              Ask a connected manager which libraries it owns. Comparisons
              report path differences and never change an existing watched
              folder.
            </p>
          </div>
          <div className="flex flex-wrap items-end gap-2">
            <label className="min-w-64 flex-1 text-sm">
              <span className="text-[var(--mm-text2)]">Media manager</span>
              <select
                className={mmSelectFieldClass}
                value={selectedConnectionId}
                onChange={(event) => {
                  setSelectedConnectionId(event.target.value);
                  setSelectedDiscoveredKeys([]);
                  discover.reset();
                  drift.reset();
                }}
              >
                <option value="">Choose a manager</option>
                {connections.data?.map((connection) => (
                  <option key={connection.id} value={connection.id}>
                    {connection.name}
                  </option>
                ))}
              </select>
            </label>
            <button
              type="button"
              className={mmActionButtonClass({ variant: "secondary" })}
              onClick={() => void discoverFromManager()}
              disabled={!selectedConnectionId || discover.isPending}
            >
              Discover libraries
            </button>
            <button
              type="button"
              className={mmActionButtonClass({ variant: "secondary" })}
              onClick={() => void compareWithManager()}
              disabled={!selectedConnectionId || drift.isPending}
            >
              Check for changes
            </button>
          </div>

          {discover.data ? (
            <div className="space-y-2" aria-label="Discovered libraries">
              {discover.data.length === 0 ? (
                <p className="text-sm text-[var(--mm-text3)]">
                  That manager did not report any libraries.
                </p>
              ) : (
                discover.data.map((item) => {
                  const unavailable =
                    item.already_imported ||
                    Boolean(item.local_path_problem) ||
                    !item.media_scope;
                  return (
                    <label
                      key={item.key}
                      className="flex items-start gap-3 rounded-lg border border-[var(--mm-border)] px-3 py-2"
                    >
                      <input
                        type="checkbox"
                        className="mt-1"
                        checked={selectedDiscoveredKeys.includes(item.key)}
                        disabled={unavailable}
                        onChange={(event) =>
                          setSelectedDiscoveredKeys((current) =>
                            event.target.checked
                              ? [...current, item.key]
                              : current.filter((key) => key !== item.key),
                          )
                        }
                      />
                      <span className="min-w-0">
                        <span className="block font-medium text-[var(--mm-text1)]">
                          {item.name}
                        </span>
                        <span className="block break-all text-xs text-[var(--mm-text3)]">
                          Manager path: {item.root_path || "Not supplied"}
                        </span>
                        {item.output_path ? (
                          <span className="block break-all text-xs text-[var(--mm-text3)]">
                            Processed output: {item.output_path}
                          </span>
                        ) : null}
                        {item.already_imported ? (
                          <span className="block text-xs text-[var(--mm-status-healthy-text)]">
                            Already imported
                          </span>
                        ) : null}
                        {item.local_path_problem || item.output_path_problem ? (
                          <span className="block text-xs text-[var(--mm-status-warning-text)]">
                            {item.local_path_problem ||
                              item.output_path_problem}
                          </span>
                        ) : null}
                      </span>
                    </label>
                  );
                })
              )}
              <button
                type="button"
                className={mmActionButtonClass({ variant: "primary" })}
                onClick={() => void importSelectedLibraries()}
                disabled={
                  selectedDiscoveredKeys.length === 0 ||
                  importDiscovered.isPending
                }
              >
                Import selected
              </button>
            </div>
          ) : null}

          {drift.data ? (
            <div className="space-y-2" aria-label="Library comparison">
              <h4 className="text-sm font-medium text-[var(--mm-text1)]">
                Comparison result
              </h4>
              {drift.data.length === 0 ? (
                <p className="text-sm text-[var(--mm-status-healthy-text)]">
                  No manager/library path differences were found.
                </p>
              ) : (
                drift.data.map((item, index) => (
                  <div
                    key={`${item.kind}-${item.library_id ?? "new"}-${index}`}
                    className="rounded-lg border border-[var(--mm-border)] px-3 py-2"
                  >
                    <p className="text-sm font-medium text-[var(--mm-text1)]">
                      {item.library_name}
                    </p>
                    <p className="text-sm text-[var(--mm-text2)]">
                      {item.detail}
                    </p>
                    {item.manager_value || item.mediamop_value ? (
                      <p className="break-all text-xs text-[var(--mm-text3)]">
                        Manager: {item.manager_value || "Not reported"} ·
                        MediaMop: {item.mediamop_value || "Not configured"}
                      </p>
                    ) : null}
                  </div>
                ))
              )}
            </div>
          ) : null}
        </section>
      ) : null}

      {rows.length === 0 ? (
        <p className="text-sm text-[var(--mm-text3)]">
          No libraries yet. Add one to tell Refiner which folder to watch.
        </p>
      ) : null}

      <ul className="space-y-3">
        {[...rows]
          .sort((a, b) => a.display_order - b.display_order)
          .map((library, index, ordered) => (
            <li
              key={library.id}
              className="rounded border border-[var(--mm-border)] p-3"
              data-testid={`refiner-library-${library.id}`}
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="min-w-0">
                  <p className="truncate font-medium text-[var(--mm-text1)]">
                    {library.name}
                  </p>
                  <p className="text-xs text-[var(--mm-text3)]">
                    {REFINER_MEDIA_SCOPE_LABELS[library.media_scope]} ·{" "}
                    {library.watched_folder || "no watched folder yet"}
                    {library.active_job_count > 0
                      ? ` · ${library.active_job_count} in progress`
                      : ""}
                  </p>
                  {library.discovered_from_connection_id ? (
                    <p className="text-xs text-[var(--mm-text3)]">
                      Linked to{" "}
                      {connections.data?.find(
                        (item) =>
                          item.id === library.discovered_from_connection_id,
                      )?.name ||
                        `manager #${library.discovered_from_connection_id}`}
                    </p>
                  ) : null}
                  <p className="mt-2 flex flex-wrap items-center gap-2 text-xs text-[var(--mm-text2)]">
                    <span
                      className={`rounded-full border px-2 py-0.5 font-medium ${managerCoverageClass(library.manager_coverage)}`}
                    >
                      Manager: {managerCoverageLabel(library.manager_coverage)}
                    </span>
                    <span>{library.manager_coverage_detail}</span>
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <MmOnOffSwitch
                    id={`refiner-library-enabled-${library.id}`}
                    label={`${library.name} enabled`}
                    enabled={library.enabled}
                    disabled={!editable}
                    onChange={() => void toggleEnabled(library)}
                  />
                  <button
                    type="button"
                    className={mmActionButtonClass({
                      variant: "tertiary",
                      disabled: !editable || index === 0,
                    })}
                    onClick={() => void move(library, -1)}
                    disabled={!editable || index === 0}
                    aria-label={`Move ${library.name} up`}
                  >
                    ↑
                  </button>
                  <button
                    type="button"
                    className={mmActionButtonClass({
                      variant: "tertiary",
                      disabled: !editable || index === ordered.length - 1,
                    })}
                    onClick={() => void move(library, 1)}
                    disabled={!editable || index === ordered.length - 1}
                    aria-label={`Move ${library.name} down`}
                  >
                    ↓
                  </button>
                  <button
                    type="button"
                    className={mmActionButtonClass({
                      variant: "secondary",
                      disabled: !editable,
                    })}
                    onClick={() => startEdit(library)}
                    disabled={!editable}
                  >
                    Edit
                  </button>
                  {library.discovered_from_connection_id ? (
                    <button
                      type="button"
                      className={mmActionButtonClass({ variant: "secondary" })}
                      onClick={() => void unlink(library)}
                      disabled={unlinkDiscovered.isPending}
                    >
                      Unlink
                    </button>
                  ) : null}
                  <button
                    type="button"
                    className={mmActionButtonClass({
                      variant: "tertiary",
                      disabled: !editable,
                    })}
                    onClick={() => void removeLibrary(library)}
                    disabled={!editable}
                    data-testid={`refiner-library-remove-${library.id}`}
                  >
                    Remove
                  </button>
                </div>
              </div>
            </li>
          ))}
      </ul>

      {adding || editingId !== null ? (
        <div
          className="space-y-3 rounded border border-[var(--mm-border)] p-3"
          data-testid="refiner-library-form"
        >
          <h3 className="text-sm font-medium text-[var(--mm-text1)]">
            {editingId !== null ? "Edit library" : "Add library"}
          </h3>
          <section className="space-y-3 rounded-xl border border-[var(--mm-border)] bg-[var(--mm-card-bg)] p-4">
            <div>
              <h4 className="font-medium text-[var(--mm-text1)]">
                Identity and folders
              </h4>
              <p className="text-xs text-[var(--mm-text3)]">
                One watched folder, one safe work area, and one finished output.
              </p>
            </div>
            <div className="grid gap-3 lg:grid-cols-2">
              {field("Name", "name", "Movies 4K")}
              <label className="block text-sm">
                <span className="text-[var(--mm-text2)]">Kind of media</span>
                <select
                  className={mmSelectFieldClass}
                  value={form.media_scope}
                  onChange={(event) =>
                    setForm({
                      ...form,
                      media_scope: event.target.value as RefinerMediaScope,
                    })
                  }
                  disabled={!editable}
                >
                  {SCOPES.map((scope) => (
                    <option key={scope} value={scope}>
                      {REFINER_MEDIA_SCOPE_LABELS[scope]}
                    </option>
                  ))}
                </select>
              </label>
              <label className="block text-sm">
                <span className="text-[var(--mm-text2)]">
                  Audio, subtitle and metadata rules
                </span>
                <select
                  className={mmSelectFieldClass}
                  value={form.rule_set_id}
                  onChange={(event) =>
                    setForm({ ...form, rule_set_id: event.target.value })
                  }
                  disabled={!editable}
                >
                  <option value="">Use scope defaults</option>
                  {(ruleSets.data ?? []).map((ruleSet) => (
                    <option key={ruleSet.id} value={ruleSet.id}>
                      {ruleSet.name}
                    </option>
                  ))}
                </select>
                <span className="mt-1 block text-xs text-[var(--mm-text3)]">
                  Create and edit reusable rule sets under Audio & subtitles.
                </span>
              </label>
              {field(
                "Watched folder",
                "watched_folder",
                "/srv/media/movies-4k",
              )}
              {field(
                "Output folder",
                "output_folder",
                "/srv/media/movies-4k-out",
              )}
              {field(
                "Work folder",
                "work_folder",
                "",
                "Leave empty to use MediaMop's private temporary folder.",
              )}
            </div>
          </section>

          <section className="space-y-3 rounded-xl border border-[var(--mm-border)] bg-[var(--mm-card-bg)] p-4">
            <div>
              <h4 className="font-medium text-[var(--mm-text1)]">
                Intake rules
              </h4>
              <p className="text-xs text-[var(--mm-text3)]">
                Decide which files belong here before Refiner spends time
                probing or processing them. A maximum of 0 means no limit.
              </p>
            </div>
            <div className="grid gap-3 lg:grid-cols-2">
              {field("File types", "media_extensions_csv", ".mkv,.mp4")}
              {field(
                "Downloader folders to ignore",
                "exclude_markers_csv",
                "__admin__,incomplete",
                "Comma-separated folder names used while a download is incomplete.",
              )}
              {field(
                "Path must match",
                "include_patterns_csv",
                "*feature*,Movies/*",
                "Optional comma-separated wildcards. Empty accepts every path.",
              )}
              {field(
                "Path must not match",
                "exclude_patterns_csv",
                "*sample*,*trailer*",
                "Optional comma-separated wildcards.",
              )}
              {field("Minimum file size (MB)", "min_file_size_mb", "0")}
              {field("Maximum file size (MB)", "max_file_size_mb", "0")}
              <div className="space-y-2 rounded-lg border border-[var(--mm-border)] p-3 lg:col-span-2">
                <div>
                  <p className="text-sm font-medium text-[var(--mm-text1)]">
                    Created and modified windows
                  </p>
                  <p className="text-xs leading-5 text-[var(--mm-text3)]">
                    Optional. Leave a side blank for no limit. Times are shown
                    in this browser&apos;s timezone and saved as UTC. Windows
                    uses the file creation time; Linux and Docker use the best
                    filesystem birth/change time available.
                  </p>
                </div>
                <div className="grid gap-3 sm:grid-cols-2">
                  {dateTimeField("Created after", "created_after")}
                  {dateTimeField("Created before", "created_before")}
                  {dateTimeField("Modified after", "modified_after")}
                  {dateTimeField("Modified before", "modified_before")}
                </div>
              </div>
              <label className="block text-sm">
                <span className="text-[var(--mm-text2)]">
                  When a file is rejected
                </span>
                <select
                  className={mmSelectFieldClass}
                  value={form.rejected_file_action}
                  onChange={(event) =>
                    setForm({
                      ...form,
                      rejected_file_action: event.target.value as
                        | "leave"
                        | "delete_file",
                    })
                  }
                  disabled={!editable}
                >
                  <option value="leave">Leave the file in place</option>
                  <option value="delete_file">
                    Delete only the rejected file
                  </option>
                </select>
                <span className="mt-1 block text-xs text-[var(--mm-text3)]">
                  Applies after readiness checks to size and path-rule
                  rejections. MediaMop never deletes a populated parent folder
                  here.
                </span>
              </label>
            </div>
            <div className="grid gap-2 lg:grid-cols-2">
              {toggle("Skip hidden files", "exclude_hidden")}
              {toggle("Only inspect the top folder", "top_level_only")}
            </div>
          </section>

          <section className="space-y-3 rounded-xl border border-[var(--mm-border)] bg-[var(--mm-card-bg)] p-4">
            <div>
              <h4 className="font-medium text-[var(--mm-text1)]">
                File readiness
              </h4>
              <p className="text-xs text-[var(--mm-text3)]">
                These checks prevent MediaMop from starting while a downloader,
                recorder, or media manager still owns the file.
              </p>
            </div>
            <div className="grid gap-3 lg:grid-cols-2">
              {field("Minimum unchanged age (seconds)", "min_file_age_seconds")}
              {field("Hold every new file (minutes)", "hold_minutes")}
              {field(
                "Size must stay stable (seconds)",
                "file_detection_interval_seconds",
              )}
              {field(
                "Fallback scan interval (seconds)",
                "scan_interval_seconds",
              )}
            </div>
            <div className="grid gap-2 lg:grid-cols-2">
              {toggle(
                "Watch this folder for changes",
                "file_system_events_enabled",
                "The periodic scan remains as a backstop for Docker, SMB, and NFS.",
              )}
              {toggle(
                "Ignore size changes",
                "ignore_size_changes",
                "Use only when another system guarantees the file is complete.",
              )}
              {toggle(
                "Skip read and write tests",
                "skip_access_tests",
                "Less safe: locked sources and unwritable outputs may fail after queueing.",
              )}
            </div>
          </section>

          <section className="space-y-3 rounded-xl border border-[var(--mm-border)] bg-[var(--mm-card-bg)] p-4">
            <div>
              <h4 className="font-medium text-[var(--mm-text1)]">
                Output safety
              </h4>
              <p className="text-xs text-[var(--mm-text3)]">
                Control sidecars, timestamps, and what happens when the
                destination already exists.
              </p>
            </div>
            <div className="grid gap-3 lg:grid-cols-2">
              {field(
                "Sidecar file types",
                "sidecar_patterns_csv",
                ".srt,.nfo,.jpg",
              )}
              <label className="block text-sm">
                <span className="text-[var(--mm-text2)]">Existing output</span>
                <select
                  className={mmSelectFieldClass}
                  value={form.output_collision_policy}
                  onChange={(event) =>
                    setForm({
                      ...form,
                      output_collision_policy: event.target.value,
                    })
                  }
                  disabled={!editable}
                >
                  <option value="replace">Replace it</option>
                  <option value="skip">Keep it and skip this file</option>
                  <option value="keep_both">Keep both</option>
                  <option value="replace_if_larger">
                    Replace only if new output is larger
                  </option>
                  <option value="replace_if_newer">
                    Replace only if source is newer
                  </option>
                </select>
              </label>
            </div>
            <div className="grid gap-2 lg:grid-cols-2">
              {toggle(
                "Preserve original timestamps",
                "preserve_original_timestamps",
              )}
            </div>
          </section>

          <section className="space-y-3 rounded-xl border border-[var(--mm-border)] bg-[var(--mm-card-bg)] p-4">
            <div>
              <h4 className="font-medium text-[var(--mm-text1)]">
                Capacity and recovery
              </h4>
              <p className="text-xs text-[var(--mm-text3)]">
                Priority is relative: higher-numbered libraries are offered work
                first.
              </p>
            </div>
            <div className="grid gap-3 lg:grid-cols-2">
              {field("Files at once", "max_concurrent_files", "1")}
              {field("Queue priority", "priority", "0")}
              {field("Maximum automatic attempts", "max_attempts", "3")}
              {field(
                "First retry delay (seconds)",
                "retry_backoff_seconds",
                "300",
              )}
            </div>
            <div className="grid gap-2 lg:grid-cols-2">
              {toggle("Retry processing failures", "retry_execution_failures")}
              {toggle(
                "Retry preflight rejections",
                "retry_preflight_failures",
                "Usually leave this off: retrying does not repair an unsupported or malformed file.",
              )}
            </div>
          </section>

          <details className="rounded-xl border border-[var(--mm-border)] bg-[var(--mm-card-bg)] p-4">
            <summary className="cursor-pointer font-medium text-[var(--mm-text1)]">
              Hardware and compatibility
            </summary>
            <p className="mt-1 text-xs text-[var(--mm-text3)]">
              Software processing is the safest default. Hardware failures fall
              back to software and are recorded.
            </p>
            <div className="mt-3 grid gap-3 lg:grid-cols-2">
              <label className="block text-sm">
                <span className="text-[var(--mm-text2)]">
                  Hardware decoding
                </span>
                <select
                  className={mmSelectFieldClass}
                  value={form.hardware_decode_mode}
                  onChange={(event) =>
                    setForm({
                      ...form,
                      hardware_decode_mode: event.target.value,
                    })
                  }
                  disabled={!editable}
                >
                  <option value="off">Off</option>
                  <option value="auto">Detect automatically</option>
                  <option value="device">Use a specific method</option>
                </select>
              </label>
              {field("Hardware method", "hardware_device", "cuda, qsv, vaapi")}
              {field(
                "Never use these vendors",
                "hardware_disabled_vendors_csv",
                "nvidia,intel",
              )}
              <label className="block text-sm">
                <span className="text-[var(--mm-text2)]">
                  FFmpeg compatibility
                </span>
                <select
                  className={mmSelectFieldClass}
                  value={form.ffmpeg_strictness}
                  onChange={(event) =>
                    setForm({ ...form, ffmpeg_strictness: event.target.value })
                  }
                  disabled={!editable}
                >
                  <option value="very">Very strict</option>
                  <option value="strict">Strict</option>
                  <option value="normal">Normal</option>
                  <option value="unofficial">Allow unofficial</option>
                  <option value="experimental">Allow experimental</option>
                </select>
              </label>
            </div>
          </details>
          <div className="space-y-2">
            <span className="text-sm font-medium text-[var(--mm-text1)]">
              When this library may run
            </span>
            <ScheduleGridEditor
              value={form.schedule_grid}
              onChange={(schedule_grid) => setForm({ ...form, schedule_grid })}
              disabled={!editable}
            />
          </div>
          <div className="flex gap-2">
            <button
              type="button"
              className={mmActionButtonClass({
                variant: "primary",
                disabled: !editable || !form.name.trim(),
              })}
              onClick={() => void save()}
              disabled={!editable || !form.name.trim()}
              data-testid="refiner-library-save"
            >
              Save
            </button>
            <button
              type="button"
              className={mmActionButtonClass({ variant: "tertiary" })}
              onClick={cancel}
            >
              Cancel
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
