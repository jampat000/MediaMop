import { useEffect, useState } from "react";
import { fetchCsrfToken } from "../../lib/api/auth-api";
import { MmOnOffSwitch } from "../../components/ui/mm-on-off-switch";
import { mmActionButtonClass } from "../../lib/ui/mm-control-roles";
import { SUBBER_LANGUAGE_OPTIONS, subberLanguageLabel } from "../../lib/subber/subber-languages";
import type { SubberProviderPutIn } from "../../lib/subber/subber-api";
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
  const [saveFolder, setSaveFolder] = useState({ ok: false, err: null as string | null });
  const [saveStyle, setSaveStyle] = useState({ ok: false, err: null as string | null });
  const [saveFreq, setSaveFreq] = useState({ ok: false, err: null as string | null });
  const [saveMap, setSaveMap] = useState({ ok: false, err: null as string | null });
  const [saveEn, setSaveEn] = useState({ ok: false, err: null as string | null });

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

  async function saveSubtitleFolder() {
    setSaveFolder({ ok: false, err: null });
    try {
      const csrf_token = await fetchCsrfToken();
      await put.mutateAsync({ csrf_token, subtitle_folder: folder.trim() });
      flashSave(setSaveFolder);
    } catch (e) {
      setSaveFolder({ ok: false, err: (e as Error).message });
    }
  }

  async function saveSubtitleStyle() {
    setSaveStyle({ ok: false, err: null });
    try {
      const csrf_token = await fetchCsrfToken();
      await put.mutateAsync({ csrf_token, exclude_hearing_impaired: excludeHi });
      flashSave(setSaveStyle);
    } catch (e) {
      setSaveStyle({ ok: false, err: (e as Error).message });
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

  async function savePathMapping() {
    setSaveMap({ ok: false, err: null });
    try {
      const csrf_token = await fetchCsrfToken();
      await put.mutateAsync({
        csrf_token,
        sonarr_path_mapping_enabled: sonMapEn,
        sonarr_path_sonarr: sonArr.trim(),
        sonarr_path_subber: sonSub.trim(),
        radarr_path_mapping_enabled: radMapEn,
        radarr_path_radarr: radArr.trim(),
        radarr_path_subber: radSub.trim(),
      });
      flashSave(setSaveMap);
    } catch (e) {
      setSaveMap({ ok: false, err: (e as Error).message });
    }
  }

  async function saveEnableSubber() {
    setSaveEn({ ok: false, err: null });
    try {
      const csrf_token = await fetchCsrfToken();
      await put.mutateAsync({ csrf_token, enabled });
      flashSave(setSaveEn);
    } catch (e) {
      setSaveEn({ ok: false, err: (e as Error).message });
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
      {/* Card 1 — OpenSubtitles */}
      <section className="space-y-3 rounded-md border border-[var(--mm-border)] bg-[var(--mm-card-bg)] p-5">
        <h2 className="text-base font-semibold text-[var(--mm-text)]">OpenSubtitles</h2>
        <label className="block text-sm text-[var(--mm-text2)]">
          Username
          <input className="mm-input mt-1 w-full max-w-md" value={osUser} disabled={dis} onChange={(e) => setOsUser(e.target.value)} />
        </label>
        <label className="block text-sm text-[var(--mm-text2)]">
          Password {q.data?.opensubtitles_password_set ? <span className="text-xs">(leave blank to keep saved)</span> : null}
          <div className="mt-1 flex max-w-md gap-2">
            <input
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
        </label>
        <label className="block text-sm text-[var(--mm-text2)]">
          API key
          <div className="mt-1 flex max-w-md gap-2">
            <input
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
        </label>
        <p className="text-xs text-[var(--mm-text2)]">
          Get your free account and API key at opensubtitles.com. Your account includes a daily download quota — Subber shows your remaining quota when you test the connection.
        </p>
        <div className="flex flex-wrap gap-2">
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
      </section>

      {/* Card 2 — Sonarr */}
      <section className="space-y-3 rounded-md border border-[var(--mm-border)] bg-[var(--mm-card-bg)] p-5">
        <h2 className="text-base font-semibold text-[var(--mm-text)]">Sonarr</h2>
        {sonHint ? (
          <p className="text-sm text-[var(--mm-text2)]">Your Fetcher Sonarr URL is {sonHint} — you can use the same one.</p>
        ) : null}
        <label className="block text-sm text-[var(--mm-text2)]">
          Sonarr base URL
          <input className="mm-input mt-1 w-full max-w-xl" value={sonUrl} disabled={dis} onChange={(e) => setSonUrl(e.target.value)} />
        </label>
        <label className="block text-sm text-[var(--mm-text2)]">
          Sonarr API key
          <div className="mt-1 flex max-w-xl gap-2">
            <input
              className="mm-input min-w-0 flex-1"
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
        </label>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            className={mmActionButtonClass({ variant: "primary", disabled: dis })}
            disabled={dis}
            onClick={() => void saveSonarr()}
            data-testid="subber-save-sonarr"
          >
            Save Sonarr
          </button>
          <button
            type="button"
            className={mmActionButtonClass({ variant: "secondary", disabled: dis || testSon.isPending })}
            disabled={dis || testSon.isPending}
            onClick={() => void runTestSon()}
          >
            Test Sonarr
          </button>
        </div>
        <SaveFeedback ok={saveSon.ok} err={saveSon.err} />
        <ConnectionStatusPanel check={sonCheck} idleHelper="Save your URL and API key, then run a test to confirm Sonarr is reachable." />
        <WebhookUrlField
          id="subber-webhook-sonarr"
          helper="Add this in Sonarr under Settings → Connect → Webhook. Set the trigger to On Download. Subber searches for subtitles immediately when Sonarr imports a file."
          value={sonHook}
          disabled={dis}
        />
        <div className="mt-4 space-y-1">
          <button
            type="button"
            className={mmActionButtonClass({ variant: "secondary", disabled: dis || syncTv.isPending })}
            disabled={dis || syncTv.isPending}
            onClick={() => {
              setTvSyncOk(false);
              void syncTv.mutate(undefined, {
                onSuccess: () => setTvSyncOk(true),
              });
            }}
            data-testid="subber-sync-tv-library"
          >
            {syncTv.isPending ? "Syncing…" : "Sync TV library from Sonarr"}
          </button>
          <p className="text-xs text-[var(--mm-text2)]">
            Pulls your full Sonarr library and checks which episodes already have subtitles. Run once after connecting.
          </p>
          {tvSyncOk ? <p className="text-xs text-[var(--mm-text)]">TV sync queued — check the Jobs tab.</p> : null}
        </div>
      </section>

      {/* Card 3 — Radarr */}
      <section className="space-y-3 rounded-md border border-[var(--mm-border)] bg-[var(--mm-card-bg)] p-5">
        <h2 className="text-base font-semibold text-[var(--mm-text)]">Radarr</h2>
        {radHint ? (
          <p className="text-sm text-[var(--mm-text2)]">Your Fetcher Radarr URL is {radHint} — you can use the same one.</p>
        ) : null}
        <label className="block text-sm text-[var(--mm-text2)]">
          Radarr base URL
          <input className="mm-input mt-1 w-full max-w-xl" value={radUrl} disabled={dis} onChange={(e) => setRadUrl(e.target.value)} />
        </label>
        <label className="block text-sm text-[var(--mm-text2)]">
          Radarr API key
          <div className="mt-1 flex max-w-xl gap-2">
            <input
              className="mm-input min-w-0 flex-1"
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
        </label>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            className={mmActionButtonClass({ variant: "primary", disabled: dis })}
            disabled={dis}
            onClick={() => void saveRadarr()}
            data-testid="subber-save-radarr"
          >
            Save Radarr
          </button>
          <button
            type="button"
            className={mmActionButtonClass({ variant: "secondary", disabled: dis || testRad.isPending })}
            disabled={dis || testRad.isPending}
            onClick={() => void runTestRad()}
          >
            Test Radarr
          </button>
        </div>
        <SaveFeedback ok={saveRad.ok} err={saveRad.err} />
        <ConnectionStatusPanel check={radCheck} idleHelper="Save your URL and API key, then run a test to confirm Radarr is reachable." />
        <WebhookUrlField
          id="subber-webhook-radarr"
          helper="Add this in Radarr under Settings → Connect → Webhook. Set the trigger to On Download. Subber searches for subtitles immediately when Radarr imports a file."
          value={radHook}
          disabled={dis}
        />
        <div className="mt-4 space-y-1">
          <button
            type="button"
            className={mmActionButtonClass({ variant: "secondary", disabled: dis || syncMovies.isPending })}
            disabled={dis || syncMovies.isPending}
            onClick={() => {
              setMoviesSyncOk(false);
              void syncMovies.mutate(undefined, {
                onSuccess: () => setMoviesSyncOk(true),
              });
            }}
            data-testid="subber-sync-movies-library"
          >
            {syncMovies.isPending ? "Syncing…" : "Sync Movies library from Radarr"}
          </button>
          <p className="text-xs text-[var(--mm-text2)]">
            Pulls your full Radarr library and checks which movies already have subtitles. Run once after connecting.
          </p>
          {moviesSyncOk ? <p className="text-xs text-[var(--mm-text)]">Movies sync queued — check the Jobs tab.</p> : null}
        </div>
      </section>

      {/* Card 4 — Languages */}
      <section className="space-y-3 rounded-md border border-[var(--mm-border)] bg-[var(--mm-card-bg)] p-5">
        <h2 className="text-base font-semibold text-[var(--mm-text)]">Languages</h2>
        <p className="text-sm text-[var(--mm-text2)]">
          Subber tries languages in this order. If the first is not found it tries the next automatically.
        </p>
        <ul className="space-y-2">
          {langs.map((code, idx) => (
            <li key={`${code}-${idx}`} className="flex flex-wrap items-center gap-2 rounded border border-[var(--mm-border)] bg-black/10 px-2 py-2">
              <span className="text-sm text-[var(--mm-text)]">
                {subberLanguageLabel(code)} ({code})
              </span>
              <button
                type="button"
                className={mmActionButtonClass({ variant: "secondary" })}
                disabled={dis || idx === 0}
                onClick={() => {
                  const n = [...langs];
                  [n[idx - 1], n[idx]] = [n[idx], n[idx - 1]];
                  setLangs(n);
                }}
              >
                Up
              </button>
              <button
                type="button"
                className={mmActionButtonClass({ variant: "secondary" })}
                disabled={dis || idx >= langs.length - 1}
                onClick={() => {
                  const n = [...langs];
                  [n[idx + 1], n[idx]] = [n[idx], n[idx + 1]];
                  setLangs(n);
                }}
              >
                Down
              </button>
              <button
                type="button"
                className={mmActionButtonClass({ variant: "secondary" })}
                disabled={dis}
                onClick={() => setLangs(langs.filter((_, i) => i !== idx))}
              >
                Remove
              </button>
            </li>
          ))}
        </ul>
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
      </section>

      {/* Card 5 — Subtitle folder */}
      <section className="space-y-3 rounded-md border border-[var(--mm-border)] bg-[var(--mm-card-bg)] p-5">
        <h2 className="text-base font-semibold text-[var(--mm-text)]">Subtitle folder</h2>
        <p className="text-sm text-[var(--mm-text2)]">
          Leave empty to save subtitles in the same folder as your media file. Subtitles are always named to match the media file — for example Movie.2023.en.srt alongside Movie.2023.mkv.
        </p>
        <label className="block text-sm text-[var(--mm-text2)]">
          Subtitle folder
          <input
            className="mm-input mt-1 w-full max-w-xl"
            value={folder}
            disabled={dis}
            onChange={(e) => setFolder(e.target.value)}
            placeholder="Same folder as media file"
          />
        </label>
        <button
          type="button"
          className={mmActionButtonClass({ variant: "primary", disabled: dis })}
          disabled={dis}
          onClick={() => void saveSubtitleFolder()}
          data-testid="subber-save-subtitle-folder"
        >
          Save subtitle folder
        </button>
        <SaveFeedback ok={saveFolder.ok} err={saveFolder.err} />
      </section>

      {/* Card 6 — Subtitle style */}
      <section className="space-y-3 rounded-md border border-[var(--mm-border)] bg-[var(--mm-card-bg)] p-5">
        <h2 className="text-base font-semibold text-[var(--mm-text)]">Subtitle style</h2>
        <MmOnOffSwitch id="subber-exclude-hi" label="Exclude hearing impaired" enabled={excludeHi} disabled={dis} onChange={setExcludeHi} />
        <p className="text-xs text-[var(--mm-text2)]">
          When on, Subber skips subtitles that include sound descriptions for hearing impaired viewers — for example [DOOR CREAKS] or [TENSE MUSIC].
        </p>
        <button type="button" className={mmActionButtonClass({ variant: "primary", disabled: dis })} disabled={dis} onClick={() => void saveSubtitleStyle()}>
          Save subtitle style
        </button>
        <SaveFeedback ok={saveStyle.ok} err={saveStyle.err} />
      </section>

      {/* Card 7 — Search frequency */}
      <section className="space-y-3 rounded-md border border-[var(--mm-border)] bg-[var(--mm-card-bg)] p-5">
        <h2 className="text-base font-semibold text-[var(--mm-text)]">Search frequency</h2>
        <MmOnOffSwitch id="subber-adapt" label="Enable adaptive searching" enabled={adaptEn} disabled={dis} onChange={setAdaptEn} />
        <p className="text-xs text-[var(--mm-text2)]">
          When on, Subber automatically searches less often for files that repeatedly return no results. This protects your daily download quota.
        </p>
        {adaptEn ? (
          <div className="space-y-2">
            <label className="block text-sm text-[var(--mm-text2)]">
              Back off after failed attempts
              <input
                type="number"
                className="mm-input mt-1 w-28"
                min={1}
                max={100}
                value={adaptMax}
                disabled={dis}
                onChange={(e) => setAdaptMax(Number(e.target.value) || 1)}
              />
            </label>
            <label className="block text-sm text-[var(--mm-text2)]">
              Wait hours before retrying
              <input
                type="number"
                className="mm-input mt-1 w-28"
                min={1}
                max={8760}
                value={adaptDelayH}
                disabled={dis}
                onChange={(e) => setAdaptDelayH(Number(e.target.value) || 1)}
              />
            </label>
            <label className="block text-sm text-[var(--mm-text2)]">
              Give up after total attempts
              <input
                type="number"
                className="mm-input mt-1 w-28"
                min={1}
                max={10000}
                value={adaptPerm}
                disabled={dis}
                onChange={(e) => setAdaptPerm(Number(e.target.value) || 1)}
              />
            </label>
          </div>
        ) : null}
        <button type="button" className={mmActionButtonClass({ variant: "primary", disabled: dis })} disabled={dis} onClick={() => void saveSearchFrequency()}>
          Save search frequency
        </button>
        <SaveFeedback ok={saveFreq.ok} err={saveFreq.err} />
      </section>

      {/* Card 8 — Providers */}
      <section className="space-y-3 rounded-md border border-[var(--mm-border)] bg-[var(--mm-card-bg)] p-5" data-testid="subber-providers-section">
        <h2 className="text-base font-semibold text-[var(--mm-text)]">Subtitle providers</h2>
        <p className="text-sm text-[var(--mm-text2)]">
          Subber searches providers in order until a subtitle is found. Lower number = searched first. Enable at least one.
        </p>
        {pq.isLoading ? <p className="text-sm text-[var(--mm-text2)]">Loading providers…</p> : null}
        <ul className="space-y-4">
          {sorted.map((p) => (
            <li key={p.provider_key} className="rounded border border-[var(--mm-border)] bg-black/10 p-4">
              <h3 className="text-sm font-semibold text-[var(--mm-text)]">{p.display_name}</h3>
              <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
                <MmOnOffSwitch
                  id={`prov-en-${p.provider_key}`}
                  label="Enabled"
                  enabled={p.enabled}
                  disabled={dis || putProv.isPending}
                  onChange={(v) => void saveProviderRow(p.provider_key, v, provPri[p.provider_key] ?? p.priority)}
                />
              </div>
              <label className="mt-2 block text-xs text-[var(--mm-text2)]">
                Priority
                <input
                  type="number"
                  className="mm-input mt-1 w-24"
                  disabled={dis}
                  value={provPri[p.provider_key] ?? p.priority}
                  onChange={(e) =>
                    setProvPri((x) => ({
                      ...x,
                      [p.provider_key]: Math.max(0, Math.min(9999, Number(e.target.value) || 0)),
                    }))
                  }
                />
              </label>
              {p.requires_account ? (
                <div className="mt-2 space-y-2">
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
              ) : (
                <p className="mt-2 text-xs text-[var(--mm-text2)]">
                  {p.provider_key === "podnapisi"
                    ? "Podnapisi works without an account. Add credentials only if you have one."
                    : p.provider_key === "subscene"
                      ? "No account required."
                      : null}
                </p>
              )}
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  className={mmActionButtonClass({ variant: "primary", disabled: dis || putProv.isPending })}
                  disabled={dis || putProv.isPending}
                  onClick={() => void saveProviderRow(p.provider_key, p.enabled, provPri[p.provider_key] ?? p.priority)}
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
                <span className="text-xs text-[var(--mm-text2)]">
                  {provMsg[p.provider_key]
                    ? provMsg[p.provider_key] === "Connected"
                      ? "Status: Connected"
                      : `Status: ${provMsg[p.provider_key]}`
                    : "Status: Not configured"}
                </span>
              </div>
            </li>
          ))}
        </ul>
      </section>

      {/* Card 9 — Path mapping */}
      <section className="space-y-3 rounded-md border border-[var(--mm-border)] bg-[var(--mm-card-bg)] p-5">
        <h2 className="text-base font-semibold text-[var(--mm-text)]">Path mapping</h2>
        <p className="text-sm text-[var(--mm-text2)]">
          Only needed if MediaMop and Sonarr/Radarr run on different machines or in separate Docker containers. Leave disabled if everything runs on the same machine.
        </p>
        <MmOnOffSwitch id="subber-son-map" label="Enable Sonarr path mapping" enabled={sonMapEn} disabled={dis} onChange={setSonMapEn} />
        {sonMapEn ? (
          <div className="space-y-2">
            <label className="block text-sm text-[var(--mm-text2)]">
              Path that Sonarr uses
              <input className="mm-input mt-1 w-full max-w-xl font-mono text-sm" value={sonArr} disabled={dis} onChange={(e) => setSonArr(e.target.value)} />
            </label>
            <label className="block text-sm text-[var(--mm-text2)]">
              Path that MediaMop uses
              <input className="mm-input mt-1 w-full max-w-xl font-mono text-sm" value={sonSub} disabled={dis} onChange={(e) => setSonSub(e.target.value)} />
            </label>
          </div>
        ) : null}
        <MmOnOffSwitch id="subber-rad-map" label="Enable Radarr path mapping" enabled={radMapEn} disabled={dis} onChange={setRadMapEn} />
        {radMapEn ? (
          <div className="space-y-2">
            <label className="block text-sm text-[var(--mm-text2)]">
              Path that Radarr uses
              <input className="mm-input mt-1 w-full max-w-xl font-mono text-sm" value={radArr} disabled={dis} onChange={(e) => setRadArr(e.target.value)} />
            </label>
            <label className="block text-sm text-[var(--mm-text2)]">
              Path that MediaMop uses
              <input className="mm-input mt-1 w-full max-w-xl font-mono text-sm" value={radSub} disabled={dis} onChange={(e) => setRadSub(e.target.value)} />
            </label>
          </div>
        ) : null}
        <button type="button" className={mmActionButtonClass({ variant: "primary", disabled: dis })} disabled={dis} onClick={() => void savePathMapping()}>
          Save path mapping
        </button>
        <SaveFeedback ok={saveMap.ok} err={saveMap.err} />
      </section>

      {/* Card 10 — Enable Subber */}
      <section className="space-y-3 rounded-md border border-[var(--mm-border)] bg-[var(--mm-card-bg)] p-5">
        <h2 className="text-base font-semibold text-[var(--mm-text)]">Enable Subber</h2>
        <p className="text-xs text-[var(--mm-text2)]">
          {enabled
            ? "Subber is on. Searches run on import and schedule."
            : "Subber is off. No automatic searches will run."}
        </p>
        <MmOnOffSwitch id="subber-enabled" label="Enable Subber" enabled={enabled} disabled={dis} onChange={setEnabled} />
        <button type="button" className={mmActionButtonClass({ variant: "primary", disabled: dis })} disabled={dis} onClick={() => void saveEnableSubber()}>
          Save
        </button>
        <SaveFeedback ok={saveEn.ok} err={saveEn.err} />
      </section>
    </div>
  );
}
