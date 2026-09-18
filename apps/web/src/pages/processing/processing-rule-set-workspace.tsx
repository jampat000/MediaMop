import { useEffect, useId, useMemo, useState, type ReactNode } from "react";

import { PageLoading } from "../../components/shared/page-loading";
import {
  QuietFieldGroup,
  QuietSection,
} from "../../components/shared/quiet-section";
import { ProcessingRulesPreviewPanel } from "./processing-rules-preview-panel";
import { MmMultiListboxPicker } from "../../components/ui/mm-multi-listbox-picker";
import { useMeQuery } from "../../lib/auth/queries";
import {
  type ProcessingRuleSetWrite,
  writeFromProcessingRuleSet,
} from "../../lib/processing/libraries-api";
import {
  useCreateProcessingRuleSet,
  useDeleteProcessingRuleSet,
  useProcessingRuleSetsQuery,
  useUpdateProcessingRuleSet,
} from "../../lib/processing/libraries-queries";
import {
  useProcessingMetadataProviderQuery,
  useSaveProcessingMetadataProvider,
  useTestProcessingMetadataProvider,
} from "../../lib/processing/metadata-provider-queries";
import { PROCESSING_STREAM_LANGUAGE_OPTIONS } from "../../lib/processing/stream-language-options";
import { processingLanguageVariantsFor } from "../../lib/processing/language-variant-options";
import {
  previewTrackName,
  trackNameTemplateError,
  DEFAULT_TRACK_NAME_TEMPLATE,
  SAMPLE_TRACK,
  type TrackNamePreviewFlags,
} from "../../lib/processing/track-name-preview";
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

const LANGUAGE_OPTIONS = PROCESSING_STREAM_LANGUAGE_OPTIONS.map((option) => ({
  value: option.code,
  label: `${option.label} (${option.code})`,
}));

/**
 * Issue #496: every base language option, immediately followed by its regional variants (an
 * indented, visually nested entry), so a picker built from a flat option list still reads as
 * "variants listed under their base language" even without native optgroup support.
 */
const LANGUAGE_OPTIONS_WITH_VARIANTS = LANGUAGE_OPTIONS.flatMap((option) => [
  option,
  ...processingLanguageVariantsFor(option.value).map((variant) => ({
    value: variant.code,
    label: `— ${variant.label} (${variant.code})`,
  })),
]);

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

const EMPTY_RULE_SET: ProcessingRuleSetWrite = {
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
  remove_hearing_impaired_subs: false,
  audio_keep_mode: "single",
  subtitle_max_per_language: 0,
  subtitle_quality_strategy: "text_first",
  standardize_track_names: false,
  track_name_template: DEFAULT_TRACK_NAME_TEMPLATE,
  track_name_overrides: {
    forced: "{language} {flags}",
    hearing_impaired: "{language} {flags}",
    commentary: "{language} {flags}",
    audio_description: "{language} {flags}",
  },
  clear_video_track_names: false,
  remove_chapters: false,
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
  const known = new Set(
    LANGUAGE_OPTIONS_WITH_VARIANTS.map((option) => option.value),
  );
  const custom = values
    .filter((value) => !known.has(value))
    .map((value) => ({ value, label: value }));
  return [...LANGUAGE_OPTIONS_WITH_VARIANTS, ...custom];
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
  const known = new Set(
    LANGUAGE_OPTIONS_WITH_VARIANTS.map((option) => option.value),
  );
  const isCustom = value.length > 0 && !known.has(value);
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
        {isCustom ? <option value={value}>{value}</option> : null}
        {LANGUAGE_OPTIONS.map((base) => {
          const variants = processingLanguageVariantsFor(base.value);
          if (variants.length === 0) {
            return (
              <option key={base.value} value={base.value}>
                {base.label}
              </option>
            );
          }
          return (
            // Issue #496: regional variants are listed under their base language.
            <optgroup key={base.value} label={base.label}>
              <option value={base.value}>{base.label} (any variant)</option>
              {variants.map((variant) => (
                <option key={variant.code} value={variant.code}>
                  {variant.label} ({variant.code})
                </option>
              ))}
            </optgroup>
          );
        })}
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

/**
 * Issue #498: a track name template field with a live preview against a sample track
 * (`SAMPLE_TRACK`: "English", VFQ, 5.1, TrueHD), or an inline error naming the first unknown
 * placeholder — the exact rule `TrackNaming.ValidateAll` enforces on save.
 */
function TrackNameTemplateField({
  label,
  detail,
  value,
  disabled,
  sampleFlags,
  onChange,
}: {
  label: string;
  detail?: string;
  value: string;
  disabled: boolean;
  sampleFlags?: TrackNamePreviewFlags;
  onChange: (value: string) => void;
}) {
  const error = trackNameTemplateError(value);
  const preview =
    error === null
      ? previewTrackName(value, { ...SAMPLE_TRACK, flags: sampleFlags })
      : null;
  return (
    <label className="block text-sm">
      <span className="text-[var(--mm-text2)]">{label}</span>
      <input
        className={mmEditableTextFieldClass}
        value={value}
        placeholder={DEFAULT_TRACK_NAME_TEMPLATE}
        disabled={disabled}
        aria-invalid={error !== null}
        onChange={(event) => onChange(event.target.value)}
      />
      {detail ? (
        <span className="mt-1 block text-xs leading-5 text-[var(--mm-text3)]">
          {detail}
        </span>
      ) : null}
      {error ? (
        <span
          role="alert"
          className="mt-1 block text-xs text-[var(--mm-status-failed-text)]"
        >
          {error}
        </span>
      ) : (
        <span className="mt-1 block text-xs leading-5 text-[var(--mm-text3)]">
          Preview: <span className="font-medium">{preview}</span>
        </span>
      )}
    </label>
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
    <QuietFieldGroup step={step} title={title} detail={detail}>
      <div className="space-y-3">{children}</div>
    </QuietFieldGroup>
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
    <QuietFieldGroup title={title} detail={detail}>
      <ol>
        {rows.map((row, index) => (
          <li
            key={`${row.field}-${index}`}
            className="grid gap-2 border-b border-[var(--mm-border)] py-3 last:border-b-0 md:grid-cols-[2rem_1fr_1.4fr_auto]"
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
      <div className="mt-4">
        <button
          type="button"
          className={mmActionButtonClass({ variant: "secondary", disabled })}
          disabled={disabled}
          onClick={() =>
            onChange([
              ...rows,
              { field: "language", value: "", reversed: false },
            ])
          }
        >
          Add criterion
        </button>
      </div>
    </QuietFieldGroup>
  );
}

export function ProcessingRuleSetWorkspace() {
  const me = useMeQuery();
  const ruleSets = useProcessingRuleSetsQuery();
  const createRuleSet = useCreateProcessingRuleSet();
  const updateRuleSet = useUpdateProcessingRuleSet();
  const deleteRuleSet = useDeleteProcessingRuleSet();
  const provider = useProcessingMetadataProviderQuery();
  const saveProvider = useSaveProcessingMetadataProvider();
  const testProvider = useTestProcessingMetadataProvider();
  const editable = canEdit(me.data?.role);

  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [creating, setCreating] = useState(false);
  const [draft, setDraft] = useState<ProcessingRuleSetWrite | null>(null);
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
      setDraft(writeFromProcessingRuleSet(selected));
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
    return <PageLoading label="Loading rule sets" />;
  }

  const disabled =
    !editable || createRuleSet.isPending || updateRuleSet.isPending;
  const change = <Key extends keyof ProcessingRuleSetWrite>(
    key: Key,
    value: ProcessingRuleSetWrite[Key],
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
      setDraft(writeFromProcessingRuleSet(saved));
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
    key: keyof ProcessingRuleSetWrite,
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
    key: keyof ProcessingRuleSetWrite,
  ) => (
    <label className="flex items-start gap-3 border-b border-[var(--mm-border)] py-2.5 text-sm last:border-b-0">
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
    <div className="mm-quiet-stack" data-testid="processing-rule-set-workspace">
      <QuietSection
        headingId="processing-rule-set-profiles-heading"
        heading="Audio & subtitle profiles"
        aside={
          !creating ? (
            <button
              type="button"
              className="mm-quiet-link"
              disabled={!editable}
              onClick={() => {
                setCreating(true);
                setSelectedId(null);
                setDraft({ ...EMPTY_RULE_SET });
                setNotice(null);
                setAdvancedOrderingOpen(false);
              }}
            >
              New profile →
            </button>
          ) : null
        }
      >
        <p className="mm-quiet-note">
          Save a profile once, then assign it to one or more libraries.
        </p>

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
                setDraft(
                  selected ? writeFromProcessingRuleSet(selected) : null,
                );
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
          <div className="mt-5">
            <p className="text-sm font-medium text-[var(--mm-text1)]">
              No profiles yet
            </p>
            <p className="mm-quiet-note mt-1">
              Create one, then assign it under Libraries.
            </p>
          </div>
        ) : (
          <div className="mt-6 space-y-5 border-t border-[var(--mm-border)] pt-6">
            <div className="max-w-2xl">
              {textField("Profile name", "name", "English feature films")}
            </div>

            <div className="grid max-w-3xl gap-10">
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
                <label className="block text-sm">
                  <span className="text-[var(--mm-text2)]">
                    Audio tracks kept
                  </span>
                  <select
                    className={mmSelectFieldClass}
                    value={draft.audio_keep_mode}
                    disabled={disabled}
                    onChange={(event) =>
                      change("audio_keep_mode", event.target.value)
                    }
                  >
                    <option value="single">
                      One winning track (today&apos;s behavior)
                    </option>
                    <option value="per_language">
                      Best track of each configured language
                    </option>
                  </select>
                  <span className="mt-1 block text-xs leading-5 text-[var(--mm-text3)]">
                    &quot;Best track of each configured language&quot; keeps the
                    original alongside a dub, e.g. Japanese plus an English dub,
                    each the best available track of its language. Never keeps
                    zero audio tracks.
                  </span>
                </label>
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
                      "Preserve tracks needed to translate foreign dialogue. A signs track counts as forced too.",
                      "preserve_forced_subs",
                    )}
                    {toggle(
                      "Keep default subtitles",
                      "Preserve tracks already marked as default.",
                      "preserve_default_subs",
                    )}
                    {toggle(
                      "Remove hearing-impaired subtitles",
                      'Drop a subtitle track detected as SDH/CC, from its flag or its name (e.g. "English (SDH)").',
                      "remove_hearing_impaired_subs",
                    )}
                    <div className="grid gap-3 sm:grid-cols-2">
                      <label className="block text-sm">
                        <span className="text-[var(--mm-text2)]">
                          Limit subtitles kept per language
                        </span>
                        <input
                          type="number"
                          min={0}
                          className={mmEditableTextFieldClass}
                          value={draft.subtitle_max_per_language}
                          disabled={disabled}
                          onChange={(event) =>
                            change(
                              "subtitle_max_per_language",
                              Math.max(0, Number(event.target.value) || 0),
                            )
                          }
                        />
                        <span className="mt-1 block text-xs leading-5 text-[var(--mm-text3)]">
                          0 means unlimited (today&apos;s behavior). A forced
                          track kept above doesn&apos;t count toward this cap.
                        </span>
                      </label>
                      <label className="block text-sm">
                        <span className="text-[var(--mm-text2)]">
                          How to pick the best subtitle
                        </span>
                        <select
                          className={mmSelectFieldClass}
                          value={draft.subtitle_quality_strategy}
                          disabled={
                            disabled || draft.subtitle_max_per_language === 0
                          }
                          onChange={(event) =>
                            change(
                              "subtitle_quality_strategy",
                              event.target.value,
                            )
                          }
                        >
                          <option value="text_first">
                            Text subtitles first (SRT/ASS over PGS)
                          </option>
                          <option value="image_first">
                            Image subtitles first (PGS over SRT/ASS)
                          </option>
                          <option value="accessibility">
                            Hearing-impaired (SDH) first
                          </option>
                        </select>
                        <span className="mt-1 block text-xs leading-5 text-[var(--mm-text3)]">
                          Only used while the cap above is set.
                        </span>
                      </label>
                    </div>
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
                detail="Select optional streams and tags Weir should strip after track selection."
              >
                <div className="grid gap-3">
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

              <ProfileSettingsSection
                step={5}
                title="Track naming & chapters"
                detail="Optional, off by default: give kept tracks consistent names and drop chapter lists."
              >
                {toggle(
                  "Standardize audio and subtitle track names",
                  "Write a name from the template below on every kept track, instead of whatever the release called it.",
                  "standardize_track_names",
                )}
                {draft.standardize_track_names ? (
                  <div className="space-y-4 border-l-2 border-[var(--mm-border)] pl-4">
                    <TrackNameTemplateField
                      label="Track name template"
                      detail="Placeholders: {language} {variant} {channels} {codec} {flags}."
                      value={draft.track_name_template}
                      disabled={disabled}
                      onChange={(value) => change("track_name_template", value)}
                    />
                    <div className="space-y-3">
                      <p className="text-xs font-medium text-[var(--mm-text2)]">
                        Overrides for flagged tracks (checked in this order;
                        leave blank to fall back to the template above)
                      </p>
                      <div className="grid gap-3 sm:grid-cols-2">
                        <TrackNameTemplateField
                          label="Forced tracks"
                          value={draft.track_name_overrides.forced}
                          disabled={disabled}
                          sampleFlags={{ forced: true }}
                          onChange={(value) =>
                            change("track_name_overrides", {
                              ...draft.track_name_overrides,
                              forced: value,
                            })
                          }
                        />
                        <TrackNameTemplateField
                          label="Hearing-impaired tracks"
                          value={draft.track_name_overrides.hearing_impaired}
                          disabled={disabled}
                          sampleFlags={{ hearingImpaired: true }}
                          onChange={(value) =>
                            change("track_name_overrides", {
                              ...draft.track_name_overrides,
                              hearing_impaired: value,
                            })
                          }
                        />
                        <TrackNameTemplateField
                          label="Commentary tracks"
                          value={draft.track_name_overrides.commentary}
                          disabled={disabled}
                          sampleFlags={{ commentary: true }}
                          onChange={(value) =>
                            change("track_name_overrides", {
                              ...draft.track_name_overrides,
                              commentary: value,
                            })
                          }
                        />
                        <TrackNameTemplateField
                          label="Audio description tracks"
                          value={draft.track_name_overrides.audio_description}
                          disabled={disabled}
                          sampleFlags={{ audioDescription: true }}
                          onChange={(value) =>
                            change("track_name_overrides", {
                              ...draft.track_name_overrides,
                              audio_description: value,
                            })
                          }
                        />
                      </div>
                    </div>
                  </div>
                ) : null}
                {toggle(
                  "Clear video track names",
                  'Blank out scene-tag video titles such as "x265-GROUP".',
                  "clear_video_track_names",
                )}
                {toggle(
                  "Remove chapters",
                  "Drop the container's chapter list.",
                  "remove_chapters",
                )}
              </ProfileSettingsSection>
            </div>

            <section>
              <button
                type="button"
                className="flex w-full items-center justify-between gap-4 border-b border-[var(--mm-border)] py-3 text-left"
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
                <div className="mt-8 space-y-10">
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

            <ProcessingRulesPreviewPanel rules={draft} disabled={!editable} />

            {notice ? (
              <p
                role="status"
                className="text-sm font-medium text-[var(--mm-text1)]"
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
      </QuietSection>

      <QuietSection
        headingId="processing-rule-set-provider-heading"
        heading="Metadata provider"
        aside={
          <>
            <span className="mm-quiet-badge">
              {providerName
                ? `${providerName.toUpperCase()} configured`
                : "Not configured"}
            </span>
            <button
              type="button"
              className="mm-quiet-link"
              aria-expanded={providerEditorOpen}
              onClick={() => setProviderEditorOpen((open) => !open)}
            >
              {providerEditorOpen ? "Close →" : "Configure →"}
            </button>
          </>
        }
      >
        <p className="mm-quiet-note">
          Only needed by profiles that keep a title&apos;s original language.
          Weir falls back safely when metadata is unavailable.
        </p>

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
              <label className="flex items-center gap-2 self-end py-2 text-sm text-[var(--mm-text2)]">
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
                className="mt-3 text-sm font-medium text-[var(--mm-text1)]"
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
      </QuietSection>
    </div>
  );
}
