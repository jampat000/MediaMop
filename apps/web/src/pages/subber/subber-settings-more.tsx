import { useEffect, useState } from "react";
import { fetchCsrfToken } from "../../lib/api/auth-api";
import { MmOnOffSwitch } from "../../components/ui/mm-on-off-switch";
import { mmActionButtonClass } from "../../lib/ui/mm-control-roles";
import type { SubberProviderPutIn } from "../../lib/subber/subber-api";
import {
  usePutSubberProviderMutation,
  usePutSubberSettingsMutation,
  useSubberProvidersQuery,
  useSubberSettingsQuery,
  useSubberTestProviderMutation,
} from "../../lib/subber/subber-queries";

const MASK = "\u2022".repeat(10);

export function SubberSettingsMoreSections({ canOperate }: { canOperate: boolean }) {
  const q = useSubberSettingsQuery();
  const pq = useSubberProvidersQuery();
  const put = usePutSubberSettingsMutation();
  const putProv = usePutSubberProviderMutation();
  const testProv = useSubberTestProviderMutation();

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

  useEffect(() => {
    const d = q.data;
    if (!d) return;
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

  const dis = !canOperate || put.isPending;
  const sorted = [...(pq.data ?? [])].sort((a, b) => a.priority - b.priority || a.provider_key.localeCompare(b.provider_key));

  async function saveExcludeHearing() {
    const csrf_token = await fetchCsrfToken();
    await put.mutateAsync({ csrf_token, exclude_hearing_impaired: excludeHi });
  }

  async function saveSearchFrequency() {
    const csrf_token = await fetchCsrfToken();
    await put.mutateAsync({
      csrf_token,
      adaptive_searching_enabled: adaptEn,
      adaptive_searching_max_attempts: adaptMax,
      adaptive_searching_delay_hours: adaptDelayH,
      permanent_skip_after_attempts: adaptPerm,
    });
  }

  async function savePathMapping() {
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
  }

  async function saveProviderRow(pk: string, enabled: boolean, priority: number) {
    const csrf_token = await fetchCsrfToken();
    const body: SubberProviderPutIn = { csrf_token, enabled, priority };
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

  if (!q.data) return null;

  return (
    <>
      <section className="space-y-3 rounded-md border border-[var(--mm-border)] bg-[var(--mm-card-bg)] p-5" data-testid="subber-providers-section">
        <h2 className="text-base font-semibold text-[var(--mm-text)]">Subtitle Providers</h2>
        <p className="text-sm text-[var(--mm-text2)]">
          Subber searches providers in order until a subtitle is found. Lower priority number = searched first. Enable at least one provider to start downloading subtitles.
        </p>
        {pq.isLoading ? <p className="text-sm text-[var(--mm-text2)]">Loading providers…</p> : null}
        <ul className="space-y-4">
          {sorted.map((p) => (
            <li key={p.provider_key} className="rounded border border-[var(--mm-border)] bg-black/10 p-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="font-medium text-[var(--mm-text)]">{p.display_name}</span>
                <MmOnOffSwitch
                  id={`prov-en-${p.provider_key}`}
                  label="Enabled"
                  enabled={p.enabled}
                  disabled={dis || putProv.isPending}
                  onChange={(v) => void saveProviderRow(p.provider_key, v, provPri[p.provider_key] ?? p.priority)}
                />
              </div>
              <label className="mt-2 block text-xs text-[var(--mm-text2)]">
                Priority (order)
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
              <div className="mt-2 flex flex-wrap gap-2">
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
                  {p.has_credentials ? "Credentials stored" : "Not configured"}
                </span>
              </div>
              {provMsg[p.provider_key] ? <p className="text-xs text-[var(--mm-text)]">{provMsg[p.provider_key]}</p> : null}
            </li>
          ))}
        </ul>
      </section>

      <section className="space-y-3 rounded-md border border-[var(--mm-border)] bg-[var(--mm-card-bg)] p-5">
        <h2 className="text-base font-semibold text-[var(--mm-text)]">Subtitle Style</h2>
        <MmOnOffSwitch
          id="subber-exclude-hi"
          label="Exclude hearing impaired"
          enabled={excludeHi}
          disabled={dis}
          onChange={setExcludeHi}
        />
        <p className="text-xs text-[var(--mm-text2)]">
          When on, Subber skips subtitles that include sound descriptions for hearing impaired viewers (for example [DOOR CREAKS]).
        </p>
        <button type="button" className={mmActionButtonClass({ variant: "primary", disabled: dis })} disabled={dis} onClick={() => void saveExcludeHearing()}>
          Save subtitle style
        </button>
      </section>

      <section className="space-y-3 rounded-md border border-[var(--mm-border)] bg-[var(--mm-card-bg)] p-5">
        <h2 className="text-base font-semibold text-[var(--mm-text)]">Search Frequency</h2>
        <MmOnOffSwitch id="subber-adapt" label="Enable adaptive searching" enabled={adaptEn} disabled={dis} onChange={setAdaptEn} />
        <p className="text-xs text-[var(--mm-text2)]">
          When on, Subber searches less often for files that repeatedly return no results, protecting API quotas.
        </p>
        {adaptEn ? (
          <div className="space-y-2">
            <label className="block text-sm text-[var(--mm-text2)]">
              Back off after failed attempts
              <input type="number" className="mm-input mt-1 w-28" min={1} max={100} value={adaptMax} disabled={dis} onChange={(e) => setAdaptMax(Number(e.target.value) || 1)} />
            </label>
            <label className="block text-sm text-[var(--mm-text2)]">
              Wait hours before retrying after back-off
              <input type="number" className="mm-input mt-1 w-28" min={1} max={8760} value={adaptDelayH} disabled={dis} onChange={(e) => setAdaptDelayH(Number(e.target.value) || 1)} />
            </label>
            <label className="block text-sm text-[var(--mm-text2)]">
              Give up after total attempts (then mark skipped)
              <input type="number" className="mm-input mt-1 w-28" min={1} max={10000} value={adaptPerm} disabled={dis} onChange={(e) => setAdaptPerm(Number(e.target.value) || 1)} />
            </label>
          </div>
        ) : null}
        <button type="button" className={mmActionButtonClass({ variant: "primary", disabled: dis })} disabled={dis} onClick={() => void saveSearchFrequency()}>
          Save search frequency settings
        </button>
      </section>

      <section className="space-y-3 rounded-md border border-[var(--mm-border)] bg-[var(--mm-card-bg)] p-5">
        <h2 className="text-base font-semibold text-[var(--mm-text)]">Path Mapping</h2>
        <p className="text-sm text-[var(--mm-text2)]">
          Only needed if Sonarr/Radarr and MediaMop see different paths to the same files (e.g. separate machines or containers). Leave disabled if everything runs on one host.
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
      </section>
    </>
  );
}
