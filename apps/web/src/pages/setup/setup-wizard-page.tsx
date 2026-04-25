import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";

import { AuthBrandStack } from "../../components/brand/auth-brand-stack";
import { PageLoading } from "../../components/shared/page-loading";
import { MmListboxPicker } from "../../components/ui/mm-listbox-picker";
import { ServerFolderPickerButton } from "../../components/ui/server-folder-picker-button";
import { fetchCsrfToken } from "../../lib/api/auth-api";
import { useMeQuery } from "../../lib/auth/queries";
import { patchPrunerInstance, postPrunerInstance, type PrunerServerInstance } from "../../lib/pruner/api";
import { usePrunerInstancesQuery } from "../../lib/pruner/queries";
import { useRefinerPathSettingsQuery, useRefinerPathSettingsSaveMutation } from "../../lib/refiner/queries";
import {
  curatedTimezoneOptionsSorted,
  CURATED_TIMEZONE_ID_SET,
} from "../../lib/suite/timezone-options";
import { useSuiteSettingsQuery, useSuiteSettingsSaveMutation } from "../../lib/suite/queries";
import { usePutSubberSettingsMutation, useSubberSettingsQuery } from "../../lib/subber/subber-queries";
import { persistDisplayDensity, readStoredDisplayDensity, type DisplayDensity } from "../../lib/ui/display-density";
import { mmActionButtonClass } from "../../lib/ui/mm-control-roles";

const LANDING_OPTIONS = [
  { value: "/app", label: "Dashboard" },
  { value: "/app/refiner", label: "Refiner" },
  { value: "/app/pruner", label: "Pruner" },
  { value: "/app/subber", label: "Subber" },
] as const;

const BACKUP_INTERVAL_OPTIONS = [
  { value: "24", label: "Every day" },
  { value: "48", label: "Every 2 days" },
  { value: "168", label: "Every week" },
] as const;

const PRUNER_PROVIDER_OPTIONS = [
  { value: "jellyfin", label: "Jellyfin" },
  { value: "emby", label: "Emby" },
  { value: "plex", label: "Plex" },
] as const;

function WizardSection({
  title,
  description,
  children,
}: {
  title: string;
  description: string;
  children: ReactNode;
}) {
  return (
    <section className="rounded-lg border border-[var(--mm-border)] bg-[var(--mm-card-bg)]/40 p-4">
      <h2 className="text-base font-semibold text-[var(--mm-text1)]">{title}</h2>
      <p className="mt-1 text-sm text-[var(--mm-text2)]">{description}</p>
      <div className="mt-4 space-y-4">{children}</div>
    </section>
  );
}

function normalizeCsvLanguages(raw: string): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const part of raw.split(",")) {
    const value = part.trim().toLowerCase();
    if (!value || seen.has(value)) {
      continue;
    }
    seen.add(value);
    out.push(value);
  }
  return out;
}

function labelForPrunerSecret(provider: string): string {
  return provider === "plex" ? "Plex token" : "API key";
}

function defaultPrunerDisplayName(provider: "jellyfin" | "emby" | "plex"): string {
  const label = PRUNER_PROVIDER_OPTIONS.find((option) => option.value === provider)?.label ?? "Media server";
  return `${label} server`;
}

export function SetupWizardPage() {
  const navigate = useNavigate();
  const me = useMeQuery();
  const settingsQ = useSuiteSettingsQuery();
  const refinerQ = useRefinerPathSettingsQuery();
  const subberQ = useSubberSettingsQuery();
  const prunerInstancesQ = usePrunerInstancesQuery();
  const saveSuite = useSuiteSettingsSaveMutation();
  const saveRefiner = useRefinerPathSettingsSaveMutation();
  const saveSubber = usePutSubberSettingsMutation();

  const [appTimezone, setAppTimezone] = useState<string>("UTC");
  const [displayDensity, setDisplayDensity] = useState<DisplayDensity>(() => readStoredDisplayDensity());
  const [landingPath, setLandingPath] = useState<string>("/app");
  const [backupEnabled, setBackupEnabled] = useState(false);
  const [backupIntervalHours, setBackupIntervalHours] = useState("24");
  const [backupPreferredTime, setBackupPreferredTime] = useState("02:00");
  const [movieWatchedFolder, setMovieWatchedFolder] = useState("");
  const [movieOutputFolder, setMovieOutputFolder] = useState("");
  const [tvWatchedFolder, setTvWatchedFolder] = useState("");
  const [tvOutputFolder, setTvOutputFolder] = useState("");
  const [prunerProvider, setPrunerProvider] = useState<"jellyfin" | "emby" | "plex">("jellyfin");
  const [prunerBaseUrl, setPrunerBaseUrl] = useState("");
  const [prunerSecret, setPrunerSecret] = useState("");
  const [sonarrBaseUrl, setSonarrBaseUrl] = useState("");
  const [sonarrApiKey, setSonarrApiKey] = useState("");
  const [radarrBaseUrl, setRadarrBaseUrl] = useState("");
  const [radarrApiKey, setRadarrApiKey] = useState("");
  const [openSubtitlesApiKey, setOpenSubtitlesApiKey] = useState("");
  const [languagePreferencesCsv, setLanguagePreferencesCsv] = useState("en");
  const [statusMessage, setStatusMessage] = useState<string | null>(null);

  useEffect(() => {
    if (!settingsQ.data) {
      return;
    }
    const tz = (settingsQ.data.app_timezone || "UTC").trim() || "UTC";
    setAppTimezone(CURATED_TIMEZONE_ID_SET.has(tz) ? tz : "UTC");
    setBackupEnabled(Boolean(settingsQ.data.configuration_backup_enabled));
    setBackupIntervalHours(String(settingsQ.data.configuration_backup_interval_hours || 24));
    setBackupPreferredTime((settingsQ.data.configuration_backup_preferred_time || "02:00").trim() || "02:00");
  }, [settingsQ.data]);

  useEffect(() => {
    if (!refinerQ.data) {
      return;
    }
    setMovieWatchedFolder(refinerQ.data.refiner_watched_folder ?? "");
    setMovieOutputFolder(refinerQ.data.refiner_output_folder ?? "");
    setTvWatchedFolder(refinerQ.data.refiner_tv_watched_folder ?? "");
    setTvOutputFolder(refinerQ.data.refiner_tv_output_folder ?? "");
  }, [refinerQ.data]);

  useEffect(() => {
    if (!subberQ.data) {
      return;
    }
    setSonarrBaseUrl(subberQ.data.sonarr_base_url ?? "");
    setRadarrBaseUrl(subberQ.data.radarr_base_url ?? "");
    setLanguagePreferencesCsv(
      subberQ.data.language_preferences.length > 0 ? subberQ.data.language_preferences.join(", ") : "en",
    );
  }, [subberQ.data]);

  useEffect(() => {
    const first = prunerInstancesQ.data?.[0];
    if (!first) {
      return;
    }
    const provider = String(first.provider) as "jellyfin" | "emby" | "plex";
    setPrunerProvider(provider);
    setPrunerBaseUrl(first.base_url || "");
  }, [prunerInstancesQ.data]);

  const wizardState = (settingsQ.data?.setup_wizard_state || "pending").trim().toLowerCase();
  const timezoneOptions = useMemo(
    () => curatedTimezoneOptionsSorted().map((tz) => ({ value: tz.id, label: tz.label })),
    [],
  );

  const loading =
    me.isPending || settingsQ.isPending || refinerQ.isPending || subberQ.isPending || prunerInstancesQ.isPending;

  if (loading) {
    return <PageLoading label="Loading setup wizard" />;
  }
  if (!me.data) {
    return <Navigate to="/login" replace />;
  }
  if (settingsQ.isError || !settingsQ.data) {
    return (
      <main className="mm-auth-body" id="mm-main-content" tabIndex={-1}>
        <div className="mm-auth-frame">
          <AuthBrandStack />
          <div className="mm-auth-card">
            <p className="mm-auth-eyebrow">Setup wizard</p>
            <h1 className="mm-auth-title">Could not load setup</h1>
            <p className="mm-auth-lead">
              The wizard could not load the current suite settings. Open Settings later and try again.
            </p>
            <p className="mm-auth-footer-link">
              <Link to="/app">Continue to the app</Link>
            </p>
          </div>
        </div>
      </main>
    );
  }

  const savePending =
    saveSuite.isPending ||
    saveRefiner.isPending ||
    saveSubber.isPending;

  function renderFolderInput({
    value,
    setter,
    placeholder,
    title,
  }: {
    value: string;
    setter: (value: string) => void;
    placeholder: string;
    title: string;
  }) {
    return (
      <div className="flex flex-col gap-2 sm:flex-row">
        <input
          className="mm-input w-full"
          value={value}
          onChange={(e) => setter(e.target.value)}
          placeholder={placeholder}
          disabled={savePending}
        />
        <ServerFolderPickerButton title={title} value={value} disabled={savePending} onSelect={setter} />
      </div>
    );
  }

  async function saveWizardState(nextState: "skipped" | "completed") {
    setStatusMessage(null);
    const current = settingsQ.data!;
    const refinerCurrent = refinerQ.data;
    const subberCurrent = subberQ.data;

    if (tvWatchedFolder.trim() && !tvOutputFolder.trim()) {
      setStatusMessage("TV Refiner setup needs an output folder when a TV watched folder is set.");
      return;
    }
    if (movieWatchedFolder.trim() && !movieOutputFolder.trim()) {
      setStatusMessage("Movies Refiner setup needs an output folder when a Movies watched folder is set.");
      return;
    }
    if ((prunerBaseUrl.trim() && !prunerSecret.trim()) || (!prunerBaseUrl.trim() && prunerSecret.trim())) {
      setStatusMessage("Pruner setup needs both a base URL and a connection secret.");
      return;
    }

    persistDisplayDensity(displayDensity);

    try {
      await saveSuite.mutateAsync({
        product_display_name: current.product_display_name,
        signed_in_home_notice: current.signed_in_home_notice,
        setup_wizard_state: nextState,
        app_timezone: appTimezone,
        log_retention_days: current.log_retention_days,
        application_logs_enabled: true,
        configuration_backup_enabled: backupEnabled,
        configuration_backup_interval_hours: Number.parseInt(backupIntervalHours, 10),
        configuration_backup_preferred_time: backupPreferredTime,
      });

      if (refinerCurrent) {
        await saveRefiner.mutateAsync({
          refiner_watched_folder: movieWatchedFolder.trim() ? movieWatchedFolder.trim() : null,
          refiner_work_folder: refinerCurrent.refiner_work_folder,
          refiner_output_folder: movieOutputFolder.trim() ? movieOutputFolder.trim() : null,
          refiner_tv_paths_included: true,
          refiner_tv_watched_folder: tvWatchedFolder.trim() ? tvWatchedFolder.trim() : null,
          refiner_tv_work_folder: refinerCurrent.refiner_tv_work_folder,
          refiner_tv_output_folder: tvOutputFolder.trim() ? tvOutputFolder.trim() : null,
          movie_watched_folder_check_interval_seconds: refinerCurrent.movie_watched_folder_check_interval_seconds,
          tv_watched_folder_check_interval_seconds: refinerCurrent.tv_watched_folder_check_interval_seconds,
        });
      }

      if (subberCurrent) {
        await saveSubber.mutateAsync({
          csrf_token: await fetchCsrfToken(),
          sonarr_base_url: sonarrBaseUrl.trim(),
          sonarr_api_key: sonarrApiKey.trim() || undefined,
          radarr_base_url: radarrBaseUrl.trim(),
          radarr_api_key: radarrApiKey.trim() || undefined,
          opensubtitles_api_key: openSubtitlesApiKey.trim() || undefined,
          language_preferences: normalizeCsvLanguages(languagePreferencesCsv),
        });
      }

      if (prunerBaseUrl.trim() && prunerSecret.trim()) {
        const existing: PrunerServerInstance | undefined =
          prunerInstancesQ.data?.find((row) => row.provider === prunerProvider);
        const credentials: Record<string, string> =
          prunerProvider === "plex"
            ? { auth_token: prunerSecret.trim() }
            : { api_key: prunerSecret.trim() };
        const displayName = existing?.display_name?.trim() || defaultPrunerDisplayName(prunerProvider);
        if (existing) {
          await patchPrunerInstance(existing.id, {
            display_name: displayName,
            base_url: prunerBaseUrl.trim(),
            enabled: true,
            credentials,
          });
        } else {
          await postPrunerInstance({
            provider: prunerProvider,
            display_name: displayName,
            base_url: prunerBaseUrl.trim(),
            credentials,
          });
        }
      }

      navigate(landingPath, { replace: true });
    } catch (err) {
      setStatusMessage(err instanceof Error ? err.message : "Could not save setup.");
    }
  }

  return (
    <main className="mm-auth-body" id="mm-main-content" tabIndex={-1}>
      <div className="mm-auth-frame mm-setup-wizard-frame">
        <AuthBrandStack />
        <div className="mm-auth-card mm-setup-wizard-card">
          <p className="mm-auth-eyebrow">First run</p>
          <h1 className="mm-auth-title">Setup wizard</h1>
          <p className="mm-auth-lead">
            Set the suite basics, backup schedule, and starter connections now. You can skip this and reopen it later from Settings.
          </p>

          <div className="grid gap-4 lg:grid-cols-2">
            <WizardSection
              title="App basics"
              description="Set the app clock, visual density, and where MediaMop opens after setup."
            >
              <div className="space-y-4">
                <div className="max-w-md">
                  <label
                    id="setup-wizard-timezone"
                    className="mb-1 block text-xs font-semibold uppercase tracking-wide text-[var(--mm-text3)]"
                  >
                    Timezone
                  </label>
                  <MmListboxPicker
                    ariaLabelledBy="setup-wizard-timezone"
                    placeholder="Select timezone"
                    disabled={savePending}
                    options={timezoneOptions}
                    value={appTimezone}
                    onChange={(value) => setAppTimezone(value)}
                  />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-[var(--mm-text3)]">
                    Open first
                  </label>
                  <div className="grid gap-2 sm:grid-cols-2" role="radiogroup" aria-label="Open first">
                    {LANDING_OPTIONS.map((option) => (
                      <label
                        key={option.value}
                        className={[
                          "relative isolate flex min-h-[2.6rem] min-w-0 cursor-pointer items-center gap-2.5 overflow-hidden rounded-md border px-3 py-2 text-sm transition-colors",
                          landingPath === option.value
                            ? "border-[var(--mm-accent)] bg-[rgba(212,175,55,0.14)] text-[var(--mm-text)]"
                            : "border-[var(--mm-border)] bg-transparent text-[var(--mm-text2)] hover:bg-[var(--mm-card-bg)]",
                        ].join(" ")}
                      >
                        <input
                          type="radio"
                          name="setup-landing-path"
                          className="h-4 w-4 shrink-0 accent-[var(--mm-accent)]"
                          checked={landingPath === option.value}
                          onChange={() => setLandingPath(option.value)}
                        />
                        <span className="min-w-0 whitespace-nowrap font-medium text-[var(--mm-text)]">{option.label}</span>
                      </label>
                    ))}
                  </div>
                </div>
              </div>
              <div>
                <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--mm-text3)]">Display density</p>
                <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4" role="radiogroup" aria-label="Display density">
                  {(
                    [
                      { id: "compact" as const, label: "Compact", hint: "Smaller layout" },
                      { id: "default" as const, label: "Balanced", hint: "Readable default" },
                      { id: "comfortable" as const, label: "Comfortable", hint: "Larger controls" },
                      { id: "expanded" as const, label: "Expanded", hint: "Big-screen mode" },
                    ] as const
                  ).map(({ id, label, hint }) => (
                    <label
                      key={id}
                      className={[
                        "flex min-w-0 cursor-pointer items-center gap-2.5 rounded-md border px-3 py-2 text-sm transition-colors",
                        displayDensity === id
                          ? "border-[var(--mm-accent)] bg-[rgba(212,175,55,0.14)] text-[var(--mm-text)]"
                          : "border-[var(--mm-border)] bg-transparent text-[var(--mm-text2)] hover:bg-[var(--mm-card-bg)]",
                      ].join(" ")}
                    >
                      <input
                        type="radio"
                        name="setup-display-density"
                        className="h-4 w-4 shrink-0 accent-[var(--mm-accent)]"
                        checked={displayDensity === id}
                        onChange={() => setDisplayDensity(id)}
                      />
                      <span className="min-w-0">
                        <span className="block font-medium text-[var(--mm-text)]">{label}</span>
                        <span className="block text-xs text-[var(--mm-text3)]">{hint}</span>
                      </span>
                    </label>
                  ))}
                </div>
              </div>
            </WizardSection>

            <WizardSection
              title="Automatic backups"
              description="Keep a rolling local copy of your MediaMop configuration."
            >
              <label className="flex cursor-pointer items-start gap-2.5 text-sm text-[var(--mm-text2)]">
                <input
                  type="checkbox"
                  className="mt-0.5 h-4 w-4 shrink-0 accent-[var(--mm-accent)]"
                  checked={backupEnabled}
                  onChange={(e) => setBackupEnabled(e.target.checked)}
                />
                <span>Run automatic configuration backups</span>
              </label>
              <div className="grid gap-4 lg:grid-cols-2">
                <label className="block text-sm text-[var(--mm-text2)]">
                  <span className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-[var(--mm-text3)]">
                    Minimum time between runs
                  </span>
                  <select
                    className="mm-input w-full"
                    value={backupIntervalHours}
                    disabled={!backupEnabled}
                    onChange={(e) => setBackupIntervalHours(e.target.value)}
                  >
                    {BACKUP_INTERVAL_OPTIONS.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="block text-sm text-[var(--mm-text2)]">
                  <span className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-[var(--mm-text3)]">
                    Preferred backup time
                  </span>
                  <input
                    type="time"
                    className="mm-input w-full"
                    value={backupPreferredTime}
                    disabled={!backupEnabled}
                    onChange={(e) => setBackupPreferredTime(e.target.value || "02:00")}
                  />
                </label>
              </div>
            </WizardSection>

            <WizardSection
              title="Refiner basics"
              description="Choose watched and output folders for TV and Movies. Detailed remux rules stay on the Refiner page."
            >
              <div className="grid gap-4 lg:grid-cols-2">
                <div className="space-y-3">
                  <h3 className="text-sm font-semibold text-[var(--mm-text1)]">TV</h3>
                  {renderFolderInput({
                    value: tvWatchedFolder,
                    setter: setTvWatchedFolder,
                    placeholder: "TV watched folder",
                    title: "Choose TV watched folder",
                  })}
                  {renderFolderInput({
                    value: tvOutputFolder,
                    setter: setTvOutputFolder,
                    placeholder: "TV output folder",
                    title: "Choose TV output folder",
                  })}
                </div>
                <div className="space-y-3">
                  <h3 className="text-sm font-semibold text-[var(--mm-text1)]">Movies</h3>
                  {renderFolderInput({
                    value: movieWatchedFolder,
                    setter: setMovieWatchedFolder,
                    placeholder: "Movies watched folder",
                    title: "Choose Movies watched folder",
                  })}
                  {renderFolderInput({
                    value: movieOutputFolder,
                    setter: setMovieOutputFolder,
                    placeholder: "Movies output folder",
                    title: "Choose Movies output folder",
                  })}
                </div>
              </div>
            </WizardSection>

            <WizardSection
              title="Pruner connection"
              description="Optionally add one media server so Pruner can preview cleanup candidates."
            >
              <div className="grid gap-4 lg:grid-cols-1">
                <label className="block text-sm text-[var(--mm-text2)]">
                  <span className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-[var(--mm-text3)]">
                    Server type
                  </span>
                  <select
                    className="mm-input w-full"
                    value={prunerProvider}
                    onChange={(e) => setPrunerProvider(e.target.value as "jellyfin" | "emby" | "plex")}
                  >
                    {PRUNER_PROVIDER_OPTIONS.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              <div className="grid gap-4 lg:grid-cols-2">
                <label className="block text-sm text-[var(--mm-text2)]">
                  <span className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-[var(--mm-text3)]">
                    Base URL
                  </span>
                  <input
                    className="mm-input w-full"
                    value={prunerBaseUrl}
                    onChange={(e) => setPrunerBaseUrl(e.target.value)}
                    placeholder={prunerProvider === "plex" ? "http://127.0.0.1:32400" : "http://127.0.0.1:8096"}
                  />
                </label>
                <label className="block text-sm text-[var(--mm-text2)]">
                  <span className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-[var(--mm-text3)]">
                    {labelForPrunerSecret(prunerProvider)}
                  </span>
                  <input
                    className="mm-input w-full"
                    value={prunerSecret}
                    onChange={(e) => setPrunerSecret(e.target.value)}
                    placeholder={labelForPrunerSecret(prunerProvider)}
                  />
                </label>
              </div>
            </WizardSection>

            <WizardSection
              title="Subber basics"
              description="Optionally save Sonarr, Radarr, and default subtitle language preferences."
            >
              <div className="grid gap-4 lg:grid-cols-2">
                <div className="space-y-3">
                  <h3 className="text-sm font-semibold text-[var(--mm-text1)]">Sonarr</h3>
                  <input
                    className="mm-input w-full"
                    value={sonarrBaseUrl}
                    onChange={(e) => setSonarrBaseUrl(e.target.value)}
                    placeholder="http://127.0.0.1:8989"
                  />
                  <input
                    className="mm-input w-full"
                    value={sonarrApiKey}
                    onChange={(e) => setSonarrApiKey(e.target.value)}
                    placeholder="Sonarr API key"
                  />
                </div>
                <div className="space-y-3">
                  <h3 className="text-sm font-semibold text-[var(--mm-text1)]">Radarr</h3>
                  <input
                    className="mm-input w-full"
                    value={radarrBaseUrl}
                    onChange={(e) => setRadarrBaseUrl(e.target.value)}
                    placeholder="http://127.0.0.1:7878"
                  />
                  <input
                    className="mm-input w-full"
                    value={radarrApiKey}
                    onChange={(e) => setRadarrApiKey(e.target.value)}
                    placeholder="Radarr API key"
                  />
                </div>
              </div>
              <div className="grid gap-4 lg:grid-cols-2">
                <label className="block text-sm text-[var(--mm-text2)]">
                  <span className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-[var(--mm-text3)]">
                    Preferred subtitle languages
                  </span>
                  <input
                    className="mm-input w-full"
                    value={languagePreferencesCsv}
                    onChange={(e) => setLanguagePreferencesCsv(e.target.value)}
                    placeholder="en, es"
                  />
                </label>
                <label className="block text-sm text-[var(--mm-text2)]">
                  <span className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-[var(--mm-text3)]">
                    OpenSubtitles API key
                  </span>
                  <input
                    className="mm-input w-full"
                    value={openSubtitlesApiKey}
                    onChange={(e) => setOpenSubtitlesApiKey(e.target.value)}
                    placeholder="Optional provider key"
                  />
                </label>
              </div>
            </WizardSection>
          </div>

          {statusMessage ? (
            <p className="mm-auth-banner mt-4" role="alert">
              {statusMessage}
            </p>
          ) : null}

          <div className="mt-4 flex flex-wrap gap-3">
            <button
              type="button"
              className="mm-auth-submit"
              onClick={() => void saveWizardState("completed")}
              disabled={savePending}
            >
              {savePending ? "Saving..." : wizardState === "pending" ? "Finish setup" : "Save changes"}
            </button>
            <button
              type="button"
              data-testid="setup-wizard-skip"
              className={mmActionButtonClass({
                variant: "secondary",
                disabled: savePending,
              })}
              onClick={() => void saveWizardState("skipped")}
              disabled={savePending}
            >
              Skip for now
            </button>
          </div>
        </div>
      </div>
    </main>
  );
}
