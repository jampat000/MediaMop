import { useEffect, useState } from "react";
import { fetchCsrfToken } from "../../lib/api/auth-api";
import { MmOnOffSwitch } from "../../components/ui/mm-on-off-switch";
import { mmActionButtonClass } from "../../lib/ui/mm-control-roles";
import { SUBBER_LANGUAGE_OPTIONS, subberLanguageLabel } from "../../lib/subber/subber-languages";
import {
  usePutSubberSettingsMutation,
  useSubberLibrarySyncMoviesMutation,
  useSubberLibrarySyncTvMutation,
  useSubberSettingsQuery,
  useSubberTestOpensubtitlesMutation,
  useSubberTestRadarrMutation,
  useSubberTestSonarrMutation,
} from "../../lib/subber/subber-queries";
import { SubberSettingsMoreSections } from "./subber-settings-more";

const MASK = "\u2022".repeat(10);

function WebhookUrlField({
  id,
  label,
  helper,
  value,
  disabled,
}: {
  id: string;
  label: string;
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
        {label}
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

export function SubberSettingsTab({ canOperate }: { canOperate: boolean }) {
  const q = useSubberSettingsQuery();
  const put = usePutSubberSettingsMutation();
  const testOs = useSubberTestOpensubtitlesMutation();
  const testSon = useSubberTestSonarrMutation();
  const testRad = useSubberTestRadarrMutation();
  const syncTv = useSubberLibrarySyncTvMutation();
  const syncMovies = useSubberLibrarySyncMoviesMutation();

  const [osUser, setOsUser] = useState("");
  const [osPass, setOsPass] = useState("");
  const [osKey, setOsKey] = useState("");
  const [showOsPass, setShowOsPass] = useState(false);
  const [showOsKey, setShowOsKey] = useState(false);
  const [sonUrl, setSonUrl] = useState("");
  const [sonKey, setSonKey] = useState("");
  const [radUrl, setRadUrl] = useState("");
  const [radKey, setRadKey] = useState("");
  const [langs, setLangs] = useState<string[]>(["en"]);
  const [folder, setFolder] = useState("");
  const [enabled, setEnabled] = useState(false);
  const [osMsg, setOsMsg] = useState<string | null>(null);
  const [tvSyncOk, setTvSyncOk] = useState(false);
  const [moviesSyncOk, setMoviesSyncOk] = useState(false);

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
  }, [q.data]);

  const base = typeof window !== "undefined" ? window.location.origin : "";
  const sonHook = `${base}/api/v1/subber/webhook/sonarr`;
  const radHook = `${base}/api/v1/subber/webhook/radarr`;
  const dis = !canOperate || put.isPending;

  async function saveOpenSubtitles() {
    const csrf_token = await fetchCsrfToken();
    const body: Parameters<typeof put.mutateAsync>[0] = {
      csrf_token,
      opensubtitles_username: osUser.trim(),
    };
    if (osPass.trim()) body.opensubtitles_password = osPass;
    if (osKey.trim()) body.opensubtitles_api_key = osKey;
    await put.mutateAsync(body);
  }

  async function saveSonarr() {
    const csrf_token = await fetchCsrfToken();
    const body: Parameters<typeof put.mutateAsync>[0] = { csrf_token, sonarr_base_url: sonUrl.trim() };
    if (sonKey.trim()) body.sonarr_api_key = sonKey;
    await put.mutateAsync(body);
  }

  async function saveRadarr() {
    const csrf_token = await fetchCsrfToken();
    const body: Parameters<typeof put.mutateAsync>[0] = { csrf_token, radarr_base_url: radUrl.trim() };
    if (radKey.trim()) body.radarr_api_key = radKey;
    await put.mutateAsync(body);
  }

  async function savePreferences() {
    const csrf_token = await fetchCsrfToken();
    await put.mutateAsync({
      csrf_token,
      language_preferences: langs,
      subtitle_folder: folder.trim(),
      enabled,
    });
  }

  async function runTestOs() {
    setOsMsg(null);
    try {
      const r = await testOs.mutateAsync();
      setOsMsg(r.ok ? `Connected. ${r.message}` : r.message);
    } catch (e) {
      setOsMsg((e as Error).message);
    }
  }

  if (q.isLoading) return <p className="text-sm text-[var(--mm-text2)]">Loading settings…</p>;
  if (q.isError) return <p className="text-sm text-red-600">{(q.error as Error).message}</p>;

  return (
    <div className="space-y-8" data-testid="subber-settings-tab">
      <section className="space-y-3 rounded-md border border-[var(--mm-border)] bg-[var(--mm-card-bg)] p-5">
        <h2 className="text-base font-semibold text-[var(--mm-text)]">OpenSubtitles connection</h2>
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
        {osMsg ? <p className="text-sm text-[var(--mm-text)]">{osMsg}</p> : null}
      </section>

      <section className="space-y-3 rounded-md border border-[var(--mm-border)] bg-[var(--mm-card-bg)] p-5">
        <h2 className="text-base font-semibold text-[var(--mm-text)]">Sonarr and Radarr connection</h2>
        <p className="text-xs text-[var(--mm-text2)]">
          These are pre-filled from your Fetcher settings if available. Subber keeps its own copy — changes here do not affect Fetcher, and changes in Fetcher do not affect Subber.
        </p>
        {q.data?.fetcher_sonarr_base_url_hint ? (
          <p className="text-xs text-[var(--mm-text2)]">Fetcher Sonarr URL hint: {q.data.fetcher_sonarr_base_url_hint}</p>
        ) : null}
        {q.data?.fetcher_radarr_base_url_hint ? (
          <p className="text-xs text-[var(--mm-text2)]">Fetcher Radarr URL hint: {q.data.fetcher_radarr_base_url_hint}</p>
        ) : null}
        <div className="space-y-2 border-t border-[var(--mm-border)] pt-4 first:border-t-0 first:pt-0">
          <h3 className="text-sm font-semibold text-[var(--mm-text)]">Sonarr</h3>
          <label className="block text-sm text-[var(--mm-text2)]">
            Sonarr base URL
            <input className="mm-input mt-1 w-full max-w-xl" value={sonUrl} disabled={dis} onChange={(e) => setSonUrl(e.target.value)} />
          </label>
          <label className="block text-sm text-[var(--mm-text2)]">
            Sonarr API key
            <input
              className="mm-input mt-1 w-full max-w-xl"
              type="password"
              value={sonKey}
              placeholder={q.data?.sonarr_api_key_set ? MASK : ""}
              disabled={dis}
              onChange={(e) => setSonKey(e.target.value)}
            />
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
              onClick={() => void testSon.mutate()}
            >
              Test Sonarr
            </button>
          </div>
          <WebhookUrlField
            id="subber-webhook-sonarr"
            label="Webhook URL for Sonarr"
            helper="Add this URL in Sonarr under Settings → Connect → Webhook (trigger on Download). Subber searches for subtitles immediately when Sonarr imports a file."
            value={sonHook}
            disabled={dis}
          />
          <div className="mt-3 space-y-1">
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
              Pulls your full Sonarr TV library and checks which episodes already have subtitles. Run this once after connecting to populate your TV tab.
            </p>
            {tvSyncOk ? <p className="text-xs text-[var(--mm-text)]">TV sync queued — check the Jobs tab for progress.</p> : null}
          </div>
        </div>
        <div className="space-y-2 border-t border-[var(--mm-border)] pt-4">
          <h3 className="text-sm font-semibold text-[var(--mm-text)]">Radarr</h3>
          <label className="block text-sm text-[var(--mm-text2)]">
            Radarr base URL
            <input className="mm-input mt-1 w-full max-w-xl" value={radUrl} disabled={dis} onChange={(e) => setRadUrl(e.target.value)} />
          </label>
          <label className="block text-sm text-[var(--mm-text2)]">
            Radarr API key
            <input
              className="mm-input mt-1 w-full max-w-xl"
              type="password"
              value={radKey}
              placeholder={q.data?.radarr_api_key_set ? MASK : ""}
              disabled={dis}
              onChange={(e) => setRadKey(e.target.value)}
            />
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
              onClick={() => void testRad.mutate()}
            >
              Test Radarr
            </button>
          </div>
          <WebhookUrlField
            id="subber-webhook-radarr"
            label="Webhook URL for Radarr"
            helper="Add this URL in Radarr under Settings → Connect → Webhook (trigger on Download). Subber searches for subtitles immediately when Radarr imports a file."
            value={radHook}
            disabled={dis}
          />
          <div className="mt-3 space-y-1">
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
              Pulls your full Radarr movie library and checks which movies already have subtitles. Run this once after connecting to populate your Movies tab.
            </p>
            {moviesSyncOk ? <p className="text-xs text-[var(--mm-text)]">Movies sync queued — check the Jobs tab for progress.</p> : null}
          </div>
        </div>
      </section>

      <section className="space-y-3 rounded-md border border-[var(--mm-border)] bg-[var(--mm-card-bg)] p-5">
        <h2 className="text-base font-semibold text-[var(--mm-text)]">Subtitle preferences</h2>
        <p className="text-xs text-[var(--mm-text2)]">Subber tries languages in this order. If the first is not found it tries the next automatically.</p>
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
              <button type="button" className={mmActionButtonClass({ variant: "secondary" })} disabled={dis} onClick={() => setLangs(langs.filter((_, i) => i !== idx))}>
                Remove
              </button>
            </li>
          ))}
        </ul>
        <div className="flex flex-wrap items-end gap-2">
          <label className="text-sm text-[var(--mm-text2)]">
            Add language
            <select
              className="mm-input mt-1 block"
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
        </div>
        <label className="block text-sm text-[var(--mm-text2)]">
          Subtitle folder
          <input className="mm-input mt-1 w-full max-w-xl" value={folder} disabled={dis} onChange={(e) => setFolder(e.target.value)} />
        </label>
        <p className="text-xs text-[var(--mm-text2)]">
          Leave empty to save subtitles in the same folder as your media file. If you enter a path, all subtitles go there. Subtitle files are always named to match your media file — for example Movie.2023.en.srt for Movie.2023.mkv.
        </p>
        <MmOnOffSwitch id="subber-enabled" label="Enable Subber" enabled={enabled} disabled={dis} onChange={setEnabled} />
        <p className="text-xs text-[var(--mm-text2)]">
          {enabled
            ? "Subber is on. Searches run on import and on schedule."
            : "Subber is off. No searches will run automatically."}
        </p>
        <button
          type="button"
          className={mmActionButtonClass({ variant: "primary", disabled: dis })}
          disabled={dis}
          onClick={() => void savePreferences()}
          data-testid="subber-save-preferences"
        >
          Save preferences
        </button>
      </section>

      <SubberSettingsMoreSections canOperate={canOperate} />
    </div>
  );
}
