import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";

import { AuthBrandStack } from "../../components/brand/auth-brand-stack";
import { PageLoading } from "../../components/shared/page-loading";
import { MmListboxPicker } from "../../components/ui/mm-listbox-picker";
import { ServerFolderPickerButton } from "../../components/ui/server-folder-picker-button";
import { useMeQuery } from "../../lib/auth/queries";
import {
  writeFromRefinerLibrary,
  type RefinerLibrary,
  type RefinerMediaType,
} from "../../lib/refiner/libraries-api";
import {
  useCreateRefinerLibrary,
  useRefinerLibrariesQuery,
  useUpdateRefinerLibrary,
} from "../../lib/refiner/libraries-queries";
import {
  curatedTimezoneOptionsSorted,
  CURATED_TIMEZONE_ID_SET,
} from "../../lib/suite/timezone-options";
import {
  useSuiteSettingsQuery,
  useSuiteSettingsSaveMutation,
} from "../../lib/suite/queries";
import {
  persistDisplayDensity,
  readStoredDisplayDensity,
  type DisplayDensity,
} from "../../lib/ui/display-density";
import { mmActionButtonClass } from "../../lib/ui/mm-control-roles";

const LANDING_OPTIONS = [
  // "/" is In hand since 3.0 (#463); the dashboard moved to /dashboard.
  { value: "/", label: "In hand" },
  { value: "/dashboard", label: "Dashboard" },
  { value: "/refiner", label: "Refiner" },
] as const;

const BACKUP_INTERVAL_OPTIONS = [
  { value: "24", label: "Every day" },
  { value: "48", label: "Every 2 days" },
  { value: "168", label: "Every week" },
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
      <h2 className="text-base font-semibold text-[var(--mm-text1)]">
        {title}
      </h2>
      <p className="mt-1 text-sm text-[var(--mm-text2)]">{description}</p>
      <div className="mt-4 space-y-4">{children}</div>
    </section>
  );
}

/** The library the wizard edits for a media type: the first one, when any exist. */
function firstLibraryOfType(
  libraries: RefinerLibrary[] | undefined,
  mediaType: RefinerMediaType,
): RefinerLibrary | undefined {
  return (libraries ?? [])
    .filter((library) => library.media_type === mediaType)
    .sort((a, b) => a.display_order - b.display_order)[0];
}

export function SetupWizardPage() {
  const navigate = useNavigate();
  const me = useMeQuery();
  const settingsQ = useSuiteSettingsQuery();
  const refinerQ = useRefinerLibrariesQuery();
  const saveSuite = useSuiteSettingsSaveMutation();
  const createLibrary = useCreateRefinerLibrary();
  const updateLibrary = useUpdateRefinerLibrary();

  const [appTimezone, setAppTimezone] = useState<string>("UTC");
  const [displayDensity, setDisplayDensity] = useState<DisplayDensity>(() =>
    readStoredDisplayDensity(),
  );
  const [landingPath, setLandingPath] = useState<string>("/");
  const [backupEnabled, setBackupEnabled] = useState(false);
  const [backupIntervalHours, setBackupIntervalHours] = useState("24");
  const [backupPreferredTime, setBackupPreferredTime] = useState("02:00");
  const [movieWatchedFolder, setMovieWatchedFolder] = useState("");
  const [movieOutputFolder, setMovieOutputFolder] = useState("");
  const [tvWatchedFolder, setTvWatchedFolder] = useState("");
  const [tvOutputFolder, setTvOutputFolder] = useState("");
  const [statusMessage, setStatusMessage] = useState<string | null>(null);

  const seededSettings = useRef(false);
  const seededRefiner = useRef(false);

  useEffect(() => {
    if (!settingsQ.data || seededSettings.current) {
      return;
    }
    seededSettings.current = true;
    const tz = (settingsQ.data.app_timezone || "UTC").trim() || "UTC";
    setAppTimezone(CURATED_TIMEZONE_ID_SET.has(tz) ? tz : "UTC");
    setBackupEnabled(Boolean(settingsQ.data.configuration_backup_enabled));
    setBackupIntervalHours(
      String(settingsQ.data.configuration_backup_interval_hours || 24),
    );
    setBackupPreferredTime(
      (settingsQ.data.configuration_backup_preferred_time || "02:00").trim() ||
        "02:00",
    );
  }, [settingsQ.data]);

  useEffect(() => {
    if (!refinerQ.data || seededRefiner.current) {
      return;
    }
    seededRefiner.current = true;
    const movies = firstLibraryOfType(refinerQ.data, "movie");
    const tv = firstLibraryOfType(refinerQ.data, "tv");
    setMovieWatchedFolder(movies?.watched_folder ?? "");
    setMovieOutputFolder(movies?.output_folder ?? "");
    setTvWatchedFolder(tv?.watched_folder ?? "");
    setTvOutputFolder(tv?.output_folder ?? "");
  }, [refinerQ.data]);

  useEffect(() => {
    const isLoading = me.isPending || settingsQ.isPending || refinerQ.isPending;
    const wState = (settingsQ.data?.setup_wizard_state || "pending")
      .trim()
      .toLowerCase();
    if (isLoading || wState !== "pending") return;
    const handler = (e: BeforeUnloadEvent) => {
      e.preventDefault();
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [me.isPending, settingsQ.isPending, settingsQ.data, refinerQ.isPending]);

  const wizardState = (settingsQ.data?.setup_wizard_state || "pending")
    .trim()
    .toLowerCase();
  const timezoneOptions = useMemo(
    () =>
      curatedTimezoneOptionsSorted().map((tz) => ({
        value: tz.id,
        label: tz.label,
      })),
    [],
  );

  const loading = me.isPending || settingsQ.isPending || refinerQ.isPending;

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
              The wizard could not load the current suite settings. Open
              Settings later and try again.
            </p>
            <p className="mm-auth-footer-link">
              <Link to="/">Continue to the app</Link>
            </p>
          </div>
        </div>
      </main>
    );
  }

  const savePending =
    saveSuite.isPending || createLibrary.isPending || updateLibrary.isPending;

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
        <ServerFolderPickerButton
          title={title}
          value={value}
          disabled={savePending}
          onSelect={setter}
        />
      </div>
    );
  }

  /**
   * The wizard edits the first Refiner library of each media type. When there is none yet it
   * adds one, but only if a folder was entered: an empty library would do nothing.
   */
  async function saveWizardLibrary(
    libraries: RefinerLibrary[],
    step: {
      mediaType: RefinerMediaType;
      name: string;
      watchedFolder: string;
      outputFolder: string;
    },
  ) {
    const existing = firstLibraryOfType(libraries, step.mediaType);
    if (existing) {
      if (
        existing.watched_folder === step.watchedFolder &&
        existing.output_folder === step.outputFolder
      ) {
        return;
      }
      await updateLibrary.mutateAsync({
        id: existing.id,
        data: {
          ...writeFromRefinerLibrary(existing),
          watched_folder: step.watchedFolder,
          output_folder: step.outputFolder,
        },
      });
      return;
    }
    if (!step.watchedFolder && !step.outputFolder) {
      return;
    }
    await createLibrary.mutateAsync({
      name: step.name,
      media_type: step.mediaType,
      watched_folder: step.watchedFolder,
      output_folder: step.outputFolder,
    });
  }

  async function saveWizardState(nextState: "skipped" | "completed") {
    setStatusMessage(null);
    const current = settingsQ.data!;
    const librariesCurrent = refinerQ.data;

    if (tvWatchedFolder.trim() && !tvOutputFolder.trim()) {
      setStatusMessage(
        "TV Refiner setup needs an output folder when a TV watched folder is set.",
      );
      return;
    }
    if (movieWatchedFolder.trim() && !movieOutputFolder.trim()) {
      setStatusMessage(
        "Movies Refiner setup needs an output folder when a Movies watched folder is set.",
      );
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
        configuration_backup_interval_hours: Number.parseInt(
          backupIntervalHours,
          10,
        ),
        configuration_backup_preferred_time: backupPreferredTime,
      });

      if (librariesCurrent) {
        await saveWizardLibrary(librariesCurrent, {
          mediaType: "movie",
          name: "Movies",
          watchedFolder: movieWatchedFolder.trim(),
          outputFolder: movieOutputFolder.trim(),
        });
        await saveWizardLibrary(librariesCurrent, {
          mediaType: "tv",
          name: "TV",
          watchedFolder: tvWatchedFolder.trim(),
          outputFolder: tvOutputFolder.trim(),
        });
      }

      void navigate(landingPath, { replace: true });
    } catch (err) {
      setStatusMessage(
        err instanceof Error ? err.message : "Could not save setup.",
      );
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
            Set the suite basics, backup schedule, and starter connections now.
            You can skip this and reopen it later from Settings.
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
                  <div
                    className="grid gap-2 sm:grid-cols-2"
                    role="radiogroup"
                    aria-label="Open first"
                  >
                    {LANDING_OPTIONS.map((option) => (
                      <label
                        key={option.value}
                        className={[
                          "relative isolate flex min-h-[2.6rem] min-w-0 cursor-pointer items-center gap-2.5 overflow-hidden rounded-md border px-3 py-2 text-sm transition-colors",
                          landingPath === option.value
                            ? "border-[var(--mm-accent)] bg-[var(--mm-accent-soft)] text-[var(--mm-text)]"
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
                        <span className="min-w-0 whitespace-nowrap font-medium text-[var(--mm-text)]">
                          {option.label}
                        </span>
                      </label>
                    ))}
                  </div>
                </div>
              </div>
              <div>
                <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--mm-text3)]">
                  Display density
                </p>
                <div
                  className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4"
                  role="radiogroup"
                  aria-label="Display density"
                >
                  {(
                    [
                      {
                        id: "compact" as const,
                        label: "Compact",
                        hint: "Smaller layout",
                      },
                      {
                        id: "default" as const,
                        label: "Balanced",
                        hint: "Readable default",
                      },
                      {
                        id: "comfortable" as const,
                        label: "Comfortable",
                        hint: "Larger controls",
                      },
                      {
                        id: "expanded" as const,
                        label: "Expanded",
                        hint: "Big-screen mode",
                      },
                    ] as const
                  ).map(({ id, label, hint }) => (
                    <label
                      key={id}
                      className={[
                        "flex min-w-0 cursor-pointer items-center gap-2.5 rounded-md border px-3 py-2 text-sm transition-colors",
                        displayDensity === id
                          ? "border-[var(--mm-accent)] bg-[var(--mm-accent-soft)] text-[var(--mm-text)]"
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
                        <span className="block font-medium text-[var(--mm-text)]">
                          {label}
                        </span>
                        <span className="block text-xs text-[var(--mm-text3)]">
                          {hint}
                        </span>
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
                    onChange={(e) =>
                      setBackupPreferredTime(e.target.value || "02:00")
                    }
                  />
                </label>
              </div>
            </WizardSection>

            <WizardSection
              title="Refiner basics"
              description="Choose watched and output folders for TV and Movies. These fill in the first Refiner library of each type, and MediaMop adds one if there is none yet. Add more libraries or change their rules on the Refiner page."
            >
              <div className="grid gap-4 lg:grid-cols-2">
                <div className="space-y-3">
                  <h3 className="text-sm font-semibold text-[var(--mm-text1)]">
                    TV
                  </h3>
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
                  <h3 className="text-sm font-semibold text-[var(--mm-text1)]">
                    Movies
                  </h3>
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
              {savePending
                ? "Saving..."
                : wizardState === "pending"
                  ? "Finish setup"
                  : "Save changes"}
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
