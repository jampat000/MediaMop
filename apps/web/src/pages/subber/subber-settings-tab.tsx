import { useEffect, useState, type ReactNode } from "react";
import { fetchCsrfToken } from "../../lib/api/auth-api";
import { MmOnOffSwitch } from "../../components/ui/mm-on-off-switch";
import { mmActionButtonClass } from "../../lib/ui/mm-control-roles";
import { SUBBER_LANGUAGE_OPTIONS, subberLanguageLabel } from "../../lib/subber/subber-languages";
import type { SubberProviderOut, SubberProviderPutIn } from "../../lib/subber/subber-api";
import {
  usePutSubberProviderMutation,
  usePutSubberSettingsMutation,
  useSubberLibrarySyncMoviesMutation,
  useSubberLibrarySyncTvMutation,
  useSubberProvidersQuery,
  useSubberSettingsQuery,
  useSubberTestOpensubtitlesMutation,
  useSubberTestProviderMutation,
  useSubberTestRadarrMutation,
  useSubberTestSonarrMutation,
} from "../../lib/subber/subber-queries";

const MASK = "\u2022".repeat(10);

type ConnectionOutcome = null | "ok" | "fail";

type ConnectionCheckState = {
  outcome: ConnectionOutcome;
  at: string | null;
  detail: string;
  quotaNote?: string;
};

const initialCheck: ConnectionCheckState = { outcome: null, at: null, detail: "" };

function providerNeedsConfigureButton(p: SubberProviderOut): boolean {
  if (p.provider_key === "subscene") return false;
  if (p.requires_account) return true;
  if (p.provider_key === "podnapisi") return true;
  return false;
}

function formatLastCheck(iso: string | null): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

function parseOpensubtitlesQuota(message: string): { rest: string; quota?: string } {
  const lower = message.toLowerCase();
  const key = "remaining quota:";
  const idx = lower.indexOf(key);
  if (idx === -1) return { rest: message };
  const quotaPart = message.slice(idx + key.length).trim().replace(/\.\s*$/, "");
  const rest = message.slice(0, idx).trim() || "Connected.";
  return { rest, quota: `Remaining quota: ${quotaPart}` };
}

function ConnectionStatusPanel({
  check,
  idleHelper,
}: {
  check: ConnectionCheckState;
  idleHelper?: string;
}) {
  const main =
    check.outcome === null ? "Not connected yet" : check.outcome === "ok" ? "Connected" : "Connection failed";
  return (
    <div className="mt-4 rounded-md border border-[var(--mm-border)] bg-[var(--mm-card-bg)] p-3.5 text-sm text-[var(--mm-text2)]">
      <p className="text-sm font-medium text-[var(--mm-text)]">{main}</p>
      <p className="mt-1 text-xs text-[var(--mm-text2)]">
        Last completed check: <span className="font-medium text-[var(--mm-text)]">{formatLastCheck(check.at)}</span>
      </p>
      {check.outcome === "ok" && check.quotaNote ? <p className="mt-1 text-xs text-[var(--mm-text2)]">{check.quotaNote}</p> : null}
      {check.outcome === "ok" && check.detail && !check.quotaNote ? (
        <p className="mt-1 text-xs text-[var(--mm-text2)]">{check.detail}</p>
      ) : null}
      {check.outcome === "fail" && check.detail ? <p className="mt-1 text-xs text-red-400">{check.detail}</p> : null}
      {check.outcome === null && idleHelper ? <p className="mt-2 text-xs text-[var(--mm-text2)]">{idleHelper}</p> : null}
    </div>
  );
}

function WebhookUrlField({
  id,
  helper,
  value,
  disabled,
}: {
  id: string;
  helper: string;
  value: string;
  disabled: boolean;
}) {
  const [copied, setCopied] = useState(false);
  async function copy() {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      /* ignore */
    }
  }
  return (
    <div className="mt-4">
      <label className="block text-sm font-medium text-[var(--mm-text)]" htmlFor={id}>
        Webhook URL
      </label>
      <p className="mt-1 text-xs text-[var(--mm-text2)]">{helper}</p>
      <div className="mt-1 flex max-w-3xl flex-wrap gap-2">
        <input id={id} readOnly className="mm-input min-w-0 flex-1 font-mono text-xs" value={value} />
        <button
          type="button"
          className={mmActionButtonClass({ variant: "secondary", disabled })}
          disabled={disabled}
          onClick={() => void copy()}
        >
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
    </div>
  );
}

function SaveFeedback({ ok, err }: { ok: boolean; err: string | null }) {
  if (err) {
    return (
      <p className="mt-2 text-sm text-red-400" role="alert">
        {err}
      </p>
    );
  }
  if (ok) {
    return (
      <p className="mt-2 text-sm text-emerald-600" role="status">
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
  "data-testid": dataTestId,
}: {
  eyebrow?: string;
  title: string;
  description?: ReactNode;
  children: ReactNode;
  "data-testid"?: string;
}) {
  return (
    <section
      className="overflow-hidden rounded-lg border border-[var(--mm-border)] bg-[var(--mm-card-bg)] shadow-sm"
      data-testid={dataTestId}
    >
      <header className="border-b border-[var(--mm-border)] bg-black/10 px-5 py-4">
        {eyebrow ? (
          <p className="text-[0.7rem] font-semibold uppercase tracking-[0.12em] text-[var(--mm-text2)]">{eyebrow}</p>
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
        {description ? <div className="mt-2 text-sm leading-relaxed text-[var(--mm-text2)]">{description}</div> : null}
      </header>
      <div className="space-y-5 px-5 py-5">{children}</div>
    </section>
  );
}

function SubberSettingsSubsection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="rounded-md border border-[var(--mm-border)] bg-black/[0.06] p-4">
      <h3 className="mb-3 text-sm font-semibold text-[var(--mm-text)]">{title}</h3>
      <div className="space-y-3">{children}</div>
    </div>
  );
}

export function SubberSettingsTab({ canOperate }: { canOperate: boolean }) {
  const q = useSubberSettingsQuery();
  const pq = useSubberProvidersQuery();
  const put = usePutSubberSettingsMutation();
  const putProv = usePutSubberProviderMutation();
  const testOs = useSubberTestOpensubtitlesMutation();
  const testSon = useSubberTestSonarrMutation();
  const testRad = useSubberTestRadarrMutation();
  const testProv = useSubberTestProviderMutation();
  const syncTv = useSubberLibrarySyncTvMutation();
  const syncMovies = useSubberLibrarySyncMoviesMutation();

  const [osUser, setOsUser] = useState("");
  const [osPass, setOsPass] = useState("");
  const [osKey, setOsKey] = useState("");
  const [showOsPass, setShowOsPass] = useState(false);
  const [showOsKey, setShowOsKey] = useState(false);
  const [sonUrl, setSonUrl] = useState("");
  const [sonKey, setSonKey] = useState("");
  const [showSonKey, setShowSonKey] = useState(false);
  const [radUrl, setRadUrl] = useState("");
  const [radKey, setRadKey] = useState("");
  const [showRadKey, setShowRadKey] = useState(false);
  const [langs, setLangs] = useState<string[]>(["en"]);
  const [folder, setFolder] = useState("");
  const [enabled, setEnabled] = useState(false);

  const [osCheck, setOsCheck] = useState<ConnectionCheckState>(initialCheck);
  const [sonCheck, setSonCheck] = useState<ConnectionCheckState>(initialCheck);
  const [radCheck, setRadCheck] = useState<ConnectionCheckState>(initialCheck);

  const [tvSyncOk, setTvSyncOk] = useState(false);
  const [moviesSyncOk, setMoviesSyncOk] = useState(false);
  const [tvSyncErr, setTvSyncErr] = useState<string | null>(null);
  const [moviesSyncErr, setMoviesSyncErr] = useState<string | null>(null);

  const [excludeHi, setExcludeHi] = useState(false);
  const [adaptEn, setAdaptEn] = useState(true);
  const [adaptMax, setAdaptMax] = useState(3);
  const [adaptDelayH, setAdaptDelayH] = useState(168);
  const [adaptPerm, setAdaptPerm] = useState(10);
  const [sonMapEn, setSonMapEn] = useState(false);
  const [sonArr, setSonArr] = useState("");
  const [sonSub, setSonSub] = useState("");
  const [radMapEn, setRadMapEn] = useState(false);
  const [radArr, setRadArr] = useState("");
  const [radSub, setRadSub] = useState("");

  const [provUser, setProvUser] = useState<Record<string, string>>({});
  const [provPass, setProvPass] = useState<Record<string, string>>({});
  const [provKey, setProvKey] = useState<Record<string, string>>({});
  const [provPri, setProvPri] = useState<Record<string, number>>({});
  const [provMsg, setProvMsg] = useState<Record<string, string | null>>({});

  const [saveOs, setSaveOs] = useState({ ok: false, err: null as string | null });
  const [saveSon, setSaveSon] = useState({ ok: false, err: null as string | null });
  const [saveRad, setSaveRad] = useState({ ok: false, err: null as string | null });
  const [saveLang, setSaveLang] = useState({ ok: false, err: null as string | null });
  const [savePrefs, setSavePrefs] = useState({ ok: false, err: null as string | null });
  const [saveFreq, setSaveFreq] = useState({ ok: false, err: null as string | null });
  const [saveSonMap, setSaveSonMap] = useState({ ok: false, err: null as string | null });
  const [saveRadMap, setSaveRadMap] = useState({ ok: false, err: null as string | null });
  const [expandedProviderKey, setExpandedProviderKey] = useState<string | null>(null);

  useEffect(() => {
    const d = q.data;
    if (!d) return;
    setOsUser(d.opensubtitles_username ?? "");
    setOsPass("");
    setOsKey("");
    setSonUrl(d.sonarr_base_url ?? "");
    setSonKey("");
    setRadUrl(d.radarr_base_url ?? "");
    setRadKey("");
    setLangs(d.language_preferences?.length ? [...d.language_preferences] : ["en"]);
    setFolder(d.subtitle_folder ?? "");
    setEnabled(d.enabled);
    setExcludeHi(Boolean(d.exclude_hearing_impaired));
    setAdaptEn(Boolean(d.adaptive_searching_enabled));
    setAdaptMax(d.adaptive_searching_max_attempts ?? 3);
    setAdaptDelayH(d.adaptive_searching_delay_hours ?? 168);
    setAdaptPerm(d.permanent_skip_after_attempts ?? 10);
    setSonMapEn(Boolean(d.sonarr_path_mapping_enabled));
    setSonArr(d.sonarr_path_sonarr ?? "");
    setSonSub(d.sonarr_path_subber ?? "");
    setRadMapEn(Boolean(d.radarr_path_mapping_enabled));
    setRadArr(d.radarr_path_radarr ?? "");
    setRadSub(d.radarr_path_subber ?? "");
  }, [q.data]);

  useEffect(() => {
    if (!pq.data) return;
    setProvPri((prev) => {
      const n = { ...prev };
      for (const p of pq.data) {
        if (n[p.provider_key] === undefined) n[p.provider_key] = p.priority;
      }
      return n;
    });
  }, [pq.data]);

  const base = typeof window !== "undefined" ? window.location.origin : "";
  const sonHook = `${base}/api/v1/subber/webhook/sonarr`;
  const radHook = `${base}/api/v1/subber/webhook/radarr`;
  const dis = !canOperate || put.isPending;

  function flashSave(setter: typeof setSaveOs) {
    setter({ ok: true, err: null });
    window.setTimeout(() => setter({ ok: false, err: null }), 2500);
  }

  async function saveOpenSubtitles() {
    setSaveOs({ ok: false, err: null });
    try {
      const csrf_token = await fetchCsrfToken();
      const body: Parameters<typeof put.mutateAsync>[0] = {
        csrf_token,
        opensubtitles_username: osUser.trim(),
      };
      if (osPass.trim()) body.opensubtitles_password = osPass;
      if (osKey.trim()) body.opensubtitles_api_key = osKey;
      await put.mutateAsync(body);
      flashSave(setSaveOs);
    } catch (e) {
      setSaveOs({ ok: false, err: (e as Error).message });
    }
  }

  async function saveSonarr() {
    setSaveSon({ ok: false, err: null });
    try {
      const csrf_token = await fetchCsrfToken();
      const body: Parameters<typeof put.mutateAsync>[0] = { csrf_token, sonarr_base_url: sonUrl.trim() };
      if (sonKey.trim()) body.sonarr_api_key = sonKey;
      await put.mutateAsync(body);
      flashSave(setSaveSon);
    } catch (e) {
      setSaveSon({ ok: false, err: (e as Error).message });
    }
  }

  async function saveRadarr() {
    setSaveRad({ ok: false, err: null });
    try {
      const csrf_token = await fetchCsrfToken();
      const body: Parameters<typeof put.mutateAsync>[0] = { csrf_token, radarr_base_url: radUrl.trim() };
      if (radKey.trim()) body.radarr_api_key = radKey;
      await put.mutateAsync(body);
      flashSave(setSaveRad);
    } catch (e) {
      setSaveRad({ ok: false, err: (e as Error).message });
    }
  }

  async function saveLanguages() {
    setSaveLang({ ok: false, err: null });
    try {
      const csrf_token = await fetchCsrfToken();
      await put.mutateAsync({ csrf_token, language_preferences: langs });
      flashSave(setSaveLang);
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
    } catch (e) {
      setSaveFreq({ ok: false, err: (e as Error).message });
    }
  }

  async function saveSonarrPathMapping() {
    setSaveSonMap({ ok: false, err: null });
    try {
      const csrf_token = await fetchCsrfToken();
      await put.mutateAsync({
        csrf_token,
        sonarr_path_mapping_enabled: sonMapEn,
        sonarr_path_sonarr: sonArr.trim(),
        sonarr_path_subber: sonSub.trim(),
      });
      flashSave(setSaveSonMap);
    } catch (e) {
      setSaveSonMap({ ok: false, err: (e as Error).message });
    }
  }

  async function saveRadarrPathMapping() {
    setSaveRadMap({ ok: false, err: null });
    try {
      const csrf_token = await fetchCsrfToken();
      await put.mutateAsync({
        csrf_token,
        radarr_path_mapping_enabled: radMapEn,
        radarr_path_radarr: radArr.trim(),
        radarr_path_subber: radSub.trim(),
      });
      flashSave(setSaveRadMap);
    } catch (e) {
      setSaveRadMap({ ok: false, err: (e as Error).message });
    }
  }

  async function runTestOs() {
    const at = new Date().toISOString();
    try {
      const r = await testOs.mutateAsync();
      if (r.ok) {
        const parsed = parseOpensubtitlesQuota(r.message || "");
        setOsCheck({
          outcome: "ok",
          at,
          detail: parsed.rest,
          quotaNote: parsed.quota,
        });
      } else {
        setOsCheck({ outcome: "fail", at, detail: r.message || "Unknown error" });
      }
    } catch (e) {
      setOsCheck({ outcome: "fail", at, detail: (e as Error).message });
    }
  }

  async function runTestSon() {
    const at = new Date().toISOString();
    try {
      const r = await testSon.mutateAsync();
      if (r.ok) {
        setSonCheck({ outcome: "ok", at, detail: r.message || "OK" });
      } else {
        setSonCheck({ outcome: "fail", at, detail: r.message || "Unknown error" });
      }
    } catch (e) {
      setSonCheck({ outcome: "fail", at, detail: (e as Error).message });
    }
  }

  async function runTestRad() {
    const at = new Date().toISOString();
    try {
      const r = await testRad.mutateAsync();
      if (r.ok) {
        setRadCheck({ outcome: "ok", at, detail: r.message || "OK" });
      } else {
        setRadCheck({ outcome: "fail", at, detail: r.message || "Unknown error" });
      }
    } catch (e) {
      setRadCheck({ outcome: "fail", at, detail: (e as Error).message });
    }
  }

  async function saveProviderRow(pk: string, enabledP: boolean, priority: number) {
    const csrf_token = await fetchCsrfToken();
    const body: SubberProviderPutIn = { csrf_token, enabled: enabledP, priority };
    const u = provUser[pk]?.trim();
    const p = provPass[pk]?.trim();
    const k = provKey[pk]?.trim();
    if (u) body.username = u;
    if (p) body.password = p;
    if (k) body.api_key = k;
    await putProv.mutateAsync({ providerKey: pk, body });
  }

  async function saveExpandedProvider(pk: string, enabledP: boolean, priority: number) {
    await saveProviderRow(pk, enabledP, priority);
    setExpandedProviderKey(null);
  }

  async function runProvTest(pk: string) {
    setProvMsg((m) => ({ ...m, [pk]: null }));
    try {
      const r = await testProv.mutateAsync(pk);
      setProvMsg((m) => ({ ...m, [pk]: r.ok ? "Connected" : r.message }));
    } catch (e) {
      setProvMsg((m) => ({ ...m, [pk]: (e as Error).message }));
    }
  }

  if (q.isLoading) return <p className="text-sm text-[var(--mm-text2)]">Loading settings…</p>;
  if (q.isError) return <p className="text-sm text-red-600">{(q.error as Error).message}</p>;

  const sonHint = (q.data?.fetcher_sonarr_base_url_hint || "").trim();
  const radHint = (q.data?.fetcher_radarr_base_url_hint || "").trim();
  const sorted = [...(pq.data ?? [])].sort((a, b) => a.priority - b.priority || a.provider_key.localeCompare(b.provider_key));

  return (
    <div className="space-y-8" data-testid="subber-settings-tab">
      <SubberSettingsSection
        eyebrow="Subtitles account"
        title="OpenSubtitles"
        description="Sign up at opensubtitles.com for a free account and API key. Subber shows your remaining download quota when you test the connection."
      >
        <SubberSettingsSubsection title="Credentials">
          <label className="block text-sm font-medium text-[var(--mm-text)]" htmlFor="subber-os-user">
            Username
          </label>
          <input
            id="subber-os-user"
            className="mm-input mt-1 w-full max-w-md"
            value={osUser}
            disabled={dis}
            onChange={(e) => setOsUser(e.target.value)}
          />
          <label className="mt-3 block text-sm font-medium text-[var(--mm-text)]" htmlFor="subber-os-pass">
            Password {q.data?.opensubtitles_password_set ? <span className="text-xs font-normal text-[var(--mm-text2)]">(leave blank to keep)</span> : null}
          </label>
          <div className="mt-1 flex max-w-md gap-2">
            <input
              id="subber-os-pass"
              className="mm-input flex-1"
              type={showOsPass ? "text" : "password"}
              value={osPass}
              placeholder={q.data?.opensubtitles_password_set ? MASK : ""}
              disabled={dis}
              onChange={(e) => setOsPass(e.target.value)}
            />
            <button type="button" className={mmActionButtonClass({ variant: "secondary" })} onClick={() => setShowOsPass(!showOsPass)}>
              {showOsPass ? "Hide" : "Show"}
            </button>
          </div>
          <label className="mt-3 block text-sm font-medium text-[var(--mm-text)]" htmlFor="subber-os-key">
            API key
          </label>
          <div className="mt-1 flex max-w-md gap-2">
            <input
              id="subber-os-key"
              className="mm-input flex-1"
              type={showOsKey ? "text" : "password"}
              value={osKey}
              placeholder={q.data?.opensubtitles_api_key_set ? MASK : ""}
              disabled={dis}
              onChange={(e) => setOsKey(e.target.value)}
            />
            <button type="button" className={mmActionButtonClass({ variant: "secondary" })} onClick={() => setShowOsKey(!showOsKey)}>
              {showOsKey ? "Hide" : "Show"}
            </button>
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            <button
              type="button"
              className={mmActionButtonClass({ variant: "primary", disabled: dis })}
              disabled={dis}
              onClick={() => void saveOpenSubtitles()}
              data-testid="subber-save-opensubtitles"
            >
              Save OpenSubtitles
            </button>
            <button
              type="button"
              className={mmActionButtonClass({ variant: "secondary", disabled: dis || testOs.isPending })}
              disabled={dis || testOs.isPending}
              onClick={() => void runTestOs()}
              data-testid="subber-test-opensubtitles"
            >
              Test connection
            </button>
          </div>
          <SaveFeedback ok={saveOs.ok} err={saveOs.err} />
          <ConnectionStatusPanel
            check={osCheck}
            idleHelper="Run a test to verify your credentials and see your remaining download quota."
          />
        </SubberSettingsSubsection>
      </SubberSettingsSection>

      <SubberSettingsSection
        eyebrow="TV library"
        title="Sonarr"
        description="Connect Sonarr so Subber can read your TV library, react to imports, and map file paths when MediaMop runs in a different container or host."
        data-testid="subber-settings-sonarr"
      >
        <SubberSettingsSubsection title="Connection">
          {sonHint ? (
            <p className="text-sm text-[var(--mm-text2)]">
              Fetcher already uses <span className="font-mono text-[var(--mm-text)]">{sonHint}</span> — you can paste the same base URL here.
            </p>
          ) : null}
          <label className="block text-sm font-medium text-[var(--mm-text)]" htmlFor="subber-son-url">
            Base URL
          </label>
          <input
            id="subber-son-url"
            className="mm-input mt-1 w-full max-w-xl font-mono text-sm"
            value={sonUrl}
            disabled={dis}
            onChange={(e) => setSonUrl(e.target.value)}
            placeholder="http://127.0.0.1:8989"
          />
          <label className="mt-3 block text-sm font-medium text-[var(--mm-text)]" htmlFor="subber-son-key">
            API key
          </label>
          <div className="mt-1 flex max-w-xl gap-2">
            <input
              id="subber-son-key"
              className="mm-input min-w-0 flex-1 font-mono text-sm"
              type={showSonKey ? "text" : "password"}
              value={sonKey}
              placeholder={q.data?.sonarr_api_key_set ? MASK : ""}
              disabled={dis}
              onChange={(e) => setSonKey(e.target.value)}
            />
            <button type="button" className={mmActionButtonClass({ variant: "secondary" })} onClick={() => setShowSonKey(!showSonKey)}>
              {showSonKey ? "Hide" : "Show"}
            </button>
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            <button
              type="button"
              className={mmActionButtonClass({ variant: "primary", disabled: dis })}
              disabled={dis}
              onClick={() => void saveSonarr()}
              data-testid="subber-save-sonarr"
            >
              Save connection
            </button>
            <button
              type="button"
              className={mmActionButtonClass({ variant: "secondary", disabled: dis || testSon.isPending })}
              disabled={dis || testSon.isPending}
              onClick={() => void runTestSon()}
              data-testid="subber-test-sonarr"
            >
              Test Sonarr
            </button>
          </div>
          <SaveFeedback ok={saveSon.ok} err={saveSon.err} />
          <ConnectionStatusPanel check={sonCheck} idleHelper="Save your URL and API key, then run a test to confirm Sonarr is reachable." />
        </SubberSettingsSubsection>

        <SubberSettingsSubsection title="Webhook">
          <WebhookUrlField
            id="subber-webhook-sonarr"
            helper="In Sonarr: Settings → Connect → Webhook. Trigger: On Download. Subber searches as soon as Sonarr imports a file."
            value={sonHook}
            disabled={dis}
          />
        </SubberSettingsSubsection>

        <SubberSettingsSubsection title="Library sync">
          <button
            type="button"
            className={mmActionButtonClass({ variant: "secondary", disabled: dis || syncTv.isPending })}
            disabled={dis || syncTv.isPending}
            onClick={() => {
              setTvSyncOk(false);
              setTvSyncErr(null);
              void syncTv.mutate(undefined, {
                onSuccess: () => setTvSyncOk(true),
                onError: (e) => setTvSyncErr((e as Error).message),
              });
            }}
            data-testid="subber-sync-tv-library"
          >
            {syncTv.isPending ? "Syncing…" : "Sync TV library from Sonarr"}
          </button>
          <p className="text-xs text-[var(--mm-text2)]">
            One-time pull of your Sonarr library so the TV tab shows coverage. Check the Jobs tab for progress.
          </p>
          {tvSyncOk ? (
            <p className="text-xs text-[var(--mm-text)]">
              TV library sync started — your TV tab will populate shortly. Check the Jobs tab for progress.
            </p>
          ) : null}
          {tvSyncErr ? (
            <p className="text-xs text-red-400" role="alert">
              {tvSyncErr}
            </p>
          ) : null}
        </SubberSettingsSubsection>

        <SubberSettingsSubsection title="Path mapping">
          <p className="text-xs text-[var(--mm-text2)]">
            Only if Sonarr and MediaMop see different paths (for example Docker bind mounts). Leave off when everything runs on one machine.
          </p>
          <MmOnOffSwitch id="subber-son-map" label="Enable Sonarr path mapping" enabled={sonMapEn} disabled={dis} onChange={setSonMapEn} />
          {sonMapEn ? (
            <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
              <label className="block min-w-0 flex-1 text-sm text-[var(--mm-text2)]">
                Path as Sonarr reports it
                <input className="mm-input mt-1 w-full font-mono text-sm" value={sonArr} disabled={dis} onChange={(e) => setSonArr(e.target.value)} />
              </label>
              <label className="block min-w-0 flex-1 text-sm text-[var(--mm-text2)]">
                Path as MediaMop sees it
                <input className="mm-input mt-1 w-full font-mono text-sm" value={sonSub} disabled={dis} onChange={(e) => setSonSub(e.target.value)} />
              </label>
            </div>
          ) : null}
          <button
            type="button"
            className={mmActionButtonClass({ variant: "primary", disabled: dis })}
            disabled={dis}
            onClick={() => void saveSonarrPathMapping()}
            data-testid="subber-save-sonarr-path-mapping"
          >
            Save Sonarr path mapping
          </button>
          <SaveFeedback ok={saveSonMap.ok} err={saveSonMap.err} />
        </SubberSettingsSubsection>
      </SubberSettingsSection>

      <SubberSettingsSection
        eyebrow="Movies library"
        title="Radarr"
        description="Connect Radarr for movie imports, webhooks, and optional path translation when Subber does not share the same filesystem view as Radarr."
        data-testid="subber-settings-radarr"
      >
        <SubberSettingsSubsection title="Connection">
          {radHint ? (
            <p className="text-sm text-[var(--mm-text2)]">
              Fetcher already uses <span className="font-mono text-[var(--mm-text)]">{radHint}</span> — you can paste the same base URL here.
            </p>
          ) : null}
          <label className="block text-sm font-medium text-[var(--mm-text)]" htmlFor="subber-rad-url">
            Base URL
          </label>
          <input
            id="subber-rad-url"
            className="mm-input mt-1 w-full max-w-xl font-mono text-sm"
            value={radUrl}
            disabled={dis}
            onChange={(e) => setRadUrl(e.target.value)}
            placeholder="http://127.0.0.1:7878"
          />
          <label className="mt-3 block text-sm font-medium text-[var(--mm-text)]" htmlFor="subber-rad-key">
            API key
          </label>
          <div className="mt-1 flex max-w-xl gap-2">
            <input
              id="subber-rad-key"
              className="mm-input min-w-0 flex-1 font-mono text-sm"
              type={showRadKey ? "text" : "password"}
              value={radKey}
              placeholder={q.data?.radarr_api_key_set ? MASK : ""}
              disabled={dis}
              onChange={(e) => setRadKey(e.target.value)}
            />
            <button type="button" className={mmActionButtonClass({ variant: "secondary" })} onClick={() => setShowRadKey(!showRadKey)}>
              {showRadKey ? "Hide" : "Show"}
            </button>
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            <button
              type="button"
              className={mmActionButtonClass({ variant: "primary", disabled: dis })}
              disabled={dis}
              onClick={() => void saveRadarr()}
              data-testid="subber-save-radarr"
            >
              Save connection
            </button>
            <button
              type="button"
              className={mmActionButtonClass({ variant: "secondary", disabled: dis || testRad.isPending })}
              disabled={dis || testRad.isPending}
              onClick={() => void runTestRad()}
              data-testid="subber-test-radarr"
            >
              Test Radarr
            </button>
          </div>
          <SaveFeedback ok={saveRad.ok} err={saveRad.err} />
          <ConnectionStatusPanel check={radCheck} idleHelper="Save your URL and API key, then run a test to confirm Radarr is reachable." />
        </SubberSettingsSubsection>

        <SubberSettingsSubsection title="Webhook">
          <WebhookUrlField
            id="subber-webhook-radarr"
            helper="In Radarr: Settings → Connect → Webhook. Trigger: On Download. Subber searches as soon as Radarr imports a file."
            value={radHook}
            disabled={dis}
          />
        </SubberSettingsSubsection>

        <SubberSettingsSubsection title="Library sync">
          <button
            type="button"
            className={mmActionButtonClass({ variant: "secondary", disabled: dis || syncMovies.isPending })}
            disabled={dis || syncMovies.isPending}
            onClick={() => {
              setMoviesSyncOk(false);
              setMoviesSyncErr(null);
              void syncMovies.mutate(undefined, {
                onSuccess: () => setMoviesSyncOk(true),
                onError: (e) => setMoviesSyncErr((e as Error).message),
              });
            }}
            data-testid="subber-sync-movies-library"
          >
            {syncMovies.isPending ? "Syncing…" : "Sync Movies library from Radarr"}
          </button>
          <p className="text-xs text-[var(--mm-text2)]">
            One-time pull of your Radarr library so the Movies tab shows coverage. Check the Jobs tab for progress.
          </p>
          {moviesSyncOk ? (
            <p className="text-xs text-[var(--mm-text)]">
              Movies library sync started — your Movies tab will populate shortly. Check the Jobs tab for progress.
            </p>
          ) : null}
          {moviesSyncErr ? (
            <p className="text-xs text-red-400" role="alert">
              {moviesSyncErr}
            </p>
          ) : null}
        </SubberSettingsSubsection>

        <SubberSettingsSubsection title="Path mapping">
          <p className="text-xs text-[var(--mm-text2)]">
            Only if Radarr and MediaMop see different paths. Leave off when everything runs on one machine.
          </p>
          <MmOnOffSwitch id="subber-rad-map" label="Enable Radarr path mapping" enabled={radMapEn} disabled={dis} onChange={setRadMapEn} />
          {radMapEn ? (
            <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
              <label className="block min-w-0 flex-1 text-sm text-[var(--mm-text2)]">
                Path as Radarr reports it
                <input className="mm-input mt-1 w-full font-mono text-sm" value={radArr} disabled={dis} onChange={(e) => setRadArr(e.target.value)} />
              </label>
              <label className="block min-w-0 flex-1 text-sm text-[var(--mm-text2)]">
                Path as MediaMop sees it
                <input className="mm-input mt-1 w-full font-mono text-sm" value={radSub} disabled={dis} onChange={(e) => setRadSub(e.target.value)} />
              </label>
            </div>
          ) : null}
          <button
            type="button"
            className={mmActionButtonClass({ variant: "primary", disabled: dis })}
            disabled={dis}
            onClick={() => void saveRadarrPathMapping()}
            data-testid="subber-save-radarr-path-mapping"
          >
            Save Radarr path mapping
          </button>
          <SaveFeedback ok={saveRadMap.ok} err={saveRadMap.err} />
        </SubberSettingsSubsection>
      </SubberSettingsSection>

      <SubberSettingsSection
        eyebrow="Search order"
        title="Subtitle languages"
        description="Subber tries languages in this order. If the first is not found it tries the next automatically."
      >
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
                onClick={() => setLangs(langs.filter((_, i) => i !== idx))}
              >
                ×
              </button>
            </span>
          ))}
        </div>
        <label className="block text-sm text-[var(--mm-text2)]">
          Add language
          <select
            className="mm-input mt-1 block max-w-xs"
            defaultValue=""
            disabled={dis}
            onChange={(e) => {
              const v = e.target.value;
              if (!v || langs.includes(v)) return;
              setLangs([...langs, v]);
              e.target.value = "";
            }}
          >
            <option value="">Choose…</option>
            {SUBBER_LANGUAGE_OPTIONS.filter((o) => !langs.includes(o.code)).map((o) => (
              <option key={o.code} value={o.code}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          className={mmActionButtonClass({ variant: "primary", disabled: dis })}
          disabled={dis}
          onClick={() => void saveLanguages()}
          data-testid="subber-save-languages"
        >
          Save languages
        </button>
        <SaveFeedback ok={saveLang.ok} err={saveLang.err} />
      </SubberSettingsSection>

      <SubberSettingsSection
        eyebrow="Files & behavior"
        title="Preferences"
        description="Where subtitles are written, optional filtering, and the master switch for automatic searches."
      >
        <div>
          <label className="block text-sm font-medium text-[var(--mm-text)]" htmlFor="subber-subtitle-folder">
            Subtitle folder
          </label>
          <input
            id="subber-subtitle-folder"
            className="mm-input mt-1 w-full max-w-xl"
            value={folder}
            disabled={dis}
            onChange={(e) => setFolder(e.target.value)}
            placeholder="Same folder as media file"
          />
          <p className="mt-1 text-xs text-[var(--mm-text2)]">
            Leave empty to save subtitles next to your media file. Subtitles are named to match — Movie.2023.en.srt alongside
            Movie.2023.mkv.
          </p>
        </div>
        <div className="space-y-2">
          <MmOnOffSwitch
            id="subber-exclude-hi"
            layout="inline"
            label="Exclude hearing impaired"
            enabled={excludeHi}
            disabled={dis}
            onChange={setExcludeHi}
          />
          <p className="max-w-xl text-xs text-[var(--mm-text2)]">
            When on, skips subtitles with sound descriptions like [DOOR CREAKS] or [TENSE MUSIC].
          </p>
        </div>
        <div className="space-y-2">
          <MmOnOffSwitch id="subber-enabled" layout="inline" label="Enable Subber" enabled={enabled} disabled={dis} onChange={setEnabled} />
          <p className="max-w-xl text-xs text-[var(--mm-text2)]">
            {enabled
              ? "Subber is on. Searches run on import and schedule."
              : "Subber is off. No automatic searches will run."}
          </p>
        </div>
        <button
          type="button"
          className={mmActionButtonClass({ variant: "primary", disabled: dis })}
          disabled={dis}
          onClick={() => void savePreferences()}
          data-testid="subber-save-subtitle-folder"
        >
          Save preferences
        </button>
        <SaveFeedback ok={savePrefs.ok} err={savePrefs.err} />
      </SubberSettingsSection>

      <SubberSettingsSection
        eyebrow="Automation"
        title="Adaptive searching"
        description="Back off automatically when subtitles are not found so repeated searches do not burn through your daily download quota."
      >
        <MmOnOffSwitch id="subber-adapt" label="Enable adaptive searching" enabled={adaptEn} disabled={dis} onChange={setAdaptEn} />
        {adaptEn ? (
          <div className="space-y-3">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-sm text-[var(--mm-text2)]">Back off after</span>
              <input
                type="number"
                className="mm-input max-w-24"
                min={1}
                max={100}
                value={adaptMax}
                disabled={dis}
                onChange={(e) => setAdaptMax(Number(e.target.value) || 1)}
              />
              <span className="text-sm text-[var(--mm-text2)]">failed attempts</span>
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
                onChange={(e) => setAdaptDelayH(Number(e.target.value) || 1)}
              />
              <span className="text-sm text-[var(--mm-text2)]">hours before retrying</span>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-sm text-[var(--mm-text2)]">Give up after</span>
              <input
                type="number"
                className="mm-input max-w-24"
                min={1}
                max={10000}
                value={adaptPerm}
                disabled={dis}
                onChange={(e) => setAdaptPerm(Number(e.target.value) || 1)}
              />
              <span className="text-sm text-[var(--mm-text2)]">total attempts</span>
            </div>
          </div>
        ) : null}
        <button type="button" className={mmActionButtonClass({ variant: "primary", disabled: dis })} disabled={dis} onClick={() => void saveSearchFrequency()}>
          Save adaptive settings
        </button>
        <SaveFeedback ok={saveFreq.ok} err={saveFreq.err} />
      </SubberSettingsSection>

      <SubberSettingsSection
        eyebrow="Sources"
        title="Subtitle providers"
        description="Subber walks this list in order until a subtitle is found. Lower number = searched first. Keep at least one provider enabled."
        data-testid="subber-providers-section"
      >
        {pq.isLoading ? <p className="text-sm text-[var(--mm-text2)]">Loading providers…</p> : null}
        <ul className="divide-y divide-[var(--mm-border)] rounded-md border border-[var(--mm-border)] bg-black/10">
          {sorted.map((p) => {
            const pri = provPri[p.provider_key] ?? p.priority;
            const provMsgText = provMsg[p.provider_key];
            const showCfg = providerNeedsConfigureButton(p);
            const expanded = expandedProviderKey === p.provider_key;
            let statusEl: ReactNode;
            if (provMsgText) {
              statusEl =
                provMsgText === "Connected" ? (
                  <span className="text-xs font-medium text-emerald-600">{provMsgText}</span>
                ) : (
                  <span className="max-w-[14rem] truncate text-xs text-[var(--mm-text2)]" title={provMsgText}>
                    {provMsgText}
                  </span>
                );
            } else if (p.provider_key === "subscene") {
              statusEl = <span className="text-xs text-[var(--mm-text2)]">No account needed</span>;
            } else if (p.requires_account) {
              statusEl = p.has_credentials ? (
                <span className="text-xs font-medium text-emerald-600">Configured</span>
              ) : (
                <span className="text-xs text-[var(--mm-text2)]">Not configured</span>
              );
            } else if (p.provider_key === "podnapisi") {
              statusEl = <span className="text-xs text-[var(--mm-text2)]">Optional credentials</span>;
            } else {
              statusEl = <span className="text-xs text-[var(--mm-text2)]">—</span>;
            }
            return (
              <li key={p.provider_key} className="bg-[var(--mm-card-bg)]/40">
                <div className="flex flex-wrap items-center gap-x-3 gap-y-2 px-3 py-2.5">
                  <span className="min-w-[7rem] text-sm font-semibold text-[var(--mm-text)]">{p.display_name}</span>
                  <div className="max-w-[11rem] shrink-0">
                    <MmOnOffSwitch
                      id={`prov-en-${p.provider_key}`}
                      label="Enabled"
                      layout="inline"
                      enabled={p.enabled}
                      disabled={dis || putProv.isPending}
                      onChange={(v) => void saveProviderRow(p.provider_key, v, pri)}
                    />
                  </div>
                  <label className="flex items-center gap-1.5 text-xs text-[var(--mm-text2)]">
                    <span className="sr-only">Priority</span>
                    <input
                      type="number"
                      className="mm-input max-w-16 text-sm"
                      disabled={dis}
                      value={pri}
                      onChange={(e) =>
                        setProvPri((x) => ({
                          ...x,
                          [p.provider_key]: Math.max(0, Math.min(9999, Number(e.target.value) || 0)),
                        }))
                      }
                      onBlur={() => {
                        if (pri !== p.priority) void saveProviderRow(p.provider_key, p.enabled, pri);
                      }}
                    />
                  </label>
                  {showCfg ? (
                    <button
                      type="button"
                      className={mmActionButtonClass({ variant: "secondary", disabled: dis })}
                      disabled={dis}
                      onClick={() => setExpandedProviderKey(expanded ? null : p.provider_key)}
                    >
                      {expanded ? "Close" : "Configure"}
                    </button>
                  ) : null}
                  <span className="ml-auto min-w-0 shrink text-right">{statusEl}</span>
                </div>
                {expanded && showCfg ? (
                  <div className="space-y-3 border-t border-[var(--mm-border)] bg-black/20 px-3 py-3">
                    {p.provider_key === "podnapisi" && !p.requires_account ? (
                      <p className="text-xs text-[var(--mm-text2)]">No account required — credentials optional.</p>
                    ) : null}
                    {p.requires_account ? (
                      <div className="space-y-2">
                        <label className="block text-xs text-[var(--mm-text2)]">
                          Username
                          <input
                            className="mm-input mt-1 w-full max-w-md"
                            disabled={dis}
                            value={provUser[p.provider_key] ?? ""}
                            onChange={(e) => setProvUser((x) => ({ ...x, [p.provider_key]: e.target.value }))}
                          />
                        </label>
                        <label className="block text-xs text-[var(--mm-text2)]">
                          Password {p.has_credentials ? <span className="text-[0.7rem]">(leave blank to keep)</span> : null}
                          <input
                            type="password"
                            className="mm-input mt-1 w-full max-w-md"
                            disabled={dis}
                            placeholder={p.has_credentials ? MASK : ""}
                            value={provPass[p.provider_key] ?? ""}
                            onChange={(e) => setProvPass((x) => ({ ...x, [p.provider_key]: e.target.value }))}
                          />
                        </label>
                        {p.provider_key.includes("opensubtitles") ? (
                          <label className="block text-xs text-[var(--mm-text2)]">
                            API key
                            <input
                              type="password"
                              className="mm-input mt-1 w-full max-w-md"
                              disabled={dis}
                              placeholder={p.has_credentials ? MASK : ""}
                              value={provKey[p.provider_key] ?? ""}
                              onChange={(e) => setProvKey((x) => ({ ...x, [p.provider_key]: e.target.value }))}
                            />
                          </label>
                        ) : null}
                      </div>
                    ) : p.provider_key === "podnapisi" ? (
                      <div className="space-y-2">
                        <label className="block text-xs text-[var(--mm-text2)]">
                          Username (optional)
                          <input
                            className="mm-input mt-1 w-full max-w-md"
                            disabled={dis}
                            value={provUser[p.provider_key] ?? ""}
                            onChange={(e) => setProvUser((x) => ({ ...x, [p.provider_key]: e.target.value }))}
                          />
                        </label>
                        <label className="block text-xs text-[var(--mm-text2)]">
                          Password (optional)
                          <input
                            type="password"
                            className="mm-input mt-1 w-full max-w-md"
                            disabled={dis}
                            placeholder={p.has_credentials ? MASK : ""}
                            value={provPass[p.provider_key] ?? ""}
                            onChange={(e) => setProvPass((x) => ({ ...x, [p.provider_key]: e.target.value }))}
                          />
                        </label>
                      </div>
                    ) : null}
                    <div className="flex flex-wrap gap-2">
                      <button
                        type="button"
                        className={mmActionButtonClass({ variant: "primary", disabled: dis || putProv.isPending })}
                        disabled={dis || putProv.isPending}
                        onClick={() => void saveExpandedProvider(p.provider_key, p.enabled, pri)}
                      >
                        Save
                      </button>
                      <button
                        type="button"
                        className={mmActionButtonClass({ variant: "secondary", disabled: dis || testProv.isPending })}
                        disabled={dis || testProv.isPending}
                        onClick={() => void runProvTest(p.provider_key)}
                      >
                        Test
                      </button>
                    </div>
                  </div>
                ) : null}
              </li>
            );
          })}
        </ul>
      </SubberSettingsSection>
    </div>
  );
}
