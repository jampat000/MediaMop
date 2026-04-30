import { useEffect, useState, type ReactNode } from "react";
import { fetchCsrfToken } from "../../lib/api/auth-api";
import { MmOnOffSwitch } from "../../components/ui/mm-on-off-switch";
import { MmListboxPicker } from "../../components/ui/mm-listbox-picker";
import { ServerFolderPickerButton } from "../../components/ui/server-folder-picker-button";
import type { MmListboxOption } from "../../components/ui/mm-listbox-picker";
import { mmActionButtonClass } from "../../lib/ui/mm-control-roles";
import {
  SUBBER_LANGUAGE_OPTIONS,
  subberLanguageLabel,
} from "../../lib/subber/subber-languages";
import {
  usePutSubberSettingsMutation,
  useSubberSettingsQuery,
} from "../../lib/subber/subber-queries";

function SaveFeedback({ ok, err }: { ok: boolean; err: string | null }) {
  if (err) {
    return (
      <p className="text-sm leading-relaxed text-red-400" role="alert">
        {err}
      </p>
    );
  }
  if (ok) {
    return (
      <p className="text-sm leading-relaxed text-emerald-600" role="status">
        Saved.
      </p>
    );
  }
  return null;
}

function SubberSettingsSection({
  eyebrow,
  title,
  description,
  children,
  footer,
  className,
  "data-testid": dataTestId,
}: {
  eyebrow?: string;
  title: string;
  description?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
  className?: string;
  "data-testid"?: string;
}) {
  return (
    <section
      className={[
        "flex h-full min-h-0 min-w-0 flex-col overflow-hidden rounded-lg border border-[var(--mm-border)] bg-[var(--mm-card-bg)] shadow-sm",
        className ?? "",
      ].join(" ")}
      data-testid={dataTestId}
    >
      <header className="shrink-0 border-b border-[var(--mm-border)] bg-black/10 px-5 py-4">
        {eyebrow ? (
          <p className="text-[0.7rem] font-semibold uppercase tracking-[0.12em] text-[var(--mm-text2)]">
            {eyebrow}
          </p>
        ) : null}
        <h2
          className={
            eyebrow
              ? "mt-1 text-lg font-semibold tracking-tight text-[var(--mm-text)]"
              : "text-lg font-semibold tracking-tight text-[var(--mm-text)]"
          }
        >
          {title}
        </h2>
        {description ? (
          <div className="mt-2 text-sm leading-relaxed text-[var(--mm-text2)]">
            {description}
          </div>
        ) : null}
      </header>
      <div className="flex min-h-0 flex-1 flex-col px-5 py-5">
        <div className="mm-card-action-body min-h-0 flex-1">{children}</div>
        {footer ? <div className="mm-card-action-footer">{footer}</div> : null}
      </div>
    </section>
  );
}

export function SubberPreferencesTab({ canOperate }: { canOperate: boolean }) {
  const q = useSubberSettingsQuery();
  const put = usePutSubberSettingsMutation();

  const [langs, setLangs] = useState<string[]>(["en"]);
  const [folder, setFolder] = useState("");
  const [enabled, setEnabled] = useState(false);
  const [excludeHi, setExcludeHi] = useState(false);
  const [adaptEn, setAdaptEn] = useState(true);
  const [adaptMax, setAdaptMax] = useState(3);
  const [adaptDelayH, setAdaptDelayH] = useState(168);
  const [adaptPerm, setAdaptPerm] = useState(10);
  const [upEn, setUpEn] = useState(false);
  const [upIntervalMin, setUpIntervalMin] = useState(10080);
  const [langDirty, setLangDirty] = useState(false);
  const [prefsDirty, setPrefsDirty] = useState(false);
  const [adaptDirty, setAdaptDirty] = useState(false);
  const [upgradeDirty, setUpgradeDirty] = useState(false);

  const [saveLang, setSaveLang] = useState({
    ok: false,
    err: null as string | null,
  });
  const [savePrefs, setSavePrefs] = useState({
    ok: false,
    err: null as string | null,
  });
  const [saveFreq, setSaveFreq] = useState({
    ok: false,
    err: null as string | null,
  });
  const [saveUpgrade, setSaveUpgrade] = useState({
    ok: false,
    err: null as string | null,
  });

  useEffect(() => {
    const d = q.data;
    if (!d) return;
    setLangs(
      d.language_preferences?.length ? [...d.language_preferences] : ["en"],
    );
    setFolder(d.subtitle_folder ?? "");
    setEnabled(d.enabled);
    setExcludeHi(Boolean(d.exclude_hearing_impaired));
    setAdaptEn(Boolean(d.adaptive_searching_enabled));
    setAdaptMax(d.adaptive_searching_max_attempts ?? 3);
    setAdaptDelayH(d.adaptive_searching_delay_hours ?? 168);
    setAdaptPerm(d.permanent_skip_after_attempts ?? 10);
    setUpEn(Boolean(d.upgrade_enabled));
    setUpIntervalMin(
      Math.max(
        60,
        Math.round((d.upgrade_schedule_interval_seconds ?? 604800) / 60),
      ),
    );
    setLangDirty(false);
    setPrefsDirty(false);
    setAdaptDirty(false);
    setUpgradeDirty(false);
  }, [q.data]);

  const dis = !canOperate || put.isPending;

  function flashSave(setter: typeof setSaveLang) {
    setter({ ok: true, err: null });
    window.setTimeout(() => setter({ ok: false, err: null }), 2500);
  }

  async function saveLanguages() {
    setSaveLang({ ok: false, err: null });
    try {
      const csrf_token = await fetchCsrfToken();
      await put.mutateAsync({ csrf_token, language_preferences: langs });
      flashSave(setSaveLang);
      setLangDirty(false);
    } catch (e) {
      setSaveLang({ ok: false, err: (e as Error).message });
    }
  }

  async function savePreferences() {
    setSavePrefs({ ok: false, err: null });
    try {
      const csrf_token = await fetchCsrfToken();
      await put.mutateAsync({
        csrf_token,
        subtitle_folder: folder.trim(),
        exclude_hearing_impaired: excludeHi,
        enabled,
      });
      flashSave(setSavePrefs);
      setPrefsDirty(false);
    } catch (e) {
      setSavePrefs({ ok: false, err: (e as Error).message });
    }
  }

  async function saveSearchFrequency() {
    setSaveFreq({ ok: false, err: null });
    try {
      const csrf_token = await fetchCsrfToken();
      await put.mutateAsync({
        csrf_token,
        adaptive_searching_enabled: adaptEn,
        adaptive_searching_max_attempts: adaptMax,
        adaptive_searching_delay_hours: adaptDelayH,
        permanent_skip_after_attempts: adaptPerm,
      });
      flashSave(setSaveFreq);
      setAdaptDirty(false);
    } catch (e) {
      setSaveFreq({ ok: false, err: (e as Error).message });
    }
  }

  async function saveUpgradePrefs() {
    setSaveUpgrade({ ok: false, err: null });
    try {
      const csrf_token = await fetchCsrfToken();
      await put.mutateAsync({
        csrf_token,
        upgrade_enabled: upEn,
        upgrade_schedule_interval_seconds: Math.max(
          60,
          Math.min(365 * 24 * 3600, upIntervalMin * 60),
        ),
      });
      flashSave(setSaveUpgrade);
      setUpgradeDirty(false);
    } catch (e) {
      setSaveUpgrade({ ok: false, err: (e as Error).message });
    }
  }

  if (q.isLoading)
    return <p className="text-sm text-[var(--mm-text2)]">Loading settings…</p>;
  if (q.isError)
    return <p className="text-sm text-red-600">{(q.error as Error).message}</p>;

  return (
    <div className="mm-bubble-stack" data-testid="subber-preferences-tab">
      {/* 2×2 on large screens so each row’s pair shares equal card height */}
      <div className="mm-bubble-grid min-w-0 lg:grid-cols-2">
        <section className="order-1 flex h-full min-h-0 min-w-0 flex-col overflow-hidden rounded-lg border border-[var(--mm-border)] bg-[var(--mm-card-bg)] shadow-sm lg:order-none">
          <header className="shrink-0 border-b border-[var(--mm-border)] bg-black/10 px-5 py-4">
            <p className="text-[0.7rem] font-semibold uppercase tracking-[0.12em] text-[var(--mm-text2)]">
              Search order
            </p>
            <h2 className="mt-1 text-lg font-semibold tracking-tight text-[var(--mm-text)]">
              Subtitle languages
            </h2>
            <div className="mt-2 text-sm leading-relaxed text-[var(--mm-text2)]">
              Subber tries languages in this order. If the first is not found it
              tries the next automatically.
            </div>
          </header>
          <div className="flex min-h-0 flex-1 flex-col px-5 py-5">
            <div className="mm-card-action-body min-h-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                {langs.map((code, idx) => (
                  <span
                    key={`${code}-${idx}`}
                    className="inline-flex items-center gap-1 rounded-full border border-[var(--mm-border)] bg-black/15 px-2.5 py-1 text-sm text-[var(--mm-text)]"
                  >
                    <span>{subberLanguageLabel(code)}</span>
                    <span className="flex items-center gap-0.5 border-l border-[var(--mm-border)] pl-1.5">
                      <button
                        type="button"
                        className="rounded px-1 text-xs text-[var(--mm-text2)] hover:bg-[var(--mm-card-bg)] disabled:opacity-30"
                        disabled={dis || idx === 0}
                        aria-label={`Move ${code} up`}
                        onClick={() => {
                          const n = [...langs];
                          [n[idx - 1], n[idx]] = [n[idx], n[idx - 1]];
                          setLangs(n);
                          setLangDirty(true);
                        }}
                      >
                        ↑
                      </button>
                      <button
                        type="button"
                        className="rounded px-1 text-xs text-[var(--mm-text2)] hover:bg-[var(--mm-card-bg)] disabled:opacity-30"
                        disabled={dis || idx >= langs.length - 1}
                        aria-label={`Move ${code} down`}
                        onClick={() => {
                          const n = [...langs];
                          [n[idx + 1], n[idx]] = [n[idx], n[idx + 1]];
                          setLangs(n);
                          setLangDirty(true);
                        }}
                      >
                        ↓
                      </button>
                    </span>
                    <button
                      type="button"
                      className="ml-0.5 rounded px-1.5 text-base leading-none text-[var(--mm-text2)] hover:bg-red-950/30 hover:text-red-300"
                      disabled={dis}
                      aria-label={`Remove ${subberLanguageLabel(code)}`}
                      onClick={() => {
                        setLangs(langs.filter((_, i) => i !== idx));
                        setLangDirty(true);
                      }}
                    >
                      ×
                    </button>
                  </span>
                ))}
              </div>
              <div>
                <span
                  id="subber-add-language-label"
                  className="block text-sm text-[var(--mm-text2)]"
                >
                  Add language
                </span>
                <MmListboxPicker
                  className="mt-1 max-w-xs"
                  ariaLabelledBy="subber-add-language-label"
                  placeholder="Choose…"
                  disabled={dis}
                  options={[
                    { value: "", label: "Choose…" },
                    ...SUBBER_LANGUAGE_OPTIONS.filter(
                      (o) => !langs.includes(o.code),
                    ).map(
                      (o): MmListboxOption => ({
                        value: o.code,
                        label: o.label,
                      }),
                    ),
                  ]}
                  value=""
                  onChange={(v) => {
                    if (!v || langs.includes(v)) return;
                    setLangs([...langs, v]);
                    setLangDirty(true);
                  }}
                />
              </div>
            </div>
            <div className="mm-card-action-footer">
              <button
                type="button"
                className={mmActionButtonClass({
                  variant: langDirty ? "primary" : "secondary",
                  disabled: dis || !langDirty,
                })}
                disabled={dis || !langDirty}
                onClick={() => void saveLanguages()}
                data-testid="subber-save-languages"
              >
                Save languages
              </button>
              <SaveFeedback ok={saveLang.ok} err={saveLang.err} />
            </div>
          </div>
        </section>

        <SubberSettingsSection
          className="order-3 lg:order-none"
          eyebrow="Automation"
          title="Adaptive searching"
          description="Back off automatically when subtitles are not found so repeated searches do not burn through your daily download quota."
          footer={
            <>
              <button
                type="button"
                className={mmActionButtonClass({
                  variant: adaptDirty ? "primary" : "secondary",
                  disabled: dis || !adaptDirty,
                })}
                disabled={dis || !adaptDirty}
                onClick={() => void saveSearchFrequency()}
              >
                Save adaptive settings
              </button>
              <SaveFeedback ok={saveFreq.ok} err={saveFreq.err} />
            </>
          }
        >
          <MmOnOffSwitch
            id="subber-adapt"
            label="Enable adaptive searching"
            enabled={adaptEn}
            disabled={dis}
            onChange={(v) => {
              setAdaptEn(v);
              setAdaptDirty(true);
            }}
          />
          {adaptEn ? (
            <div className="space-y-3">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-sm text-[var(--mm-text2)]">
                  Back off after
                </span>
                <input
                  type="number"
                  className="mm-input max-w-24"
                  min={1}
                  max={100}
                  value={adaptMax}
                  disabled={dis}
                  onChange={(e) => {
                    setAdaptMax(Number(e.target.value) || 1);
                    setAdaptDirty(true);
                  }}
                />
                <span className="text-sm text-[var(--mm-text2)]">
                  failed attempts
                </span>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-sm text-[var(--mm-text2)]">Wait</span>
                <input
                  type="number"
                  className="mm-input max-w-24"
                  min={1}
                  max={8760}
                  value={adaptDelayH}
                  disabled={dis}
                  onChange={(e) => {
                    setAdaptDelayH(Number(e.target.value) || 1);
                    setAdaptDirty(true);
                  }}
                />
                <span className="text-sm text-[var(--mm-text2)]">
                  hours before retrying
                </span>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-sm text-[var(--mm-text2)]">
                  Give up after
                </span>
                <input
                  type="number"
                  className="mm-input max-w-24"
                  min={1}
                  max={10000}
                  value={adaptPerm}
                  disabled={dis}
                  onChange={(e) => {
                    setAdaptPerm(Number(e.target.value) || 1);
                    setAdaptDirty(true);
                  }}
                />
                <span className="text-sm text-[var(--mm-text2)]">
                  total attempts
                </span>
              </div>
            </div>
          ) : null}
        </SubberSettingsSection>

        <SubberSettingsSection
          className="order-2 lg:order-none"
          eyebrow="Files & behavior"
          title="Preferences"
          description="Where subtitles are written, optional filtering, and the master switch for automatic searches."
          footer={
            <>
              <button
                type="button"
                className={mmActionButtonClass({
                  variant: prefsDirty ? "primary" : "secondary",
                  disabled: dis || !prefsDirty,
                })}
                disabled={dis || !prefsDirty}
                onClick={() => void savePreferences()}
                data-testid="subber-save-subtitle-folder"
              >
                Save preferences
              </button>
              <SaveFeedback ok={savePrefs.ok} err={savePrefs.err} />
            </>
          }
        >
          <div>
            <label
              className="block text-sm font-medium text-[var(--mm-text)]"
              htmlFor="subber-subtitle-folder"
            >
              Subtitle folder
            </label>
            <input
              id="subber-subtitle-folder"
              className="mm-input w-full"
              value={folder}
              disabled={dis}
              onChange={(e) => {
                setFolder(e.target.value);
                setPrefsDirty(true);
              }}
              placeholder="Same folder as media file"
            />
            <div className="mt-2 max-w-xl">
              <ServerFolderPickerButton
                title="Choose subtitle folder"
                value={folder}
                disabled={dis}
                onSelect={(path) => {
                  setFolder(path);
                  setPrefsDirty(true);
                }}
              />
            </div>
            <p className="mt-1 text-xs text-[var(--mm-text2)]">
              Leave empty to save subtitles next to your media file. Subtitles
              are named to match — Movie.2023.en.srt alongside Movie.2023.mkv.
            </p>
          </div>
          <div className="space-y-2">
            <MmOnOffSwitch
              id="subber-exclude-hi"
              layout="inline"
              label="Exclude hearing impaired"
              enabled={excludeHi}
              disabled={dis}
              onChange={(v) => {
                setExcludeHi(v);
                setPrefsDirty(true);
              }}
            />
            <p className="max-w-xl text-xs text-[var(--mm-text2)]">
              When on, skips subtitles with sound descriptions like [DOOR
              CREAKS] or [TENSE MUSIC].
            </p>
          </div>
          <div className="space-y-2">
            <MmOnOffSwitch
              id="subber-enabled"
              layout="inline"
              label="Enable Subber"
              enabled={enabled}
              disabled={dis}
              onChange={(v) => {
                setEnabled(v);
                setPrefsDirty(true);
              }}
            />
            <p className="max-w-xl text-xs text-[var(--mm-text2)]">
              {enabled
                ? "Subber is on. Searches run on import and schedule."
                : "Subber is off. No automatic searches will run."}
            </p>
          </div>
        </SubberSettingsSection>

        <SubberSettingsSection
          className="order-4 lg:order-none"
          eyebrow="Automation"
          title="Subtitle upgrade"
          description="Periodically re-search media that already has subtitles looking for better matches."
          footer={
            <>
              <button
                type="button"
                className={mmActionButtonClass({
                  variant: upgradeDirty ? "primary" : "secondary",
                  disabled: dis || !upgradeDirty,
                })}
                disabled={dis || !upgradeDirty}
                onClick={() => void saveUpgradePrefs()}
              >
                Save upgrade settings
              </button>
              <SaveFeedback ok={saveUpgrade.ok} err={saveUpgrade.err} />
            </>
          }
        >
          <MmOnOffSwitch
            id="subber-up-master"
            label="Enable subtitle upgrades"
            enabled={upEn}
            disabled={dis}
            onChange={(v) => {
              setUpEn(v);
              setUpgradeDirty(true);
            }}
          />
          <p className="text-xs text-[var(--mm-text2)]">
            {upEn
              ? "Subtitle upgrade is on."
              : "Subtitle upgrade is off. Subtitles already downloaded will not be re-searched."}
          </p>
          {upEn ? (
            <label className="block text-sm text-[var(--mm-text2)]">
              Check every (minutes)
              <input
                type="number"
                min={60}
                max={525600}
                className="mm-input mt-1 w-full max-w-xs"
                value={upIntervalMin}
                onChange={(e) => {
                  setUpIntervalMin(
                    Math.max(
                      60,
                      Math.min(525600, Number(e.target.value) || 60),
                    ),
                  );
                  setUpgradeDirty(true);
                }}
                disabled={dis}
              />
            </label>
          ) : null}
        </SubberSettingsSection>
      </div>
    </div>
  );
}
