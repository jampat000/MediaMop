import { useEffect, useMemo, useState } from "react";

import { PageLoading } from "../../components/shared/page-loading";
import { useMeQuery } from "../../lib/auth/queries";
import {
  type RefinerRuleSetWrite,
  writeFromRefinerRuleSet,
} from "../../lib/refiner/libraries-api";
import {
  useCreateRefinerRuleSet,
  useDeleteRefinerRuleSet,
  useRefinerRuleSetsQuery,
  useUpdateRefinerRuleSet,
} from "../../lib/refiner/libraries-queries";
import {
  useRefinerMetadataProviderQuery,
  useSaveRefinerMetadataProvider,
  useTestRefinerMetadataProvider,
} from "../../lib/refiner/metadata-provider-queries";
import {
  mmActionButtonClass,
  mmEditableTextFieldClass,
  mmSelectFieldClass,
} from "../../lib/ui/mm-control-roles";

type TrackSorter = {
  field: string;
  value: string;
  reversed: boolean;
};

const SORTER_FIELDS = [
  "language",
  "channels",
  "codec",
  "bitrate",
  "title",
  "default",
  "forced",
  "commentary",
];

const DEFAULT_AUDIO_SORTERS: TrackSorter[] = [
  { field: "commentary", value: "", reversed: false },
  { field: "channels", value: "", reversed: false },
  { field: "codec", value: "", reversed: false },
  { field: "bitrate", value: "", reversed: false },
  { field: "default", value: "", reversed: false },
];

const DEFAULT_SUBTITLE_SORTERS: TrackSorter[] = [
  { field: "forced", value: "", reversed: false },
  { field: "default", value: "", reversed: false },
  { field: "language", value: "", reversed: false },
];

const EMPTY_RULE_SET: RefinerRuleSetWrite = {
  name: "",
  primary_audio_lang: "eng",
  secondary_audio_lang: "",
  tertiary_audio_lang: "",
  default_audio_slot: "primary",
  remove_commentary: true,
  subtitle_mode: "keep_all",
  subtitle_langs_csv: "",
  preserve_forced_subs: true,
  preserve_default_subs: true,
  audio_preference_mode: "preferred_langs_quality",
  audio_sorters_json: JSON.stringify(DEFAULT_AUDIO_SORTERS),
  subtitle_sorters_json: JSON.stringify(DEFAULT_SUBTITLE_SORTERS),
  keep_original_language: false,
  original_language_additional_csv: "",
  original_language_keep_only_first: true,
  original_language_first_if_none: true,
  original_language_treat_empty_as_original: false,
  remove_images: false,
  remove_attachments: false,
  remove_title: false,
  remove_language_tags: false,
  remove_other_metadata: false,
};

function canEdit(role: string | undefined): boolean {
  return role === "operator" || role === "admin";
}

function parseSorters(raw: string, fallback: TrackSorter[]): TrackSorter[] {
  try {
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) return fallback.map((item) => ({ ...item }));
    const rows = parsed
      .filter(
        (item): item is Record<string, unknown> =>
          Boolean(item) && typeof item === "object",
      )
      .map((item) => ({
        field: String(item.field ?? "language"),
        value: typeof item.value === "string" ? item.value : "",
        reversed: Boolean(item.reversed),
      }))
      .filter((item) => SORTER_FIELDS.includes(item.field));
    return rows.length > 0 ? rows : fallback.map((item) => ({ ...item }));
  } catch {
    return fallback.map((item) => ({ ...item }));
  }
}

function dumpSorters(rows: TrackSorter[]): string {
  return JSON.stringify(
    rows.map((row) => ({
      field: row.field,
      value: row.value.trim() || null,
      reversed: row.reversed,
    })),
  );
}

function errorText(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

function SorterEditor({
  title,
  detail,
  rows,
  disabled,
  onChange,
}: {
  title: string;
  detail: string;
  rows: TrackSorter[];
  disabled: boolean;
  onChange: (rows: TrackSorter[]) => void;
}) {
  const update = (index: number, value: TrackSorter) =>
    onChange(rows.map((row, rowIndex) => (rowIndex === index ? value : row)));
  const move = (index: number, offset: number) => {
    const nextIndex = index + offset;
    if (nextIndex < 0 || nextIndex >= rows.length) return;
    const next = [...rows];
    [next[index], next[nextIndex]] = [next[nextIndex], next[index]];
    onChange(next);
  };

  return (
    <section className="space-y-3 rounded-xl border border-[var(--mm-border)] bg-[var(--mm-surface2)] p-4">
      <div>
        <h4 className="font-medium text-[var(--mm-text1)]">{title}</h4>
        <p className="mt-1 text-xs leading-5 text-[var(--mm-text3)]">
          {detail}
        </p>
      </div>
      <ol className="space-y-2">
        {rows.map((row, index) => (
          <li
            key={`${row.field}-${index}`}
            className="grid gap-2 rounded-lg border border-[var(--mm-border)] p-3 md:grid-cols-[2rem_1fr_1.4fr_auto]"
          >
            <span className="pt-2 text-center text-xs font-semibold text-[var(--mm-text3)]">
              {index + 1}
            </span>
            <label className="text-xs text-[var(--mm-text3)]">
              Criterion
              <select
                className={mmSelectFieldClass}
                value={row.field}
                disabled={disabled}
                onChange={(event) =>
                  update(index, { ...row, field: event.target.value })
                }
              >
                {SORTER_FIELDS.map((field) => (
                  <option key={field} value={field}>
                    {field}
                  </option>
                ))}
              </select>
            </label>
            <label className="text-xs text-[var(--mm-text3)]">
              Match value (optional)
              <input
                className={mmEditableTextFieldClass}
                value={row.value}
                placeholder="eng, >=5.1, dts, commentary…"
                disabled={disabled}
                onChange={(event) =>
                  update(index, { ...row, value: event.target.value })
                }
              />
            </label>
            <div className="flex flex-wrap items-end gap-1">
              <label className="inline-flex min-h-9 items-center gap-1 px-1 text-xs text-[var(--mm-text2)]">
                <input
                  type="checkbox"
                  checked={row.reversed}
                  disabled={disabled}
                  onChange={(event) =>
                    update(index, { ...row, reversed: event.target.checked })
                  }
                />
                Reverse
              </label>
              <button
                type="button"
                className={mmActionButtonClass({
                  variant: "tertiary",
                  disabled: disabled || index === 0,
                })}
                disabled={disabled || index === 0}
                onClick={() => move(index, -1)}
                aria-label={`Move ${title} criterion ${index + 1} up`}
              >
                ↑
              </button>
              <button
                type="button"
                className={mmActionButtonClass({
                  variant: "tertiary",
                  disabled: disabled || index === rows.length - 1,
                })}
                disabled={disabled || index === rows.length - 1}
                onClick={() => move(index, 1)}
                aria-label={`Move ${title} criterion ${index + 1} down`}
              >
                ↓
              </button>
              <button
                type="button"
                className={mmActionButtonClass({
                  variant: "tertiary",
                  disabled,
                })}
                disabled={disabled}
                onClick={() =>
                  onChange(rows.filter((_, rowIndex) => rowIndex !== index))
                }
              >
                Remove
              </button>
            </div>
          </li>
        ))}
      </ol>
      <button
        type="button"
        className={mmActionButtonClass({ variant: "secondary", disabled })}
        disabled={disabled}
        onClick={() =>
          onChange([...rows, { field: "language", value: "", reversed: false }])
        }
      >
        Add criterion
      </button>
    </section>
  );
}

export function RefinerRuleSetWorkspace() {
  const me = useMeQuery();
  const ruleSets = useRefinerRuleSetsQuery();
  const createRuleSet = useCreateRefinerRuleSet();
  const updateRuleSet = useUpdateRefinerRuleSet();
  const deleteRuleSet = useDeleteRefinerRuleSet();
  const provider = useRefinerMetadataProviderQuery();
  const saveProvider = useSaveRefinerMetadataProvider();
  const testProvider = useTestRefinerMetadataProvider();
  const editable = canEdit(me.data?.role);

  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [creating, setCreating] = useState(false);
  const [draft, setDraft] = useState<RefinerRuleSetWrite | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [providerName, setProviderName] = useState<"" | "tmdb">("");
  const [providerBaseUrl, setProviderBaseUrl] = useState("");
  const [providerKey, setProviderKey] = useState("");
  const [clearProviderKey, setClearProviderKey] = useState(false);
  const [providerNotice, setProviderNotice] = useState<string | null>(null);

  useEffect(() => {
    if (creating || !ruleSets.data) return;
    const selected =
      ruleSets.data.find((row) => row.id === selectedId) ?? ruleSets.data[0];
    if (!selected) {
      setSelectedId(null);
      setDraft(null);
      return;
    }
    if (selected.id !== selectedId || draft === null) {
      setSelectedId(selected.id);
      setDraft(writeFromRefinerRuleSet(selected));
    }
  }, [creating, draft, ruleSets.data, selectedId]);

  useEffect(() => {
    if (!provider.data) return;
    setProviderName(provider.data.provider === "tmdb" ? "tmdb" : "");
    setProviderBaseUrl(provider.data.base_url);
    setProviderKey("");
    setClearProviderKey(false);
  }, [provider.data]);

  const selectedRuleSet = ruleSets.data?.find((row) => row.id === selectedId);
  const audioSorters = useMemo(
    () => parseSorters(draft?.audio_sorters_json ?? "", DEFAULT_AUDIO_SORTERS),
    [draft?.audio_sorters_json],
  );
  const subtitleSorters = useMemo(
    () =>
      parseSorters(
        draft?.subtitle_sorters_json ?? "",
        DEFAULT_SUBTITLE_SORTERS,
      ),
    [draft?.subtitle_sorters_json],
  );

  if (ruleSets.isLoading || provider.isLoading || me.isPending) {
    return <PageLoading label="Loading Refiner rule sets" />;
  }

  const disabled =
    !editable || createRuleSet.isPending || updateRuleSet.isPending;
  const change = <Key extends keyof RefinerRuleSetWrite>(
    key: Key,
    value: RefinerRuleSetWrite[Key],
  ) =>
    setDraft((current) => (current ? { ...current, [key]: value } : current));

  const saveRuleSet = async () => {
    if (!draft || !draft.name.trim()) {
      setNotice("Give this rule set a name before saving it.");
      return;
    }
    setNotice(null);
    try {
      const saved = creating
        ? await createRuleSet.mutateAsync({ ...draft, name: draft.name.trim() })
        : await updateRuleSet.mutateAsync({
            id: selectedId as number,
            data: { ...draft, name: draft.name.trim() },
          });
      setCreating(false);
      setSelectedId(saved.id);
      setDraft(writeFromRefinerRuleSet(saved));
      setNotice(`${saved.name} was saved.`);
    } catch (error) {
      setNotice(errorText(error, "That rule set could not be saved."));
    }
  };

  const removeRuleSet = async () => {
    if (!selectedRuleSet || selectedRuleSet.used_by_library_count > 0) return;
    if (!window.confirm(`Remove the rule set “${selectedRuleSet.name}”?`))
      return;
    try {
      await deleteRuleSet.mutateAsync(selectedRuleSet.id);
      setSelectedId(null);
      setDraft(null);
      setNotice(`${selectedRuleSet.name} was removed.`);
    } catch (error) {
      setNotice(errorText(error, "That rule set could not be removed."));
    }
  };

  const providerBody = () => ({
    provider: providerName,
    base_url: providerBaseUrl.trim(),
    ...(clearProviderKey
      ? { api_key: "" }
      : providerKey.trim()
        ? { api_key: providerKey.trim() }
        : {}),
  });

  const saveProviderConnection = async () => {
    setProviderNotice(null);
    try {
      const saved = await saveProvider.mutateAsync(providerBody());
      setProviderKey("");
      setClearProviderKey(false);
      setProviderNotice(
        saved.provider
          ? "Metadata provider saved. Test it before relying on original-language matching."
          : "Metadata provider cleared. Original-language rules will fall back to the saved audio preferences.",
      );
    } catch (error) {
      setProviderNotice(
        errorText(error, "The metadata provider could not be saved."),
      );
    }
  };

  const testProviderConnection = async () => {
    setProviderNotice(null);
    try {
      await saveProvider.mutateAsync(providerBody());
      const result = await testProvider.mutateAsync(providerBody());
      setProviderNotice(result.detail);
    } catch (error) {
      setProviderNotice(errorText(error, "The metadata provider test failed."));
    }
  };

  const textField = (
    label: string,
    key: keyof RefinerRuleSetWrite,
    placeholder = "",
  ) => (
    <label className="block text-sm">
      <span className="text-[var(--mm-text2)]">{label}</span>
      <input
        className={mmEditableTextFieldClass}
        value={String(draft?.[key] ?? "")}
        placeholder={placeholder}
        disabled={disabled}
        onChange={(event) => change(key, event.target.value as never)}
      />
    </label>
  );

  const toggle = (
    label: string,
    detail: string,
    key: keyof RefinerRuleSetWrite,
  ) => (
    <label className="flex items-start gap-3 rounded-lg border border-[var(--mm-border)] px-3 py-2 text-sm">
      <input
        type="checkbox"
        className="mt-1"
        checked={Boolean(draft?.[key])}
        disabled={disabled}
        onChange={(event) => change(key, event.target.checked as never)}
      />
      <span>
        <span className="block font-medium text-[var(--mm-text1)]">
          {label}
        </span>
        <span className="mt-0.5 block text-xs leading-5 text-[var(--mm-text3)]">
          {detail}
        </span>
      </span>
    </label>
  );

  return (
    <div className="space-y-5" data-testid="refiner-rule-set-workspace">
      <section className="mm-module-surface rounded-xl border border-[var(--mm-border)] bg-[var(--mm-card-bg)] p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="mm-page__eyebrow">Reusable processing profiles</p>
            <h2 className="mt-1 text-xl font-semibold text-[var(--mm-text1)]">
              Rule sets
            </h2>
            <p className="mt-1 max-w-3xl text-sm leading-6 text-[var(--mm-text2)]">
              Build one ordered audio, subtitle and metadata policy, then attach
              it to any number of libraries. Edit a library under Libraries to
              choose its rule set.
            </p>
          </div>
          <button
            type="button"
            className={mmActionButtonClass({
              variant: "primary",
              disabled: !editable,
            })}
            disabled={!editable}
            onClick={() => {
              setCreating(true);
              setSelectedId(null);
              setDraft({ ...EMPTY_RULE_SET });
              setNotice(null);
            }}
          >
            New rule set
          </button>
        </div>

        {(ruleSets.data?.length ?? 0) > 0 && !creating ? (
          <label className="mt-4 block max-w-xl text-sm">
            <span className="text-[var(--mm-text2)]">Rule set to edit</span>
            <select
              className={mmSelectFieldClass}
              value={selectedId ?? ""}
              onChange={(event) => {
                const id = Number(event.target.value);
                const selected = ruleSets.data?.find((row) => row.id === id);
                setSelectedId(id);
                setDraft(selected ? writeFromRefinerRuleSet(selected) : null);
                setNotice(null);
              }}
            >
              {(ruleSets.data ?? []).map((row) => (
                <option key={row.id} value={row.id}>
                  {row.name} · used by {row.used_by_library_count}{" "}
                  {row.used_by_library_count === 1 ? "library" : "libraries"}
                </option>
              ))}
            </select>
          </label>
        ) : null}

        {!draft ? (
          <p className="mt-4 text-sm text-[var(--mm-text3)]">
            No rule sets exist yet. Create one, then attach it to a library.
          </p>
        ) : (
          <div className="mt-5 space-y-4">
            <section className="grid gap-3 rounded-xl border border-[var(--mm-border)] bg-[var(--mm-surface2)] p-4 md:grid-cols-2">
              {textField("Rule-set name", "name", "English feature films")}
              <label className="block text-sm">
                <span className="text-[var(--mm-text2)]">
                  Audio policy preset
                </span>
                <select
                  className={mmSelectFieldClass}
                  value={draft.audio_preference_mode}
                  disabled={disabled}
                  onChange={(event) => {
                    const mode = event.target.value;
                    change("audio_preference_mode", mode);
                    change(
                      "audio_sorters_json",
                      dumpSorters(
                        mode === "quality_all_languages"
                          ? DEFAULT_AUDIO_SORTERS.filter(
                              (row) => row.field !== "default",
                            )
                          : DEFAULT_AUDIO_SORTERS,
                      ),
                    );
                  }}
                >
                  <option value="preferred_langs_quality">
                    Languages first, then quality
                  </option>
                  <option value="preferred_langs_strict">
                    Only preferred languages
                  </option>
                  <option value="quality_all_languages">
                    Best quality in any language
                  </option>
                </select>
              </label>
              {textField("Primary audio language", "primary_audio_lang", "eng")}
              {textField(
                "Secondary audio language",
                "secondary_audio_lang",
                "jpn",
              )}
              {textField(
                "Tertiary audio language",
                "tertiary_audio_lang",
                "fre",
              )}
              <label className="block text-sm">
                <span className="text-[var(--mm-text2)]">
                  Default audio slot
                </span>
                <select
                  className={mmSelectFieldClass}
                  value={draft.default_audio_slot}
                  disabled={disabled}
                  onChange={(event) =>
                    change("default_audio_slot", event.target.value)
                  }
                >
                  <option value="primary">Primary</option>
                  <option value="secondary">Secondary</option>
                  <option value="tertiary">Tertiary</option>
                </select>
              </label>
              <div className="md:col-span-2">
                {toggle(
                  "Remove commentary tracks",
                  "Commentary is excluded before ranking the remaining audio.",
                  "remove_commentary",
                )}
              </div>
            </section>

            <SorterEditor
              title="Audio order"
              detail="Top criteria decide first. A match value promotes a specific language, codec or expression such as >=5.1; Reverse flips that criterion."
              rows={audioSorters}
              disabled={disabled}
              onChange={(rows) =>
                change("audio_sorters_json", dumpSorters(rows))
              }
            />

            <section className="space-y-3 rounded-xl border border-[var(--mm-border)] bg-[var(--mm-surface2)] p-4">
              <div>
                <h4 className="font-medium text-[var(--mm-text1)]">
                  Subtitles
                </h4>
                <p className="mt-1 text-xs text-[var(--mm-text3)]">
                  Keep everything, keep a language list, or remove all subtitle
                  streams.
                </p>
              </div>
              <div className="grid gap-3 md:grid-cols-2">
                <label className="block text-sm">
                  <span className="text-[var(--mm-text2)]">
                    Subtitle handling
                  </span>
                  <select
                    className={mmSelectFieldClass}
                    value={draft.subtitle_mode}
                    disabled={disabled}
                    onChange={(event) =>
                      change("subtitle_mode", event.target.value)
                    }
                  >
                    <option value="keep_all">Keep all subtitles</option>
                    <option value="keep_listed">Keep listed languages</option>
                    <option value="remove_all">Remove all subtitles</option>
                  </select>
                </label>
                {textField(
                  "Subtitle languages",
                  "subtitle_langs_csv",
                  "eng,fre",
                )}
                {toggle(
                  "Keep forced subtitles",
                  "Preserve forced tracks when subtitles are retained.",
                  "preserve_forced_subs",
                )}
                {toggle(
                  "Keep default subtitles",
                  "Preserve tracks already marked default.",
                  "preserve_default_subs",
                )}
              </div>
            </section>

            <SorterEditor
              title="Subtitle order"
              detail="The same ordered criteria are applied to retained subtitle tracks."
              rows={subtitleSorters}
              disabled={disabled}
              onChange={(rows) =>
                change("subtitle_sorters_json", dumpSorters(rows))
              }
            />

            <section className="space-y-3 rounded-xl border border-[var(--mm-border)] bg-[var(--mm-surface2)] p-4">
              <div>
                <h4 className="font-medium text-[var(--mm-text1)]">
                  Original language
                </h4>
                <p className="mt-1 text-xs leading-5 text-[var(--mm-text3)]">
                  Ask the saved metadata provider for the title&apos;s original
                  language. If it cannot answer, the audio preset above remains
                  the safe fallback.
                </p>
              </div>
              {toggle(
                "Keep the original language",
                "Uses the provider only for this rule set.",
                "keep_original_language",
              )}
              {draft.keep_original_language ? (
                <div className="grid gap-3 md:grid-cols-2">
                  {textField(
                    "Additional languages to keep",
                    "original_language_additional_csv",
                    "eng,jpn",
                  )}
                  {toggle(
                    "Keep only the first track per language",
                    "Avoids duplicate tracks in the same language.",
                    "original_language_keep_only_first",
                  )}
                  {toggle(
                    "Fall back if no original-language track exists",
                    "Guarantees the output still follows the saved audio preferences.",
                    "original_language_first_if_none",
                  )}
                  {toggle(
                    "Treat an untagged track as original",
                    "Useful for media whose primary track has no language tag.",
                    "original_language_treat_empty_as_original",
                  )}
                </div>
              ) : null}
            </section>

            <section className="space-y-3 rounded-xl border border-[var(--mm-border)] bg-[var(--mm-surface2)] p-4">
              <div>
                <h4 className="font-medium text-[var(--mm-text1)]">
                  Metadata cleanup
                </h4>
                <p className="mt-1 text-xs text-[var(--mm-text3)]">
                  These removals count as real work even when the audio and
                  subtitles already match.
                </p>
              </div>
              <div className="grid gap-3 md:grid-cols-2">
                {toggle(
                  "Remove embedded images",
                  "Strips cover-art streams.",
                  "remove_images",
                )}
                {toggle(
                  "Remove attachments",
                  "Strips fonts and other attached files.",
                  "remove_attachments",
                )}
                {toggle(
                  "Remove container title",
                  "Leaves other metadata intact unless selected below.",
                  "remove_title",
                )}
                {toggle(
                  "Remove language tags",
                  "Strips per-stream language metadata after selection.",
                  "remove_language_tags",
                )}
                {toggle(
                  "Remove remaining metadata",
                  "Strips other container-level tags.",
                  "remove_other_metadata",
                )}
              </div>
            </section>

            {notice ? (
              <p
                role="status"
                className="rounded border border-[var(--mm-border)] px-3 py-2 text-sm"
              >
                {notice}
              </p>
            ) : null}
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                className={mmActionButtonClass({
                  variant: "primary",
                  disabled,
                })}
                disabled={disabled}
                onClick={() => void saveRuleSet()}
              >
                {creating ? "Create rule set" : "Save rule set"}
              </button>
              {!creating && selectedRuleSet ? (
                <button
                  type="button"
                  className={mmActionButtonClass({
                    variant: "tertiary",
                    disabled:
                      disabled || selectedRuleSet.used_by_library_count > 0,
                  })}
                  disabled={
                    disabled || selectedRuleSet.used_by_library_count > 0
                  }
                  onClick={() => void removeRuleSet()}
                  title={
                    selectedRuleSet.used_by_library_count > 0
                      ? "Detach this rule set from every library before removing it."
                      : "Remove this unused rule set."
                  }
                >
                  Remove rule set
                </button>
              ) : null}
              {selectedRuleSet?.used_by_library_count ? (
                <span className="text-xs text-[var(--mm-text3)]">
                  Used by {selectedRuleSet.used_by_library_count}{" "}
                  {selectedRuleSet.used_by_library_count === 1
                    ? "library"
                    : "libraries"}
                  ; deletion is locked.
                </span>
              ) : null}
            </div>
          </div>
        )}
      </section>

      <section className="mm-module-surface rounded-xl border border-[var(--mm-border)] bg-[var(--mm-card-bg)] p-5">
        <p className="mm-page__eyebrow">Original-language source</p>
        <h2 className="mt-1 text-lg font-semibold text-[var(--mm-text1)]">
          Metadata provider
        </h2>
        <p className="mt-1 max-w-3xl text-sm leading-6 text-[var(--mm-text2)]">
          The API key is encrypted at rest and never returned to this screen. A
          failed or missing provider never fails a file; Refiner falls back to
          the rule set&apos;s audio preferences.
        </p>
        <div className="mt-4 grid gap-3 lg:grid-cols-3">
          <label className="block text-sm">
            <span className="text-[var(--mm-text2)]">Provider</span>
            <select
              className={mmSelectFieldClass}
              value={providerName}
              disabled={!editable}
              onChange={(event) =>
                setProviderName(event.target.value === "tmdb" ? "tmdb" : "")
              }
            >
              <option value="">None</option>
              <option value="tmdb">TMDb</option>
            </select>
          </label>
          <label className="block text-sm lg:col-span-2">
            <span className="text-[var(--mm-text2)]">
              Provider or gateway URL
            </span>
            <input
              className={mmEditableTextFieldClass}
              value={providerBaseUrl}
              disabled={!editable || providerName === ""}
              onChange={(event) => setProviderBaseUrl(event.target.value)}
            />
          </label>
          <label className="block text-sm lg:col-span-2">
            <span className="text-[var(--mm-text2)]">API key</span>
            <input
              type="password"
              className={mmEditableTextFieldClass}
              value={providerKey}
              disabled={!editable || providerName === "" || clearProviderKey}
              placeholder={
                provider.data?.key_configured
                  ? "Saved — enter a replacement only"
                  : "Enter API key"
              }
              onChange={(event) => setProviderKey(event.target.value)}
            />
          </label>
          <label className="flex items-center gap-2 rounded-lg border border-[var(--mm-border)] px-3 py-2 text-sm text-[var(--mm-text2)]">
            <input
              type="checkbox"
              checked={clearProviderKey}
              disabled={!editable || !provider.data?.key_configured}
              onChange={(event) => setClearProviderKey(event.target.checked)}
            />
            Remove saved key on save
          </label>
        </div>
        {providerNotice ? (
          <p
            role="status"
            className="mt-3 rounded border border-[var(--mm-border)] px-3 py-2 text-sm"
          >
            {providerNotice}
          </p>
        ) : null}
        <div className="mt-4 flex flex-wrap gap-2">
          <button
            type="button"
            className={mmActionButtonClass({
              variant: "primary",
              disabled: !editable || saveProvider.isPending,
            })}
            disabled={!editable || saveProvider.isPending}
            onClick={() => void saveProviderConnection()}
          >
            Save provider
          </button>
          <button
            type="button"
            className={mmActionButtonClass({
              variant: "secondary",
              disabled:
                !editable || providerName === "" || testProvider.isPending,
            })}
            disabled={
              !editable || providerName === "" || testProvider.isPending
            }
            onClick={() => void testProviderConnection()}
          >
            Save and test
          </button>
        </div>
      </section>
    </div>
  );
}
