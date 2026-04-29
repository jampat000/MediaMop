import { useEffect, useState, type ReactNode } from "react";
import { fetchCsrfToken } from "../../lib/api/auth-api";
import { MmOnOffSwitch } from "../../components/ui/mm-on-off-switch";
import { ServerFolderPickerButton } from "../../components/ui/server-folder-picker-button";
import { mmActionButtonClass } from "../../lib/ui/mm-control-roles";
import { useAppDateFormatter } from "../../lib/ui/mm-format-date";
import {
  usePutSubberSettingsMutation,
  useSubberLibrarySyncMoviesMutation,
  useSubberLibrarySyncTvMutation,
  useSubberRadarrRootFoldersMutation,
  useSubberSettingsQuery,
  useSubberSonarrRootFoldersMutation,
  useSubberTestRadarrMutation,
  useSubberTestSonarrMutation,
} from "../../lib/subber/subber-queries";
import type { SubberArrRootFolderOut } from "../../lib/subber/subber-api";
import {
  PathMappingSection,
  RadarrConnectionSection,
  SonarrConnectionSection,
  SyncActionsSection,
} from "./subber-connections-sections";

const MASK = "\u2022".repeat(10);

type ConnectionOutcome = null | "ok" | "fail";

type ConnectionCheckState = {
  outcome: ConnectionOutcome;
  at: string | null;
  detail: string;
  quotaNote?: string;
};

const initialCheck: ConnectionCheckState = { outcome: null, at: null, detail: "" };

function ConnectionStatusPanel({
  check,
  idleHelper,
  fmt,
}: {
  check: ConnectionCheckState;
  idleHelper?: string;
  fmt: (iso: string | null) => string;
}) {
  const main =
    check.outcome === null ? "Not connected yet" : check.outcome === "ok" ? "Connected" : "Connection failed";
  return (
    <div className="mt-4 rounded-md border border-[var(--mm-border)] bg-[var(--mm-card-bg)] p-3.5 text-sm text-[var(--mm-text2)]">
      <p className="text-sm font-medium text-[var(--mm-text)]">{main}</p>
      <p className="mt-1 text-xs text-[var(--mm-text2)]">
        Last completed check: <span className="font-medium text-[var(--mm-text)]">{fmt(check.at)}</span>
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
      <div className="mm-bubble-stack px-5 py-5">{children}</div>
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

function formatBytes(bytes: number | null | undefined) {
  if (bytes == null || !Number.isFinite(bytes)) return null;
  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toFixed(unit === 0 ? 0 : 1)} ${units[unit]} free`;
}

function ArrRootFolderChoices({
  label,
  folders,
  message,
  error,
  onUseArr,
  onUseBoth,
}: {
  label: "Sonarr" | "Radarr";
  folders: SubberArrRootFolderOut[];
  message: string | null;
  error: string | null;
  onUseArr: (path: string) => void;
  onUseBoth: (path: string) => void;
}) {
  if (!message && !error && folders.length === 0) return null;
  return (
    <div className="rounded-md border border-[var(--mm-border)] bg-black/10 p-3">
      {error ? <p className="text-xs text-red-400">{error}</p> : null}
      {message ? <p className="text-xs text-[var(--mm-text2)]">{message}</p> : null}
      {folders.length ? (
        <div className="mt-2 grid gap-2">
          {folders.map((folder) => {
            const free = formatBytes(folder.free_space);
            return (
              <div key={folder.path} className="rounded-md border border-[var(--mm-border)] bg-[var(--mm-card-bg)] p-2.5">
                <p className="break-all font-mono text-xs text-[var(--mm-text)]">{folder.path}</p>
                {free ? <p className="mt-1 text-[0.7rem] text-[var(--mm-text2)]">{free}</p> : null}
                <div className="mt-2 flex flex-wrap gap-2">
                  <button type="button" className={mmActionButtonClass({ variant: "secondary" })} onClick={() => onUseArr(folder.path)}>
                    Use as {label} path
                  </button>
                  <button type="button" className={mmActionButtonClass({ variant: "secondary" })} onClick={() => onUseBoth(folder.path)}>
                    Use for both
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}

export function SubberConnectionsTab({ canOperate }: { canOperate: boolean }) {
  const fmt = useAppDateFormatter();
  const q = useSubberSettingsQuery();
  const put = usePutSubberSettingsMutation();
  const testSon = useSubberTestSonarrMutation();
  const testRad = useSubberTestRadarrMutation();
  const syncTv = useSubberLibrarySyncTvMutation();
  const syncMovies = useSubberLibrarySyncMoviesMutation();
  const sonRootFoldersFetch = useSubberSonarrRootFoldersMutation();
  const radRootFoldersFetch = useSubberRadarrRootFoldersMutation();

  const [sonUrl, setSonUrl] = useState("");
  const [sonKey, setSonKey] = useState("");
  const [showSonKey, setShowSonKey] = useState(false);
  const [radUrl, setRadUrl] = useState("");
  const [radKey, setRadKey] = useState("");
  const [showRadKey, setShowRadKey] = useState(false);
  const [sonMapEn, setSonMapEn] = useState(false);
  const [sonArr, setSonArr] = useState("");
  const [sonSub, setSonSub] = useState("");
  const [radMapEn, setRadMapEn] = useState(false);
  const [radArr, setRadArr] = useState("");
  const [radSub, setRadSub] = useState("");
  const [sonCheck, setSonCheck] = useState<ConnectionCheckState>(initialCheck);
  const [radCheck, setRadCheck] = useState<ConnectionCheckState>(initialCheck);
  const [saveSon, setSaveSon] = useState({ ok: false, err: null as string | null });
  const [saveRad, setSaveRad] = useState({ ok: false, err: null as string | null });
  const [saveSonMap, setSaveSonMap] = useState({ ok: false, err: null as string | null });
  const [saveRadMap, setSaveRadMap] = useState({ ok: false, err: null as string | null });
  const [tvSyncOk, setTvSyncOk] = useState(false);
  const [moviesSyncOk, setMoviesSyncOk] = useState(false);
  const [tvSyncErr, setTvSyncErr] = useState<string | null>(null);
  const [moviesSyncErr, setMoviesSyncErr] = useState<string | null>(null);
  const [sonDirty, setSonDirty] = useState(false);
  const [radDirty, setRadDirty] = useState(false);
  const [sonMapDirty, setSonMapDirty] = useState(false);
  const [radMapDirty, setRadMapDirty] = useState(false);
  const [sonRootFolders, setSonRootFolders] = useState<SubberArrRootFolderOut[]>([]);
  const [radRootFolders, setRadRootFolders] = useState<SubberArrRootFolderOut[]>([]);
  const [sonRootMessage, setSonRootMessage] = useState<string | null>(null);
  const [radRootMessage, setRadRootMessage] = useState<string | null>(null);
  const [sonRootError, setSonRootError] = useState<string | null>(null);
  const [radRootError, setRadRootError] = useState<string | null>(null);

  useEffect(() => {
    const d = q.data;
    if (!d) return;
    setSonUrl(d.sonarr_base_url ?? "");
    setSonKey("");
    setRadUrl(d.radarr_base_url ?? "");
    setRadKey("");
    setSonMapEn(Boolean(d.sonarr_path_mapping_enabled));
    setSonArr(d.sonarr_path_sonarr ?? "");
    setSonSub(d.sonarr_path_subber ?? "");
    setRadMapEn(Boolean(d.radarr_path_mapping_enabled));
    setRadArr(d.radarr_path_radarr ?? "");
    setRadSub(d.radarr_path_subber ?? "");
    setSonDirty(false);
    setRadDirty(false);
    setSonMapDirty(false);
    setRadMapDirty(false);
  }, [q.data]);

  const dis = !canOperate || put.isPending;

  function flashSave(setter: typeof setSaveSon) {
    setter({ ok: true, err: null });
    window.setTimeout(() => setter({ ok: false, err: null }), 2500);
  }

  async function saveSonarr() {
    setSaveSon({ ok: false, err: null });
    try {
      const csrf_token = await fetchCsrfToken();
      const body: Parameters<typeof put.mutateAsync>[0] = { csrf_token, sonarr_base_url: sonUrl.trim() };
      if (sonKey.trim()) body.sonarr_api_key = sonKey;
      await put.mutateAsync(body);
      flashSave(setSaveSon);
      setSonDirty(false);
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
      setRadDirty(false);
    } catch (e) {
      setSaveRad({ ok: false, err: (e as Error).message });
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
      setSonMapDirty(false);
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
      setRadMapDirty(false);
    } catch (e) {
      setSaveRadMap({ ok: false, err: (e as Error).message });
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

  async function detectSonarrRootFolders() {
    setSonRootMessage(null);
    setSonRootError(null);
    try {
      const r = await sonRootFoldersFetch.mutateAsync();
      setSonRootFolders(r.folders);
      if (r.ok) {
        setSonRootMessage(r.message);
      } else {
        setSonRootError(r.message || "Sonarr did not return any root folders.");
      }
    } catch (e) {
      setSonRootError((e as Error).message);
    }
  }

  async function detectRadarrRootFolders() {
    setRadRootMessage(null);
    setRadRootError(null);
    try {
      const r = await radRootFoldersFetch.mutateAsync();
      setRadRootFolders(r.folders);
      if (r.ok) {
        setRadRootMessage(r.message);
      } else {
        setRadRootError(r.message || "Radarr did not return any root folders.");
      }
    } catch (e) {
      setRadRootError((e as Error).message);
    }
  }

  if (q.isLoading) return <p className="text-sm text-[var(--mm-text2)]">Loading settings…</p>;
  if (q.isError) return <p className="text-sm text-red-600">{(q.error as Error).message}</p>;

  const sonHint = (q.data?.arr_library_sonarr_base_url_hint || "").trim();
  const radHint = (q.data?.arr_library_radarr_base_url_hint || "").trim();

  return (
    <div className="mm-bubble-stack" data-testid="subber-connections-tab">
      <div className="mm-bubble-grid lg:grid-cols-2">
        <div className="mm-bubble-stack">
          <SubberSettingsSection
            eyebrow="TV library"
            title="Sonarr"
            description="Connect Sonarr so Subber can read your TV library and react to imports."
            data-testid="subber-settings-sonarr"
          >
            <SonarrConnectionSection>
            <SubberSettingsSubsection title="Connection">
              {sonHint ? (
                <p className="text-sm text-[var(--mm-text2)]">
                  Arr library already uses <span className="font-mono text-[var(--mm-text)]">{sonHint}</span> — you can paste the same base URL here.
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
                onChange={(e) => {
                  setSonUrl(e.target.value);
                  setSonDirty(true);
                }}
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
                  onChange={(e) => {
                    setSonKey(e.target.value);
                    setSonDirty(true);
                  }}
                />
                <button type="button" className={mmActionButtonClass({ variant: "secondary" })} onClick={() => setShowSonKey(!showSonKey)}>
                  {showSonKey ? "Hide" : "Show"}
                </button>
              </div>
              <div className="mt-4 flex flex-wrap gap-2">
                <button
                  type="button"
                  className={mmActionButtonClass({ variant: sonDirty ? "primary" : "secondary", disabled: dis || !sonDirty })}
                  disabled={dis || !sonDirty}
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
              <ConnectionStatusPanel
                check={sonCheck}
                idleHelper="Save your URL and API key, then run a test to confirm Sonarr is reachable."
                fmt={fmt}
              />
            </SubberSettingsSubsection>
            </SonarrConnectionSection>

            <SyncActionsSection>
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
            </SyncActionsSection>
          </SubberSettingsSection>

          <PathMappingSection>
          <SubberSettingsSection
            title="Path mapping"
            description="Only needed when Subber and Sonarr run in separate containers."
          >
            <MmOnOffSwitch
              id="subber-son-map"
              label="Enable Sonarr path mapping"
              enabled={sonMapEn}
              disabled={dis}
              onChange={(v) => {
                setSonMapEn(v);
                setSonMapDirty(true);
              }}
            />
            {sonMapEn ? (
              <>
                <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
                  <label className="block min-w-0 flex-1 text-sm text-[var(--mm-text2)]">
                    Path as Sonarr reports it
                    <div className="mt-1 flex flex-col gap-2 sm:flex-row">
                      <input
                        className="mm-input w-full font-mono text-sm"
                        value={sonArr}
                        disabled={dis}
                        onChange={(e) => {
                          setSonArr(e.target.value);
                          setSonMapDirty(true);
                        }}
                      />
                      <ServerFolderPickerButton
                        title="Choose Sonarr TV path"
                        value={sonArr}
                        disabled={dis}
                        onSelect={(path) => {
                          setSonArr(path);
                          setSonMapDirty(true);
                        }}
                      />
                    </div>
                  </label>
                  <label className="block min-w-0 flex-1 text-sm text-[var(--mm-text2)]">
                    Path as MediaMop sees it
                    <div className="mt-1 flex flex-col gap-2 sm:flex-row">
                      <input
                        className="mm-input w-full font-mono text-sm"
                        value={sonSub}
                        disabled={dis}
                        onChange={(e) => {
                          setSonSub(e.target.value);
                          setSonMapDirty(true);
                        }}
                      />
                      <ServerFolderPickerButton
                        title="Choose MediaMop TV path"
                        value={sonSub}
                        disabled={dis}
                        onSelect={(path) => {
                          setSonSub(path);
                          setSonMapDirty(true);
                        }}
                      />
                    </div>
                  </label>
                </div>
                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    className={mmActionButtonClass({ variant: "secondary", disabled: dis || sonRootFoldersFetch.isPending })}
                    disabled={dis || sonRootFoldersFetch.isPending}
                    onClick={() => void detectSonarrRootFolders()}
                  >
                    {sonRootFoldersFetch.isPending ? "Detecting..." : "Detect Sonarr paths"}
                  </button>
                  <p className="basis-full text-xs text-[var(--mm-text2)]">
                    Pulls Sonarr root folders through the API. Use these when Sonarr reports container or NAS paths differently from MediaMop.
                  </p>
                </div>
                <ArrRootFolderChoices
                  label="Sonarr"
                  folders={sonRootFolders}
                  message={sonRootMessage}
                  error={sonRootError}
                  onUseArr={(path) => {
                    setSonArr(path);
                    setSonMapDirty(true);
                  }}
                  onUseBoth={(path) => {
                    setSonArr(path);
                    setSonSub(path);
                    setSonMapDirty(true);
                  }}
                />
              </>
            ) : null}
            <button
              type="button"
              className={mmActionButtonClass({ variant: sonMapDirty ? "primary" : "secondary", disabled: dis || !sonMapDirty })}
              disabled={dis || !sonMapDirty}
              onClick={() => void saveSonarrPathMapping()}
              data-testid="subber-save-sonarr-path-mapping"
            >
              Save Sonarr path mapping
            </button>
            <SaveFeedback ok={saveSonMap.ok} err={saveSonMap.err} />
          </SubberSettingsSection>
          </PathMappingSection>
        </div>

        <div className="mm-bubble-stack">
          <SubberSettingsSection
            eyebrow="Movies library"
            title="Radarr"
            description="Connect Radarr so Subber can read your movies library and react to imports."
            data-testid="subber-settings-radarr"
          >
            <RadarrConnectionSection>
            <SubberSettingsSubsection title="Connection">
              {radHint ? (
                <p className="text-sm text-[var(--mm-text2)]">
                  Arr library already uses <span className="font-mono text-[var(--mm-text)]">{radHint}</span> — you can paste the same base URL here.
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
                onChange={(e) => {
                  setRadUrl(e.target.value);
                  setRadDirty(true);
                }}
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
                  onChange={(e) => {
                    setRadKey(e.target.value);
                    setRadDirty(true);
                  }}
                />
                <button type="button" className={mmActionButtonClass({ variant: "secondary" })} onClick={() => setShowRadKey(!showRadKey)}>
                  {showRadKey ? "Hide" : "Show"}
                </button>
              </div>
              <div className="mt-4 flex flex-wrap gap-2">
                <button
                  type="button"
                  className={mmActionButtonClass({ variant: radDirty ? "primary" : "secondary", disabled: dis || !radDirty })}
                  disabled={dis || !radDirty}
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
              <ConnectionStatusPanel
                check={radCheck}
                idleHelper="Save your URL and API key, then run a test to confirm Radarr is reachable."
                fmt={fmt}
              />
            </SubberSettingsSubsection>
            </RadarrConnectionSection>

            <SyncActionsSection>
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
            </SyncActionsSection>
          </SubberSettingsSection>

          <PathMappingSection>
          <SubberSettingsSection
            title="Path mapping"
            description="Only needed when Subber and Radarr run in separate containers."
          >
            <MmOnOffSwitch
              id="subber-rad-map"
              label="Enable Radarr path mapping"
              enabled={radMapEn}
              disabled={dis}
              onChange={(v) => {
                setRadMapEn(v);
                setRadMapDirty(true);
              }}
            />
            {radMapEn ? (
              <>
                <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
                  <label className="block min-w-0 flex-1 text-sm text-[var(--mm-text2)]">
                    Path as Radarr reports it
                    <div className="mt-1 flex flex-col gap-2 sm:flex-row">
                      <input
                        className="mm-input w-full font-mono text-sm"
                        value={radArr}
                        disabled={dis}
                        onChange={(e) => {
                          setRadArr(e.target.value);
                          setRadMapDirty(true);
                        }}
                      />
                      <ServerFolderPickerButton
                        title="Choose Radarr Movies path"
                        value={radArr}
                        disabled={dis}
                        onSelect={(path) => {
                          setRadArr(path);
                          setRadMapDirty(true);
                        }}
                      />
                    </div>
                  </label>
                  <label className="block min-w-0 flex-1 text-sm text-[var(--mm-text2)]">
                    Path as MediaMop sees it
                    <div className="mt-1 flex flex-col gap-2 sm:flex-row">
                      <input
                        className="mm-input w-full font-mono text-sm"
                        value={radSub}
                        disabled={dis}
                        onChange={(e) => {
                          setRadSub(e.target.value);
                          setRadMapDirty(true);
                        }}
                      />
                      <ServerFolderPickerButton
                        title="Choose MediaMop Movies path"
                        value={radSub}
                        disabled={dis}
                        onSelect={(path) => {
                          setRadSub(path);
                          setRadMapDirty(true);
                        }}
                      />
                    </div>
                  </label>
                </div>
                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    className={mmActionButtonClass({ variant: "secondary", disabled: dis || radRootFoldersFetch.isPending })}
                    disabled={dis || radRootFoldersFetch.isPending}
                    onClick={() => void detectRadarrRootFolders()}
                  >
                    {radRootFoldersFetch.isPending ? "Detecting..." : "Detect Radarr paths"}
                  </button>
                  <p className="basis-full text-xs text-[var(--mm-text2)]">
                    Pulls Radarr root folders through the API. Use these when Radarr reports container or NAS paths differently from MediaMop.
                  </p>
                </div>
                <ArrRootFolderChoices
                  label="Radarr"
                  folders={radRootFolders}
                  message={radRootMessage}
                  error={radRootError}
                  onUseArr={(path) => {
                    setRadArr(path);
                    setRadMapDirty(true);
                  }}
                  onUseBoth={(path) => {
                    setRadArr(path);
                    setRadSub(path);
                    setRadMapDirty(true);
                  }}
                />
              </>
            ) : null}
            <button
              type="button"
              className={mmActionButtonClass({ variant: radMapDirty ? "primary" : "secondary", disabled: dis || !radMapDirty })}
              disabled={dis || !radMapDirty}
              onClick={() => void saveRadarrPathMapping()}
              data-testid="subber-save-radarr-path-mapping"
            >
              Save Radarr path mapping
            </button>
            <SaveFeedback ok={saveRadMap.ok} err={saveRadMap.err} />
          </SubberSettingsSection>
          </PathMappingSection>
        </div>
      </div>
    </div>
  );
}
