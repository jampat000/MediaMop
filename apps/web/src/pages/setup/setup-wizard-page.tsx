import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";

import { AuthBrandStack } from "../../components/brand/auth-brand-stack";
import { PageLoading } from "../../components/shared/page-loading";
import { MmListboxPicker } from "../../components/ui/mm-listbox-picker";
import { ServerFolderPickerButton } from "../../components/ui/server-folder-picker-button";
import { useMeQuery } from "../../lib/auth/queries";
import {
  writeFromProcessingLibrary,
  type ProcessingLibrary,
  type ProcessingMediaType,
} from "../../lib/processing/libraries-api";
import {
  useCreateProcessingLibrary,
  useProcessingLibrariesQuery,
  useUpdateProcessingLibrary,
} from "../../lib/processing/libraries-queries";
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

const WIZARD_DENSITY_OPTIONS: ReadonlyArray<{
  id: DisplayDensity;
  label: string;
  hint: string;
}> = [
  { id: "compact", label: "Compact", hint: "Tighter, fits more" },
  { id: "default", label: "Balanced", hint: "The default" },
  { id: "comfortable", label: "Comfortable", hint: "Larger text" },
  { id: "expanded", label: "Expanded", hint: "For big screens" },
];

const BACKUP_INTERVAL_OPTIONS = [
  { value: "24", label: "Every day" },
  { value: "48", label: "Every 2 days" },
  { value: "168", label: "Every week" },
] as const;

function WizardSection({
  headingId,
  title,
  description,
  children,
}: {
  headingId: string;
  title: string;
  description: string;
  children: ReactNode;
}) {
  return (
    <section className="mm-quiet-section" aria-labelledby={headingId}>
      <div className="mm-quiet-section__head">
        <h2 id={headingId} className="mm-quiet-section__title">
          {title}
        </h2>
      </div>
      <div className="mm-quiet-section__body">
        <div className="flex flex-col gap-3">
          <p className="mm-quiet-note">{description}</p>
          {children}
        </div>
      </div>
    </section>
  );
}

/** The library the wizard edits for a media type: the first one, when any exist. */
function firstLibraryOfType(
  libraries: ProcessingLibrary[] | undefined,
  mediaType: ProcessingMediaType,
): ProcessingLibrary | undefined {
  return (libraries ?? [])
    .filter((library) => library.media_type === mediaType)
    .sort((a, b) => a.display_order - b.display_order)[0];
}

export function SetupWizardPage() {
  const navigate = useNavigate();
  const me = useMeQuery();
  const settingsQ = useSuiteSettingsQuery();
  const processingQ = useProcessingLibrariesQuery();
  const saveSuite = useSuiteSettingsSaveMutation();
  const createLibrary = useCreateProcessingLibrary();
  const updateLibrary = useUpdateProcessingLibrary();

  const [appTimezone, setAppTimezone] = useState<string>("UTC");
  const [displayDensity, setDisplayDensity] = useState<DisplayDensity>(() =>
    readStoredDisplayDensity(),
  );
  const [backupEnabled, setBackupEnabled] = useState(false);
  const [backupIntervalHours, setBackupIntervalHours] = useState("24");
  const [backupPreferredTime, setBackupPreferredTime] = useState("02:00");
  const [movieWatchedFolder, setMovieWatchedFolder] = useState("");
  const [movieOutputFolder, setMovieOutputFolder] = useState("");
  const [tvWatchedFolder, setTvWatchedFolder] = useState("");
  const [tvOutputFolder, setTvOutputFolder] = useState("");
  const [statusMessage, setStatusMessage] = useState<string | null>(null);

  const seededSettings = useRef(false);
  const seededProcessing = useRef(false);

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
    if (!processingQ.data || seededProcessing.current) {
      return;
    }
    seededProcessing.current = true;
    const movies = firstLibraryOfType(processingQ.data, "movie");
    const tv = firstLibraryOfType(processingQ.data, "tv");
    setMovieWatchedFolder(movies?.watched_folder ?? "");
    setMovieOutputFolder(movies?.output_folder ?? "");
    setTvWatchedFolder(tv?.watched_folder ?? "");
    setTvOutputFolder(tv?.output_folder ?? "");
  }, [processingQ.data]);

  useEffect(() => {
    const isLoading =
      me.isPending || settingsQ.isPending || processingQ.isPending;
    const wState = (settingsQ.data?.setup_wizard_state || "pending")
      .trim()
      .toLowerCase();
    if (isLoading || wState !== "pending") return;
    const handler = (e: BeforeUnloadEvent) => {
      e.preventDefault();
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [
    me.isPending,
    settingsQ.isPending,
    settingsQ.data,
    processingQ.isPending,
  ]);

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

  const loading = me.isPending || settingsQ.isPending || processingQ.isPending;

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
              The wizard could not load the current settings. Open Settings
              later and try again.
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
    id,
    label,
    visibleLabel,
    hint,
    value,
    setter,
  }: {
    id: string;
    /** Full name for assistive tech, e.g. "Movies watched folder". */
    label: string;
    visibleLabel: string;
    hint: string;
    value: string;
    setter: (value: string) => void;
  }) {
    return (
      <div className="min-w-0">
        <label htmlFor={id} className="mm-wizard-label">
          {visibleLabel}
        </label>
        <div className="mm-wizard-folder">
          <input
            id={id}
            className="mm-input w-full"
            value={value}
            onChange={(e) => setter(e.target.value)}
            placeholder={hint}
            aria-label={label}
            disabled={savePending}
          />
          <ServerFolderPickerButton
            title={`Choose ${label}`}
            value={value}
            disabled={savePending}
            onSelect={setter}
          />
        </div>
      </div>
    );
  }

  /**
   * The wizard edits the first library of each media type. When there is none yet it
   * adds one, but only if a folder was entered: an empty library would do nothing.
   */
  async function saveWizardLibrary(
    libraries: ProcessingLibrary[],
    step: {
      mediaType: ProcessingMediaType;
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
          ...writeFromProcessingLibrary(existing),
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
    const librariesCurrent = processingQ.data;

    if (tvWatchedFolder.trim() && !tvOutputFolder.trim()) {
      setStatusMessage(
        "Add a TV output folder: it is needed when a TV watched folder is set.",
      );
      return;
    }
    if (movieWatchedFolder.trim() && !movieOutputFolder.trim()) {
      setStatusMessage(
        "Add a Movies output folder: it is needed when a Movies watched folder is set.",
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

      void navigate("/", { replace: true });
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
          <h1 className="mm-auth-title">Set up Weir</h1>
          <p className="mm-auth-lead">
            A few basics to get Weir going. Everything here can be changed later
            in Settings and Processing, and you can skip it for now.
          </p>

          <div className="mm-quiet-stack mt-5">
            <WizardSection
              headingId="setup-wizard-basics-heading"
              title="Basics"
              description="The clock Weir uses, and how dense the screens are in this browser."
            >
              <div className="mm-wizard-basics">
                <div className="min-w-0">
                  <span id="setup-wizard-timezone" className="mm-wizard-label">
                    Time zone
                  </span>
                  <MmListboxPicker
                    ariaLabelledBy="setup-wizard-timezone"
                    placeholder="Select time zone"
                    disabled={savePending}
                    options={timezoneOptions}
                    value={appTimezone}
                    onChange={(value) => setAppTimezone(value)}
                  />
                </div>
                <div className="min-w-0">
                  <span id="setup-wizard-density" className="mm-wizard-label">
                    Display density
                  </span>
                  <div
                    className="mm-density-options mm-density-options--wide"
                    role="radiogroup"
                    aria-labelledby="setup-wizard-density"
                  >
                    {WIZARD_DENSITY_OPTIONS.map(({ id, label, hint }) => (
                      <label
                        key={id}
                        className={`mm-density-option${displayDensity === id ? " mm-density-option--selected" : ""}`}
                      >
                        <input
                          type="radio"
                          name="setup-display-density"
                          className="mm-density-option__input"
                          checked={displayDensity === id}
                          onChange={() => setDisplayDensity(id)}
                        />
                        <span className="min-w-0">
                          <span className="mm-density-option__label">
                            {label}
                          </span>
                          <span className="mm-density-option__hint">
                            {hint}
                          </span>
                        </span>
                      </label>
                    ))}
                  </div>
                </div>
              </div>
            </WizardSection>

            <WizardSection
              headingId="setup-wizard-libraries-heading"
              title="Libraries"
              description="Where your downloader finishes files, and where Weir puts them once cleaned for your media manager to import. This fills in your first Movies and TV library; add more, and set their audio and subtitle rules, on the Processing page."
            >
              <div className="mm-wizard-libraries">
                {(
                  [
                    {
                      key: "movie",
                      heading: "Movies",
                      watched: movieWatchedFolder,
                      setWatched: setMovieWatchedFolder,
                      output: movieOutputFolder,
                      setOutput: setMovieOutputFolder,
                    },
                    {
                      key: "tv",
                      heading: "TV",
                      watched: tvWatchedFolder,
                      setWatched: setTvWatchedFolder,
                      output: tvOutputFolder,
                      setOutput: setTvOutputFolder,
                    },
                  ] as const
                ).map((group) => (
                  <fieldset key={group.key} className="mm-wizard-library">
                    <legend className="mm-wizard-library__title">
                      {group.heading}
                    </legend>
                    {renderFolderInput({
                      id: `setup-wizard-${group.key}-watched`,
                      label: `${group.heading} watched folder`,
                      visibleLabel: "Watched folder",
                      hint: "Where finished downloads land",
                      value: group.watched,
                      setter: group.setWatched,
                    })}
                    {renderFolderInput({
                      id: `setup-wizard-${group.key}-output`,
                      label: `${group.heading} output folder`,
                      visibleLabel: "Output folder",
                      hint: "Where cleaned files go",
                      value: group.output,
                      setter: group.setOutput,
                    })}
                  </fieldset>
                ))}
              </div>
            </WizardSection>

            <WizardSection
              headingId="setup-wizard-backups-heading"
              title="Automatic backups"
              description="Keep a rolling local copy of your Weir configuration."
            >
              <label className="flex cursor-pointer items-start gap-2.5 text-sm text-[var(--mm-text1)]">
                <input
                  type="checkbox"
                  className="mt-0.5 h-4 w-4 shrink-0 accent-[var(--mm-accent)]"
                  checked={backupEnabled}
                  onChange={(e) => setBackupEnabled(e.target.checked)}
                />
                <span>Back up the configuration automatically</span>
              </label>
              <div className="mm-wizard-backup-fields">
                <label className="block min-w-0">
                  <span className="mm-wizard-label">
                    Minimum time between backups
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
                <label className="block min-w-0">
                  <span className="mm-wizard-label">Preferred time</span>
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
