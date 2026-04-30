import { useEffect, useState, type ReactNode } from "react";
import { fetchCsrfToken } from "../../lib/api/auth-api";
import { MmOnOffSwitch } from "../../components/ui/mm-on-off-switch";
import { mmActionButtonClass } from "../../lib/ui/mm-control-roles";
import type {
  SubberProviderOut,
  SubberProviderPutIn,
} from "../../lib/subber/subber-api";
import {
  usePutSubberProviderMutation,
  useSubberProvidersQuery,
  useSubberTestOpensubtitlesMutation,
  useSubberTestProviderMutation,
} from "../../lib/subber/subber-queries";

const MASK = "\u2022".repeat(10);

function providerNeedsConfigureButton(p: SubberProviderOut): boolean {
  if (!p.available) return false;
  if (p.requires_account) return true;
  if (p.provider_key === "podnapisi") return true;
  return false;
}

function providerImplemented(providerKey: string): boolean {
  return providerKey !== "subscene" && providerKey !== "addic7ed";
}

export function SubberProvidersTab({ canOperate }: { canOperate: boolean }) {
  const pq = useSubberProvidersQuery();
  const putProv = usePutSubberProviderMutation();
  const testOs = useSubberTestOpensubtitlesMutation();
  const testProv = useSubberTestProviderMutation();

  const [provUser, setProvUser] = useState<Record<string, string>>({});
  const [provPass, setProvPass] = useState<Record<string, string>>({});
  const [provKey, setProvKey] = useState<Record<string, string>>({});
  const [provPri, setProvPri] = useState<Record<string, number | null>>({});
  const [provMsg, setProvMsg] = useState<Record<string, string | null>>({});
  const [provDirty, setProvDirty] = useState<Record<string, boolean>>({});
  const [expandedProviderKey, setExpandedProviderKey] = useState<string | null>(
    null,
  );

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

  const dis = !canOperate || putProv.isPending;

  async function saveProviderRow(
    pk: string,
    enabledP: boolean,
    priority: number | null,
  ) {
    const csrf_token = await fetchCsrfToken();
    const body: SubberProviderPutIn = {
      csrf_token,
      enabled: enabledP,
      priority: priority ?? undefined,
    };
    const u = provUser[pk]?.trim();
    const p = provPass[pk]?.trim();
    const k = provKey[pk]?.trim();
    if (u) body.username = u;
    if (p) body.password = p;
    if (k) body.api_key = k;
    await putProv.mutateAsync({ providerKey: pk, body });
  }

  async function saveExpandedProvider(
    pk: string,
    enabledP: boolean,
    priority: number | null,
  ) {
    try {
      await saveProviderRow(pk, enabledP, priority);
      setProvDirty((d) => ({ ...d, [pk]: false }));
      setExpandedProviderKey(null);
    } catch {
      /* keep dirty / expanded */
    }
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

  async function runTestOs(pk: string) {
    setProvMsg((m) => ({ ...m, [pk]: null }));
    try {
      const r = await testOs.mutateAsync();
      setProvMsg((m) => ({
        ...m,
        [pk]: r.ok ? "Connected" : (r.message ?? "Error"),
      }));
    } catch (e) {
      setProvMsg((m) => ({ ...m, [pk]: (e as Error).message }));
    }
  }

  const sorted = [...(pq.data ?? [])].sort(
    (a, b) =>
      (a.priority ?? 999_999) - (b.priority ?? 999_999) ||
      a.provider_key.localeCompare(b.provider_key),
  );

  return (
    <div className="mm-bubble-stack" data-testid="subber-providers-tab">
      <section
        className="overflow-hidden rounded-lg border border-[var(--mm-border)] bg-[var(--mm-card-bg)] shadow-sm"
        data-testid="subber-providers-section"
      >
        <header className="border-b border-[var(--mm-border)] bg-black/10 px-5 py-4">
          <p className="text-[0.7rem] font-semibold uppercase tracking-[0.12em] text-[var(--mm-text2)]">
            Sources
          </p>
          <h2 className="mt-1 text-lg font-semibold tracking-tight text-[var(--mm-text)]">
            Subtitle providers
          </h2>
        </header>
        <div className="px-5 py-5">
          {pq.isLoading ? (
            <p className="text-sm text-[var(--mm-text2)]">Loading providers…</p>
          ) : pq.isError ? (
            <p className="text-sm text-red-600">
              {(pq.error as Error).message}
            </p>
          ) : (
            <ul className="divide-y divide-[var(--mm-border)] rounded-md border border-[var(--mm-border)] bg-black/10">
              {sorted.map((p) => {
                const pri = provPri[p.provider_key] ?? p.priority ?? null;
                const provMsgText = provMsg[p.provider_key];
                const showCfg = providerNeedsConfigureButton(p);
                const expanded = expandedProviderKey === p.provider_key;
                const isDirty = provDirty[p.provider_key] ?? false;
                let statusEl: ReactNode;
                if (provMsgText) {
                  statusEl =
                    provMsgText === "Connected" ? (
                      <span className="text-xs font-medium text-emerald-600">
                        {provMsgText}
                      </span>
                    ) : (
                      <span
                        className="max-w-[14rem] truncate text-xs text-[var(--mm-text2)]"
                        title={provMsgText}
                      >
                        {provMsgText}
                      </span>
                    );
                } else if (!p.available) {
                  statusEl = (
                    <span className="text-xs text-amber-400">
                      {p.availability_note ?? "Not available"}
                    </span>
                  );
                } else if (p.requires_account) {
                  statusEl = p.has_credentials ? (
                    <span className="text-xs font-medium text-emerald-600">
                      Configured
                    </span>
                  ) : (
                    <span className="text-xs text-[var(--mm-text2)]">
                      Not configured
                    </span>
                  );
                } else if (p.provider_key === "podnapisi") {
                  statusEl = (
                    <span className="text-xs text-[var(--mm-text2)]">
                      Optional credentials
                    </span>
                  );
                } else {
                  statusEl = (
                    <span className="text-xs text-[var(--mm-text2)]">—</span>
                  );
                }
                return (
                  <li
                    key={p.provider_key}
                    className={[
                      "transition-colors",
                      p.enabled
                        ? "border-l-2 border-l-[rgba(212,175,55,0.6)] bg-[var(--mm-card-bg)]/60"
                        : "border-l-2 border-l-transparent bg-[var(--mm-card-bg)]/40",
                    ].join(" ")}
                  >
                    <button
                      type="button"
                      className="flex w-full items-center gap-4 px-4 py-3.5 text-left transition-colors hover:bg-white/[0.02]"
                      disabled={!p.available}
                      onClick={() =>
                        setExpandedProviderKey(expanded ? null : p.provider_key)
                      }
                    >
                      <span
                        className={[
                          "h-2 w-2 shrink-0 rounded-full",
                          p.enabled &&
                          (p.has_credentials || !p.requires_account)
                            ? "bg-emerald-500"
                            : p.enabled &&
                                p.requires_account &&
                                !p.has_credentials
                              ? "bg-red-500"
                              : "bg-[var(--mm-border)]",
                        ].join(" ")}
                      />
                      <span className="min-w-[10rem] text-sm font-semibold text-[var(--mm-text)]">
                        {p.display_name}
                      </span>
                      <span className="text-xs text-[var(--mm-text2)]">
                        {statusEl}
                      </span>
                      <span className="ml-auto flex items-center gap-3">
                        <span className="text-xs text-[var(--mm-text3)]">
                          Priority{" "}
                          {p.priority !== null && p.priority !== undefined
                            ? p.priority
                            : "—"}
                        </span>
                        <svg
                          aria-hidden
                          className={[
                            "h-4 w-4 shrink-0 text-[var(--mm-text3)] transition-transform",
                            expanded ? "rotate-180" : "",
                          ].join(" ")}
                          viewBox="0 0 20 20"
                          fill="currentColor"
                        >
                          <path d="M5.5 7.5 10 12l4.5-4.5H5.5z" />
                        </svg>
                      </span>
                    </button>

                    {expanded ? (
                      <div className="border-t border-[var(--mm-border)] bg-black/20 px-4 pb-4 pt-4">
                        <div className="space-y-4">
                          {p.provider_key === "podnapisi" &&
                          !p.requires_account ? (
                            <p className="text-xs text-[var(--mm-text2)]">
                              No account required — credentials optional.
                            </p>
                          ) : null}
                          {p.requires_account ? (
                            <div className="grid gap-3 sm:grid-cols-2">
                              <label className="block text-xs text-[var(--mm-text2)]">
                                Username
                                <input
                                  className="mm-input mt-1 w-full"
                                  disabled={dis}
                                  value={provUser[p.provider_key] ?? ""}
                                  onChange={(e) => {
                                    setProvUser((x) => ({
                                      ...x,
                                      [p.provider_key]: e.target.value,
                                    }));
                                    setProvDirty((d) => ({
                                      ...d,
                                      [p.provider_key]: true,
                                    }));
                                  }}
                                />
                              </label>
                              <label className="block text-xs text-[var(--mm-text2)]">
                                Password{" "}
                                {p.has_credentials ? (
                                  <span className="text-[0.7rem]">
                                    (leave blank to keep)
                                  </span>
                                ) : null}
                                <input
                                  type="password"
                                  className="mm-input mt-1 w-full"
                                  disabled={dis}
                                  placeholder={p.has_credentials ? MASK : ""}
                                  value={provPass[p.provider_key] ?? ""}
                                  onChange={(e) => {
                                    setProvPass((x) => ({
                                      ...x,
                                      [p.provider_key]: e.target.value,
                                    }));
                                    setProvDirty((d) => ({
                                      ...d,
                                      [p.provider_key]: true,
                                    }));
                                  }}
                                />
                              </label>
                              {p.provider_key.includes("opensubtitles") ? (
                                <label className="block text-xs text-[var(--mm-text2)]">
                                  API key
                                  <input
                                    type="password"
                                    className="mm-input mt-1 w-full"
                                    disabled={dis}
                                    placeholder={p.has_credentials ? MASK : ""}
                                    value={provKey[p.provider_key] ?? ""}
                                    onChange={(e) => {
                                      setProvKey((x) => ({
                                        ...x,
                                        [p.provider_key]: e.target.value,
                                      }));
                                      setProvDirty((d) => ({
                                        ...d,
                                        [p.provider_key]: true,
                                      }));
                                    }}
                                  />
                                </label>
                              ) : null}
                            </div>
                          ) : p.provider_key === "podnapisi" ? (
                            <div className="grid gap-3 sm:grid-cols-2">
                              <label className="block text-xs text-[var(--mm-text2)]">
                                Username (optional)
                                <input
                                  className="mm-input mt-1 w-full"
                                  disabled={dis}
                                  value={provUser[p.provider_key] ?? ""}
                                  onChange={(e) => {
                                    setProvUser((x) => ({
                                      ...x,
                                      [p.provider_key]: e.target.value,
                                    }));
                                    setProvDirty((d) => ({
                                      ...d,
                                      [p.provider_key]: true,
                                    }));
                                  }}
                                />
                              </label>
                              <label className="block text-xs text-[var(--mm-text2)]">
                                Password (optional)
                                <input
                                  type="password"
                                  className="mm-input mt-1 w-full"
                                  disabled={dis}
                                  placeholder={p.has_credentials ? MASK : ""}
                                  value={provPass[p.provider_key] ?? ""}
                                  onChange={(e) => {
                                    setProvPass((x) => ({
                                      ...x,
                                      [p.provider_key]: e.target.value,
                                    }));
                                    setProvDirty((d) => ({
                                      ...d,
                                      [p.provider_key]: true,
                                    }));
                                  }}
                                />
                              </label>
                            </div>
                          ) : null}

                          <div className="flex flex-wrap items-center gap-3 border-t border-[var(--mm-border)] pt-3">
                            <label className="flex items-center gap-2 text-xs text-[var(--mm-text2)]">
                              Priority
                              <input
                                type="number"
                                className="mm-input max-w-[4rem] text-sm"
                                disabled={dis}
                                value={pri ?? ""}
                                onChange={(e) => {
                                  const v = e.target.value;
                                  setProvPri((x) => ({
                                    ...x,
                                    [p.provider_key]:
                                      v === ""
                                        ? null
                                        : Math.max(
                                            0,
                                            Math.min(9999, Number(v) || 0),
                                          ),
                                  }));
                                }}
                                onBlur={() => {
                                  if (pri !== p.priority)
                                    void saveProviderRow(
                                      p.provider_key,
                                      p.enabled,
                                      pri,
                                    );
                                }}
                              />
                            </label>
                            <div className="flex items-center gap-2">
                              <MmOnOffSwitch
                                id={`prov-en-${p.provider_key}`}
                                label="Enabled"
                                layout="inline"
                                enabled={p.enabled}
                                disabled={
                                  dis ||
                                  putProv.isPending ||
                                  !providerImplemented(p.provider_key)
                                }
                                onChange={(v) =>
                                  void saveProviderRow(p.provider_key, v, pri)
                                }
                              />
                            </div>
                            <div className="ml-auto flex gap-2">
                              {showCfg ? (
                                <>
                                  <button
                                    type="button"
                                    className={mmActionButtonClass({
                                      variant: isDirty
                                        ? "primary"
                                        : "secondary",
                                      disabled:
                                        dis || putProv.isPending || !isDirty,
                                    })}
                                    disabled={
                                      dis || putProv.isPending || !isDirty
                                    }
                                    onClick={() =>
                                      void saveExpandedProvider(
                                        p.provider_key,
                                        p.enabled,
                                        pri,
                                      )
                                    }
                                    data-testid={
                                      p.provider_key === "opensubtitles_org" ||
                                      p.provider_key === "opensubtitles_com"
                                        ? "subber-save-opensubtitles"
                                        : undefined
                                    }
                                  >
                                    Save
                                  </button>
                                  <button
                                    type="button"
                                    className={mmActionButtonClass({
                                      variant: "secondary",
                                      disabled:
                                        dis ||
                                        (p.provider_key ===
                                          "opensubtitles_org" ||
                                        p.provider_key === "opensubtitles_com"
                                          ? testOs.isPending
                                          : testProv.isPending),
                                    })}
                                    disabled={
                                      dis ||
                                      (p.provider_key === "opensubtitles_org" ||
                                      p.provider_key === "opensubtitles_com"
                                        ? testOs.isPending
                                        : testProv.isPending)
                                    }
                                    onClick={() => {
                                      if (
                                        p.provider_key ===
                                          "opensubtitles_org" ||
                                        p.provider_key === "opensubtitles_com"
                                      ) {
                                        void runTestOs(p.provider_key);
                                      } else {
                                        void runProvTest(p.provider_key);
                                      }
                                    }}
                                    data-testid={
                                      p.provider_key === "opensubtitles_org" ||
                                      p.provider_key === "opensubtitles_com"
                                        ? "subber-test-opensubtitles"
                                        : undefined
                                    }
                                  >
                                    Test
                                  </button>
                                </>
                              ) : null}
                            </div>
                          </div>

                          {provMsg[p.provider_key] ? (
                            <p
                              className={[
                                "text-xs",
                                provMsg[p.provider_key] === "Connected"
                                  ? "text-emerald-500"
                                  : "text-red-400",
                              ].join(" ")}
                            >
                              {provMsg[p.provider_key]}
                            </p>
                          ) : null}
                        </div>
                      </div>
                    ) : null}
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </section>
    </div>
  );
}
