import { useState } from "react";

import { MmOnOffSwitch } from "../../components/ui/mm-on-off-switch";
import { PageLoading } from "../../components/shared/page-loading";
import { useMeQuery } from "../../lib/auth/queries";
import {
  REFINER_MEDIA_SCOPE_LABELS,
  type RefinerLibrary,
  type RefinerLibraryWrite,
  type RefinerMediaScope,
} from "../../lib/refiner/libraries-api";
import {
  useCreateRefinerLibrary,
  useDeleteRefinerLibrary,
  useRefinerLibrariesQuery,
  useReorderRefinerLibraries,
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
  min_file_size_mb: string;
  min_file_age_seconds: string;
  scan_interval_seconds: string;
  hold_minutes: string;
  file_detection_interval_seconds: string;
  max_concurrent_files: string;
  exclude_hidden: boolean;
  top_level_only: boolean;
  ignore_size_changes: boolean;
  skip_access_tests: boolean;
  file_system_events_enabled: boolean;
};

const EMPTY_FORM: FormState = {
  name: "",
  media_scope: "movie",
  watched_folder: "",
  work_folder: "",
  output_folder: "",
  media_extensions_csv: ".mkv,.mp4,.m4v,.webm,.avi",
  exclude_markers_csv: "",
  min_file_size_mb: "0",
  min_file_age_seconds: "60",
  scan_interval_seconds: "300",
  hold_minutes: "0",
  file_detection_interval_seconds: "30",
  max_concurrent_files: "1",
  exclude_hidden: true,
  top_level_only: false,
  ignore_size_changes: false,
  skip_access_tests: false,
  file_system_events_enabled: true,
};

function formFrom(library: RefinerLibrary): FormState {
  return {
    name: library.name,
    media_scope: library.media_scope,
    watched_folder: library.watched_folder,
    work_folder: library.work_folder,
    output_folder: library.output_folder,
    media_extensions_csv: library.media_extensions_csv,
    exclude_markers_csv: library.exclude_markers_csv,
    min_file_size_mb: String(library.min_file_size_mb),
    min_file_age_seconds: String(library.min_file_age_seconds),
    scan_interval_seconds: String(library.scan_interval_seconds),
    hold_minutes: String(library.hold_minutes),
    file_detection_interval_seconds: String(
      library.file_detection_interval_seconds,
    ),
    max_concurrent_files: String(library.max_concurrent_files),
    exclude_hidden: library.exclude_hidden,
    top_level_only: library.top_level_only,
    ignore_size_changes: library.ignore_size_changes,
    skip_access_tests: library.skip_access_tests,
    file_system_events_enabled: library.file_system_events_enabled,
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
    min_file_size_mb: asNumber(form.min_file_size_mb, 0),
    min_file_age_seconds: asNumber(form.min_file_age_seconds, 60),
    scan_interval_seconds: asNumber(form.scan_interval_seconds, 300),
    hold_minutes: asNumber(form.hold_minutes, 0),
    file_detection_interval_seconds: asNumber(
      form.file_detection_interval_seconds,
      30,
    ),
    max_concurrent_files: asNumber(form.max_concurrent_files, 1),
    exclude_hidden: form.exclude_hidden,
    top_level_only: form.top_level_only,
    ignore_size_changes: form.ignore_size_changes,
    skip_access_tests: form.skip_access_tests,
    file_system_events_enabled: form.file_system_events_enabled,
    rule_set_id: library?.rule_set_id ?? null,
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

/**
 * Refiner libraries: add, edit, reorder, enable, remove.
 *
 * Replaces the fixed Movies/TV path form. A library is a row now, so a fourth one is
 * an ordinary thing to have rather than a schema change (ADR-0014).
 */
export function RefinerLibrariesSection() {
  const me = useMeQuery();
  const libraries = useRefinerLibrariesQuery();
  const create = useCreateRefinerLibrary();
  const update = useUpdateRefinerLibrary();
  const remove = useDeleteRefinerLibrary();
  const reorder = useReorderRefinerLibraries();

  const [adding, setAdding] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [notice, setNotice] = useState<string | null>(null);

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
          <div className="grid gap-3 sm:grid-cols-2">
            {field("Name", "name", "Movies 4K")}
            <label className="block text-sm">
              <span className="text-[var(--mm-text2)]">Kind of media</span>
              <select
                className={mmSelectFieldClass}
                value={form.media_scope}
                onChange={(e) =>
                  setForm({
                    ...form,
                    media_scope: e.target.value as RefinerMediaScope,
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
            {field("Watched folder", "watched_folder", "/srv/media/movies-4k")}
            {field(
              "Output folder",
              "output_folder",
              "/srv/media/movies-4k-out",
            )}
            {field(
              "Work folder",
              "work_folder",
              "",
              "Leave empty to use MediaMop's own temporary folder.",
            )}
            {field(
              "File types",
              "media_extensions_csv",
              ".mkv,.mp4",
              "Anything else in this folder is ignored, and the scan says how many.",
            )}
            {field(
              "Ignore folders containing",
              "exclude_markers_csv",
              "__admin__,incomplete",
              "Downloader staging folders. Comma separated.",
            )}
            {field("Smallest file to process (MB)", "min_file_size_mb")}
            {field(
              "Leave files alone for (seconds)",
              "min_file_age_seconds",
              "",
              "How long a file must sit unchanged before Refiner touches it.",
            )}
            {field(
              "Check this folder every (seconds)",
              "scan_interval_seconds",
            )}
            {field(
              "Park new files for (minutes)",
              "hold_minutes",
              "",
              "A deliberate settling delay. Held files stay visible with the time they are due.",
            )}
            {field(
              "Watch the file size for (seconds)",
              "file_detection_interval_seconds",
              "",
              "How long the size must stay the same before MediaMop treats the file as finished being written. 0 turns this off.",
            )}
            {field("Files at once", "max_concurrent_files")}
          </div>
          <div className="flex flex-wrap gap-4">
            <label className="flex items-center gap-2 text-sm text-[var(--mm-text2)]">
              <input
                type="checkbox"
                checked={form.exclude_hidden}
                onChange={(e) =>
                  setForm({ ...form, exclude_hidden: e.target.checked })
                }
                disabled={!editable}
              />
              Skip hidden files
            </label>
            <label className="flex items-center gap-2 text-sm text-[var(--mm-text2)]">
              <input
                type="checkbox"
                checked={form.top_level_only}
                onChange={(e) =>
                  setForm({ ...form, top_level_only: e.target.checked })
                }
                disabled={!editable}
              />
              Only look in the top folder
            </label>
            <label className="flex items-center gap-2 text-sm text-[var(--mm-text2)]">
              <input
                type="checkbox"
                checked={form.ignore_size_changes}
                onChange={(e) =>
                  setForm({ ...form, ignore_size_changes: e.target.checked })
                }
                disabled={!editable}
              />
              Do not watch the file size
            </label>
            <label className="flex items-center gap-2 text-sm text-[var(--mm-text2)]">
              <input
                type="checkbox"
                checked={form.skip_access_tests}
                onChange={(e) =>
                  setForm({ ...form, skip_access_tests: e.target.checked })
                }
                disabled={!editable}
              />
              Skip the read and write check
            </label>
            <label className="flex items-center gap-2 text-sm text-[var(--mm-text2)]">
              <input
                type="checkbox"
                checked={form.file_system_events_enabled}
                onChange={(e) =>
                  setForm({
                    ...form,
                    file_system_events_enabled: e.target.checked,
                  })
                }
                disabled={!editable}
              />
              Watch this folder for changes
            </label>
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
