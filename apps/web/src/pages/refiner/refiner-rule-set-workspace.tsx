import { useEffect, useId, useMemo, useState, type ReactNode } from "react";

import { PageLoading } from "../../components/shared/page-loading";
import { RefinerRulesPreviewPanel } from "./refiner-rules-preview-panel";
import { MmMultiListboxPicker } from "../../components/ui/mm-multi-listbox-picker";
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
import { REFINER_STREAM_LANGUAGE_OPTIONS } from "../../lib/refiner/stream-language-options";
import {
  mmActionButtonClass,
  mmCheckboxControlClass,
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

const SORTER_LABELS: Record<string, string> = {
  language: "Language",
  channels: "Channel count",
  codec: "Codec",
  bitrate: "Bitrate",
  title: "Track title",
  default: "Default flag",
  forced: "Forced flag",
  commentary: "Commentary flag",
};

const LANGUAGE_OPTIONS = REFINER_STREAM_LANGUAGE_OPTIONS.map((option) => ({
  value: option.code,
  label: `${option.label} (${option.code})`,
}));

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

function csvValues(value: string): string[] {
  return value
    .split(",")
    .map((item) => item.trim().toLowerCase())
    .filter(Boolean);
}

function languageOptionsFor(values: readonly string[]) {
  const known = new Set(LANGUAGE_OPTIONS.map((option) => option.value));
  const custom = values
    .filter((value) => !known.has(value))
    .map((value) => ({ value, label: value }));
  return [...LANGUAGE_OPTIONS, ...custom];
}

function LanguageSelectField({
  label,
  value,
  optional = false,
  disabled,
  onChange,
}: {
  label: string;
  value: string;
  optional?: boolean;
  disabled: boolean;
  onChange: (value: string) => void;
}) {
  const options = languageOptionsFor(value ? [value] : []);
  return (
    <label className="block text-sm">
      <span className="text-[var(--mm-text2)]">{label}</span>
      <select
        className={mmSelectFieldClass}
        value={value}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value)}
      >
        {optional ? <option value="">None</option> : null}
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  );
}

function LanguageMultiField({
  label,
  value,
  disabled,
  onChange,
}: {
  label: string;
  value: string;
  disabled: boolean;
  onChange: (value: string) => void;
}) {
  const labelId = useId();
  const values = csvValues(value);
  return (
    <div className="block text-sm">
      <span id={labelId} className="text-[var(--mm-text2)]">
        {label}
      </span>
      <MmMultiListboxPicker
        options={languageOptionsFor(values)}
        values={values}
        disabled={disabled}
        ariaLabelledBy={labelId}
        placeholder="Choose languages…"
        onChange={(next) => onChange(next.join(","))}
      />
    </div>
  );
}

function ProfileSettingsSection({
  step,
  title,
  detail,
  children,
}: {
  step: number;
  title: string;
  detail: string;
  children: ReactNode;
}) {
  return (
    <section className="rounded-xl border border-[var(--mm-border)] bg-[var(--mm-surface2)] p-4 sm:p-5">
      <div className="flex items-start gap-3">
        <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-[var(--mm-gold)] bg-[var(--mm-accent-soft)] text-xs font-bold text-[var(--mm-text1)]">
          {step}
        </span>
        <div className="min-w-0">
          <h3 className="font-semibold text-[var(--mm-text1)]">{title}</h3>
          <p className="mt-1 text-xs leading-5 text-[var(--mm-text3)]">
            {detail}
          </p>
        </div>
      </div>
      <div className="mt-4 space-y-3">{children}</div>
    </section>
  );
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
                    {SORTER_LABELS[field] ?? field}
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
                  className={mmCheckboxControlClass}
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
  const [advancedOrderingOpen, setAdvancedOrderingOpen] = useState(false);
  const [providerEditorOpen, setProviderEditorOpen] = useState(false);

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
        className={mmCheckboxControlClass}
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
      <section className="mm-module-surface rounded-xl border border-[var(--mm-border)] bg-[var(--mm-card-bg)] p-5 sm:p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <p className="mm-page__eyebrow">Processing profiles</p>
            <h2 className="mt-1 text-xl font-semibold text-[var(--mm-text1)]">
              Audio &amp; subtitle profiles
            </h2>
            <p className="mt-1 max-w-3xl text-sm leading-6 text-[var(--mm-text2)]">
              Save a profile once, then assign it to one or more libraries.
            </p>
          </div>
          {!creating ? (
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
                setAdvancedOrderingOpen(false);
              }}
            >
              New profile
            </button>
          ) : null}
        </div>

        {(ruleSets.data?.length ?? 0) > 0 && !creating ? (
          <label className="mt-5 block max-w-2xl text-sm">
            <span className="text-[var(--mm-text2)]">Profile to edit</span>
            <select
              className={mmSelectFieldClass}
              value={selectedId ?? ""}
              onChange={(event) => {
                const id = Number(event.target.value);
                const selected = ruleSets.data?.find((row) => row.id === id);
                setSelectedId(id);
                setDraft(selected ? writeFromRefinerRuleSet(selected) : null);
                setNotice(null);
                setAdvancedOrderingOpen(false);
              }}
            >
              {(ruleSets.data ?? []).map((row) => (
                <option key={row.id} value={row.id}>
                  {row.name} · {row.used_by_library_count}{" "}
                  {row.used_by_library_count === 1 ? "library" : "libraries"}
                </option>
              ))}
            </select>
          </label>
        ) : null}

        {!draft ? (
          <div className="mt-5 rounded-xl border border-dashed border-[var(--mm-border)] px-4 py-6 text-sm text-[var(--mm-text2)]">
            <p className="font-medium text-[var(--mm-text1)]">
              No profiles yet
            </p>
            <p className="mt-1">Create one, then assign it under Libraries.</p>
          </div>
        ) : (
          <div className="mt-6 space-y-5 border-t border-[var(--mm-border)] pt-6">
            <div className="max-w-2xl">
              {textField("Profile name", "name", "English feature films")}
            </div>

            <div className="grid items-start gap-4 xl:grid-cols-2">
              <ProfileSettingsSection
                step={1}
                title="Audio"
                detail="Choose the language priority and which retained track becomes default."
              >
                <label className="block text-sm">
                  <span className="text-[var(--mm-text2)]">
                    Selection strategy
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
                      Preferred languages, then quality
                    </option>
                    <option value="preferred_langs_strict">
                      Preferred languages only
                    </option>
                    <option value="quality_all_languages">
                      Best quality in any language
                    </option>
                  </select>
                </label>
                <div className="grid gap-3 sm:grid-cols-2">
                  <LanguageSelectField
                    label="First choice"
                    value={draft.primary_audio_lang}
                    disabled={disabled}
                    onChange={(value) => change("primary_audio_lang", value)}
                  />
                  <LanguageSelectField
                    label="Second choice"
                    value={draft.secondary_audio_lang}
                    optional
                    disabled={disabled}
                    onChange={(value) => change("secondary_audio_lang", value)}
                  />
                  <LanguageSelectField
                    label="Third choice"
                    value={draft.tertiary_audio_lang}
                    optional
                    disabled={disabled}
                    onChange={(value) => change("tertiary_audio_lang", value)}
                  />
                  <label className="block text-sm">
                    <span className="text-[var(--mm-text2)]">
                      Mark as default
                    </span>
                    <select
                      className={mmSelectFieldClass}
                      value={draft.default_audio_slot}
                      disabled={disabled}
                      onChange={(event) =>
                        change("default_audio_slot", event.target.value)
                      }
                    >
                      <option value="primary">First choice</option>
                      <option value="secondary">Second choice</option>
                      <option value="tertiary">Third choice</option>
                    </select>
                  </label>
                </div>
                {toggle(
                  "Remove commentary tracks",
                  "Exclude commentary before selecting the preferred audio.",
                  "remove_commentary",
                )}
              </ProfileSettingsSection>

              <ProfileSettingsSection
                step={2}
                title="Subtitles"
                detail="Choose what is retained and which tracks keep their flags."
              >
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
                    <option value="keep_listed">Keep selected languages</option>
                    <option value="remove_all">Remove all subtitles</option>
                  </select>
                </label>
                {draft.subtitle_mode === "keep_listed" ? (
                  <LanguageMultiField
                    label="Languages to keep"
                    value={draft.subtitle_langs_csv}
                    disabled={disabled}
                    onChange={(value) => change("subtitle_langs_csv", value)}
                  />
                ) : null}
                {draft.subtitle_mode !== "remove_all" ? (
                  <div className="grid gap-3">
                    {toggle(
                      "Keep forced subtitles",
                      "Preserve tracks needed to translate foreign dialogue.",
                      "preserve_forced_subs",
                    )}
                    {toggle(
                      "Keep default subtitles",
                      "Preserve tracks already marked as default.",
                      "preserve_default_subs",
                    )}
                  </div>
                ) : null}
              </ProfileSettingsSection>

              <ProfileSettingsSection
                step={3}
                title="Original language"
                detail="Optionally keep the title's original spoken language as well."
              >
                {toggle(
                  "Keep the original language",
                  providerName
                    ? `Uses ${providerName.toUpperCase()} when it can identify the title.`
                    : "Requires the metadata provider configured below.",
                  "keep_original_language",
                )}
                {draft.keep_original_language ? (
                  <div className="space-y-3 border-l-2 border-[var(--mm-border)] pl-4">
                    <LanguageMultiField
                      label="Other languages to keep"
                      value={draft.original_language_additional_csv}
                      disabled={disabled}
                      onChange={(value) =>
                        change("original_language_additional_csv", value)
                      }
                    />
                    {toggle(
                      "Keep one track per language",
                      "Avoid duplicate tracks in the same language.",
                      "original_language_keep_only_first",
                    )}
                    {toggle(
                      "Use audio preferences if no match is found",
                      "Keeps the profile safe when metadata is incomplete.",
                      "original_language_first_if_none",
                    )}
                    {toggle(
                      "Treat an untagged track as original",
                      "Useful when the main track has no language tag.",
                      "original_language_treat_empty_as_original",
                    )}
                  </div>
                ) : null}
              </ProfileSettingsSection>

              <ProfileSettingsSection
                step={4}
                title="Remove from container"
                detail="Select optional streams and tags Refiner should strip after track selection."
              >
                <div className="grid gap-3 sm:grid-cols-2">
                  {toggle(
                    "Embedded images",
                    "Strip embedded cover art.",
                    "remove_images",
                  )}
                  {toggle(
                    "Attachments",
                    "Strip fonts and other attached files.",
                    "remove_attachments",
                  )}
                  {toggle(
                    "Container title",
                    "Remove the container title only.",
                    "remove_title",
                  )}
                  {toggle(
                    "Language tags",
                    "Strip language metadata after selection.",
                    "remove_language_tags",
                  )}
                  {toggle(
                    "Other metadata",
                    "Strip other container-level tags.",
                    "remove_other_metadata",
                  )}
                </div>
              </ProfileSettingsSection>
            </div>

            <section className="rounded-xl border border-[var(--mm-border)] bg-[var(--mm-surface2)]">
              <button
                type="button"
                className="flex w-full items-center justify-between gap-4 p-4 text-left sm:p-5"
                aria-expanded={advancedOrderingOpen}
                onClick={() => setAdvancedOrderingOpen((open) => !open)}
              >
                <span>
                  <span className="block font-semibold text-[var(--mm-text1)]">
                    Advanced track ordering
                  </span>
                  <span className="mt-1 block text-xs leading-5 text-[var(--mm-text3)]">
                    Override the profile defaults with ordered codec, channel,
                    bitrate, and flag criteria.
                  </span>
                </span>
                <span className="shrink-0 text-sm font-semibold text-[var(--mm-accent-bright)]">
                  {advancedOrderingOpen ? "Hide" : "Edit"}
                </span>
              </button>
              {advancedOrderingOpen ? (
                <div className="space-y-4 border-t border-[var(--mm-border)] p-4 sm:p-5">
                  <SorterEditor
                    title="Audio order"
                    detail="The first matching criterion wins. Only add a match value when a criterion needs one."
                    rows={audioSorters}
                    disabled={disabled}
                    onChange={(rows) =>
                      change("audio_sorters_json", dumpSorters(rows))
                    }
                  />
                  <SorterEditor
                    title="Subtitle order"
                    detail="These criteria rank only the subtitle tracks retained above."
                    rows={subtitleSorters}
                    disabled={disabled}
                    onChange={(rows) =>
                      change("subtitle_sorters_json", dumpSorters(rows))
                    }
                  />
                </div>
              ) : null}
            </section>

            <RefinerRulesPreviewPanel rules={draft} disabled={!editable} />

            {notice ? (
              <p
                role="status"
                className="rounded border border-[var(--mm-border)] px-3 py-2 text-sm"
              >
                {notice}
              </p>
            ) : null}
            <div className="flex flex-wrap items-center gap-2 border-t border-[var(--mm-border)] pt-5">
              <button
                type="button"
                className={mmActionButtonClass({
                  variant: "primary",
                  disabled,
                })}
                disabled={disabled}
                onClick={() => void saveRuleSet()}
              >
                {creating ? "Create profile" : "Save profile"}
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
                      ? "Detach this profile from every library before removing it."
                      : "Remove this unused profile."
                  }
                >
                  Remove profile
                </button>
              ) : null}
              {selectedRuleSet?.used_by_library_count ? (
                <span className="text-xs text-[var(--mm-text3)]">
                  Used by {selectedRuleSet.used_by_library_count}{" "}
                  {selectedRuleSet.used_by_library_count === 1
                    ? "library"
                    : "libraries"}
                  ; removal is locked.
                </span>
              ) : null}
            </div>
          </div>
        )}
      </section>

      <section className="mm-module-surface rounded-xl border border-[var(--mm-border)] bg-[var(--mm-card-bg)] p-5 sm:p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <p className="mm-page__eyebrow">Optional connection</p>
            <h2 className="mt-1 text-lg font-semibold text-[var(--mm-text1)]">
              Metadata provider
            </h2>
            <p className="mt-1 max-w-3xl text-sm leading-6 text-[var(--mm-text2)]">
              Only needed by profiles that keep a title&apos;s original
              language. Refiner falls back safely when metadata is unavailable.
            </p>
          </div>
          <div className="flex items-center gap-3">
            <span className="rounded-full border border-[var(--mm-border)] px-2.5 py-1 text-xs font-semibold text-[var(--mm-text2)]">
              {providerName
                ? `${providerName.toUpperCase()} configured`
                : "Not configured"}
            </span>
            <button
              type="button"
              className={mmActionButtonClass({ variant: "secondary" })}
              aria-expanded={providerEditorOpen}
              onClick={() => setProviderEditorOpen((open) => !open)}
            >
              {providerEditorOpen ? "Close" : "Configure"}
            </button>
          </div>
        </div>

        {providerEditorOpen ? (
          <div className="mt-5 border-t border-[var(--mm-border)] pt-5">
            <div className="grid gap-3 lg:grid-cols-3">
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
                  disabled={
                    !editable || providerName === "" || clearProviderKey
                  }
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
                  className={mmCheckboxControlClass}
                  checked={clearProviderKey}
                  disabled={!editable || !provider.data?.key_configured}
                  onChange={(event) =>
                    setClearProviderKey(event.target.checked)
                  }
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
          </div>
        ) : null}
      </section>
    </div>
  );
}
