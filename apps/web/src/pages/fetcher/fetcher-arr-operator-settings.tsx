import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { PageLoading } from "../../components/shared/page-loading";
import { isHttpErrorFromApi, isLikelyNetworkFailure } from "../../lib/api/error-guards";
import {
  useFetcherArrOperatorSettingsQuery,
  useFetcherArrSearchLaneSaveMutation,
} from "../../lib/fetcher/arr-operator-settings/queries";
import type { FetcherArrOperatorSettingsOut, FetcherArrSearchLane } from "../../lib/fetcher/arr-operator-settings/types";
import { showFetcherArrOperatorSettingsEditor } from "../../lib/fetcher/failed-imports/eligibility";
import {
  FETCHER_SECTION_RADARR_HEADING,
  FETCHER_SECTION_SCHEDULES_HEADING,
  FETCHER_SECTION_SONARR_HEADING,
  FETCHER_TAB_RADARR_LABEL,
  FETCHER_TAB_SONARR_LABEL,
} from "./fetcher-display-names";
import { FetcherConnectionsPanels } from "./fetcher-connections-panels";
import { FetcherEnableSwitch } from "./fetcher-enable-switch";
import { fetcherMenuButtonClass } from "./fetcher-menu-button";
import {
  FETCHER_TAB_PANEL_BLURB_CLASS,
  FETCHER_TAB_PANEL_INTRO_CLASS,
  FETCHER_TAB_PANEL_TITLE_CLASS,
} from "./fetcher-tab-panel-intro";
import {
  MM_SCHEDULE_TIME_WINDOW_HEADING,
  MM_SCHEDULE_TIME_WINDOW_HELPER,
  MmScheduleDayChips,
  MmScheduleTimeFields,
} from "../../components/ui/mm-schedule-window-controls";
import { draftDiffersFromCommittedLabel } from "./fetcher-numeric-settings-draft";

export type FetcherArrSettingsTabId = "connections" | "sonarr" | "radarr" | "schedules";

type LaneDraftKey = "sonarr_missing" | "sonarr_upgrade" | "radarr_missing" | "radarr_upgrade";

function cloneLanes(data: FetcherArrOperatorSettingsOut): {
  sonarr_missing: FetcherArrSearchLane;
  sonarr_upgrade: FetcherArrSearchLane;
  radarr_missing: FetcherArrSearchLane;
  radarr_upgrade: FetcherArrSearchLane;
} {
  return {
    sonarr_missing: { ...data.sonarr_missing },
    sonarr_upgrade: { ...data.sonarr_upgrade },
    radarr_missing: { ...data.radarr_missing },
    radarr_upgrade: { ...data.radarr_upgrade },
  };
}

function laneShapeEqual(a: FetcherArrSearchLane, b: FetcherArrSearchLane): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}

function mergeDraftWithFreshServerLanes(
  prevDraft: ReturnType<typeof cloneLanes> | null,
  prevServer: ReturnType<typeof cloneLanes> | null,
  freshServer: ReturnType<typeof cloneLanes>,
): ReturnType<typeof cloneLanes> {
  if (!prevDraft || !prevServer) {
    return freshServer;
  }
  const keepOrReplace = (key: LaneDraftKey): FetcherArrSearchLane => {
    const hadUnsavedLocalDraft = !laneShapeEqual(prevDraft[key], prevServer[key]);
    return hadUnsavedLocalDraft ? prevDraft[key] : freshServer[key];
  };
  return {
    sonarr_missing: keepOrReplace("sonarr_missing"),
    sonarr_upgrade: keepOrReplace("sonarr_upgrade"),
    radarr_missing: keepOrReplace("radarr_missing"),
    radarr_upgrade: keepOrReplace("radarr_upgrade"),
  };
}

function laneDirty(
  key: LaneDraftKey,
  draft: ReturnType<typeof cloneLanes>,
  server: FetcherArrOperatorSettingsOut | undefined,
): boolean {
  if (!server) {
    return false;
  }
  return JSON.stringify(draft[key]) !== JSON.stringify(server[key]);
}

/** Blank search run-interval restores to 60 minutes, expressed in seconds for the API. */
const DEFAULT_SEARCH_RUN_INTERVAL_SECONDS = 60 * 60;

const SEARCH_RUN_INTERVAL_MIN_MINUTES = 1;
const SEARCH_RUN_INTERVAL_MAX_MINUTES = 7 * 24 * 60;

function committedSearchRunIntervalMinutesLabel(lane: FetcherArrSearchLane): string {
  return String(Math.round(lane.schedule_interval_seconds / 60));
}

/** Draft is whole minutes; persisted value is seconds. */
function finalizeSearchLaneScheduleIntervalFromMinutesDraft(
  draft: string | null,
  lane: FetcherArrSearchLane,
  serverLane: FetcherArrSearchLane,
): number {
  if (draft === null) {
    return lane.schedule_interval_seconds;
  }
  const raw = draft.trim();
  if (raw === "") {
    return DEFAULT_SEARCH_RUN_INTERVAL_SECONDS;
  }
  const minutes = Number(raw);
  if (!Number.isFinite(minutes)) {
    return serverLane.schedule_interval_seconds;
  }
  const m = Math.min(
    Math.max(Math.trunc(minutes), SEARCH_RUN_INTERVAL_MIN_MINUTES),
    SEARCH_RUN_INTERVAL_MAX_MINUTES,
  );
  return Math.min(Math.max(m * 60, 60), 604800);
}

function finalizeSearchLaneRetryDelayMinutes(
  draft: string | null,
  lane: FetcherArrSearchLane,
  serverLane: FetcherArrSearchLane,
): number {
  if (draft === null) {
    return lane.retry_delay_minutes;
  }
  const raw = draft.trim();
  if (raw === "") {
    return serverLane.retry_delay_minutes;
  }
  const n = Number(raw);
  if (!Number.isFinite(n)) {
    return serverLane.retry_delay_minutes;
  }
  return Math.min(Math.max(Math.trunc(n), 1), 525600);
}

function finalizeSearchLaneMaxItemsPerRun(
  draft: string | null,
  lane: FetcherArrSearchLane,
  serverLane: FetcherArrSearchLane,
): number {
  if (draft === null) {
    return lane.max_items_per_run;
  }
  const raw = draft.trim();
  if (raw === "") {
    return serverLane.max_items_per_run;
  }
  const n = Number(raw);
  if (!Number.isFinite(n)) {
    return serverLane.max_items_per_run;
  }
  return Math.min(Math.max(Math.trunc(n), 1), 1000);
}

type SearchLaneBubbleVariant = "full" | "limitsOnly" | "scheduleOnly";

function SearchLaneBubble({
  testId,
  sectionTitle,
  sectionIntro,
  idPrefix,
  lane,
  serverLane,
  onLaneChange,
  saveLabel,
  canEdit,
  savePending,
  dirty,
  saveSuccess,
  onPersistLane,
  variant = "full",
}: {
  testId: string;
  sectionTitle: string;
  sectionIntro: string;
  idPrefix: string;
  lane: FetcherArrSearchLane;
  serverLane: FetcherArrSearchLane;
  onLaneChange: (next: FetcherArrSearchLane) => void;
  saveLabel: string;
  canEdit: boolean;
  savePending: boolean;
  dirty: boolean;
  saveSuccess: boolean;
  /** Persist this lane after merging flushed numeric draft values (avoids stale draft on save). */
  onPersistLane: (mergedLane: FetcherArrSearchLane) => void;
  /** `limitsOnly` / `scheduleOnly` split timed schedule controls from per-run limits (Fetcher Schedules vs Sonarr/Radarr tabs). */
  variant?: SearchLaneBubbleVariant;
}) {
  const disabled = !canEdit || savePending;
  const [scheduleIntervalDraft, setScheduleIntervalDraft] = useState<string | null>(null);
  const [maxItemsDraft, setMaxItemsDraft] = useState<string | null>(null);
  const [retryDelayDraft, setRetryDelayDraft] = useState<string | null>(null);

  const scheduleCommittedLabel = committedSearchRunIntervalMinutesLabel(lane);
  const maxItemsCommittedLabel = String(lane.max_items_per_run);
  const retryCommittedLabel = String(lane.retry_delay_minutes);
  const scheduleDraftPending = draftDiffersFromCommittedLabel(scheduleIntervalDraft, scheduleCommittedLabel);
  const maxItemsDraftPending = draftDiffersFromCommittedLabel(maxItemsDraft, maxItemsCommittedLabel);
  const retryDraftPending = draftDiffersFromCommittedLabel(retryDelayDraft, retryCommittedLabel);
  const effectiveDirty =
    variant === "limitsOnly"
      ? dirty || maxItemsDraftPending || retryDraftPending
      : variant === "scheduleOnly"
        ? dirty || scheduleDraftPending
        : dirty || scheduleDraftPending || maxItemsDraftPending || retryDraftPending;

  const handleSave = () => {
    const scheduleNext = finalizeSearchLaneScheduleIntervalFromMinutesDraft(scheduleIntervalDraft, lane, serverLane);
    const maxItemsNext = finalizeSearchLaneMaxItemsPerRun(maxItemsDraft, lane, serverLane);
    const retryNext = finalizeSearchLaneRetryDelayMinutes(retryDelayDraft, lane, serverLane);
    setScheduleIntervalDraft(null);
    setMaxItemsDraft(null);
    setRetryDelayDraft(null);
    const merged = {
      ...lane,
      schedule_interval_seconds: scheduleNext,
      max_items_per_run: maxItemsNext,
      retry_delay_minutes: retryNext,
    };
    onPersistLane(merged);
  };

  const commitScheduleIntervalOnBlur = () => {
    if (scheduleIntervalDraft === null) {
      return;
    }
    const nextSeconds = finalizeSearchLaneScheduleIntervalFromMinutesDraft(scheduleIntervalDraft, lane, serverLane);
    setScheduleIntervalDraft(null);
    if (nextSeconds !== lane.schedule_interval_seconds) {
      onLaneChange({ ...lane, schedule_interval_seconds: nextSeconds });
    }
  };

  const commitRetryDelayOnBlur = () => {
    if (retryDelayDraft === null) {
      return;
    }
    const nextMinutes = finalizeSearchLaneRetryDelayMinutes(retryDelayDraft, lane, serverLane);
    setRetryDelayDraft(null);
    if (nextMinutes !== lane.retry_delay_minutes) {
      onLaneChange({ ...lane, retry_delay_minutes: nextMinutes });
    }
  };

  const commitMaxItemsOnBlur = () => {
    if (maxItemsDraft === null) {
      return;
    }
    const nextMax = finalizeSearchLaneMaxItemsPerRun(maxItemsDraft, lane, serverLane);
    setMaxItemsDraft(null);
    if (nextMax !== lane.max_items_per_run) {
      onLaneChange({ ...lane, max_items_per_run: nextMax });
    }
  };

  return (
    <section
      className={[
        "mm-card mm-dash-card flex h-full min-h-0 min-w-0 flex-col gap-7 transition-shadow duration-200",
        saveSuccess
          ? "ring-2 ring-[var(--mm-accent-ring)] ring-offset-2 ring-offset-[var(--mm-bg-main)] shadow-[0_0_0_1px_rgba(212,175,55,0.12)]"
          : "",
      ].join(" ")}
      data-testid={testId}
    >
      <div>
        <h3 className="text-base font-semibold text-[var(--mm-text1)]">{sectionTitle}</h3>
        <p className="mt-1 text-sm text-[var(--mm-text2)]">{sectionIntro}</p>
      </div>

      {variant === "full" || variant === "scheduleOnly" ? (
        <>
          <FetcherEnableSwitch
            id={`${idPrefix}-lane-enable`}
            label="Enable timed scans"
            enabled={lane.enabled}
            disabled={disabled}
            onChange={(v) => onLaneChange({ ...lane, enabled: v })}
          />

          <div>
            <span className="text-sm font-medium text-[var(--mm-text1)]">Run interval (minutes)</span>
            <p className="mt-1 text-xs text-[var(--mm-text3)]">How often this search runs automatically.</p>
            <input
              type="number"
              min={SEARCH_RUN_INTERVAL_MIN_MINUTES}
              max={SEARCH_RUN_INTERVAL_MAX_MINUTES}
              className="mm-input mt-2 w-full"
              value={scheduleIntervalDraft !== null ? scheduleIntervalDraft : scheduleCommittedLabel}
              onFocus={() => setScheduleIntervalDraft(committedSearchRunIntervalMinutesLabel(lane))}
              onChange={(e) => setScheduleIntervalDraft(e.target.value)}
              onBlur={() => commitScheduleIntervalOnBlur()}
              disabled={disabled}
            />
          </div>

          <div className="space-y-3">
            <div>
              <span className="text-sm font-medium text-[var(--mm-text1)]">{MM_SCHEDULE_TIME_WINDOW_HEADING}</span>
              <p className="mt-1 text-xs text-[var(--mm-text3)]">{MM_SCHEDULE_TIME_WINDOW_HELPER}</p>
            </div>
            <div className="space-y-4">
              <FetcherEnableSwitch
                id={`${idPrefix}-schedule-limit`}
                label="Limit to these hours"
                enabled={lane.schedule_enabled}
                disabled={disabled}
                onChange={(v) => onLaneChange({ ...lane, schedule_enabled: v })}
              />
              <div className="space-y-2">
                <span className="text-sm font-medium text-[var(--mm-text1)]">Days</span>
                <MmScheduleDayChips
                  scheduleDaysCsv={lane.schedule_days}
                  disabled={disabled}
                  onChangeCsv={(csv) => onLaneChange({ ...lane, schedule_days: csv })}
                />
              </div>
              <MmScheduleTimeFields
                idPrefix={idPrefix}
                start={lane.schedule_start}
                end={lane.schedule_end}
                disabled={disabled}
                onStart={(hhmm) => onLaneChange({ ...lane, schedule_start: hhmm })}
                onEnd={(hhmm) => onLaneChange({ ...lane, schedule_end: hhmm })}
              />
            </div>
          </div>
        </>
      ) : null}

      {variant === "full" || variant === "limitsOnly" ? (
        <>
          <div>
            <span className="text-sm font-medium text-[var(--mm-text1)]">Items per run</span>
            <p className="mt-1 text-xs text-[var(--mm-text3)]">
              How many items this search will look for each time it runs.
            </p>
            <input
              type="number"
              min={1}
              max={1000}
              className="mm-input mt-2 w-full"
              value={maxItemsDraft !== null ? maxItemsDraft : maxItemsCommittedLabel}
              onFocus={() => setMaxItemsDraft(String(lane.max_items_per_run))}
              onChange={(e) => setMaxItemsDraft(e.target.value)}
              onBlur={() => commitMaxItemsOnBlur()}
              disabled={disabled}
            />
          </div>

          <div>
            <span className="text-sm font-medium text-[var(--mm-text1)]">Retry cooldown (minutes)</span>
            <p className="mt-1 text-xs text-[var(--mm-text3)]">
              How long to wait before searching the same item again.
            </p>
            <input
              type="number"
              min={1}
              max={525600}
              className="mm-input mt-2 w-full"
              value={retryDelayDraft !== null ? retryDelayDraft : retryCommittedLabel}
              onFocus={() => setRetryDelayDraft(String(lane.retry_delay_minutes))}
              onChange={(e) => setRetryDelayDraft(e.target.value)}
              onBlur={() => commitRetryDelayOnBlur()}
              disabled={disabled}
            />
          </div>
        </>
      ) : null}

      {saveSuccess ? (
        <p
          className="rounded-md border border-[rgba(212,175,55,0.45)] bg-[var(--mm-accent-soft)] px-3 py-2 text-sm font-medium text-[var(--mm-text1)]"
          role="status"
          data-testid={`${testId}-save-ok`}
        >
          Saved.
        </p>
      ) : null}

      <div className="border-t border-[var(--mm-border)] pt-5">
        <button
          type="button"
          className={`${fetcherMenuButtonClass({
            variant: "primary",
            disabled: !canEdit || !effectiveDirty || savePending,
          })} w-full`}
          disabled={!canEdit || !effectiveDirty || savePending}
          onClick={handleSave}
        >
          {savePending ? "Saving…" : saveLabel}
        </button>
      </div>
    </section>
  );
}

/** Fetcher tabs: Connections and per-app lane editors (SQLite-backed). */
export function FetcherArrOperatorSettingsSection({
  role,
  activeTab,
}: {
  role: string | undefined;
  activeTab: FetcherArrSettingsTabId;
}) {
  const q = useFetcherArrOperatorSettingsQuery();
  const saveSonarrMissing = useFetcherArrSearchLaneSaveMutation("sonarr_missing");
  const saveSonarrUpgrade = useFetcherArrSearchLaneSaveMutation("sonarr_upgrade");
  const saveRadarrMissing = useFetcherArrSearchLaneSaveMutation("radarr_missing");
  const saveRadarrUpgrade = useFetcherArrSearchLaneSaveMutation("radarr_upgrade");
  const laneSaveByKey = {
    sonarr_missing: saveSonarrMissing,
    sonarr_upgrade: saveSonarrUpgrade,
    radarr_missing: saveRadarrMissing,
    radarr_upgrade: saveRadarrUpgrade,
  } as const;
  const canEdit = showFetcherArrOperatorSettingsEditor(role);

  const [draft, setDraft] = useState<ReturnType<typeof cloneLanes> | null>(null);
  const serverSnapshotRef = useRef<ReturnType<typeof cloneLanes> | null>(null);
  const draftRef = useRef(draft);
  draftRef.current = draft;
  const [saveMessage, setSaveMessage] = useState<string | null>(null);
  const [laneSavedOutline, setLaneSavedOutline] = useState<LaneDraftKey | null>(null);

  useEffect(() => {
    if (q.data) {
      const fresh = cloneLanes(q.data);
      setDraft((prevDraft) => mergeDraftWithFreshServerLanes(prevDraft, serverSnapshotRef.current, fresh));
      serverSnapshotRef.current = fresh;
    }
  }, [q.data]);

  useEffect(() => {
    if (!laneSavedOutline) {
      return;
    }
    const t = window.setTimeout(() => setLaneSavedOutline(null), 2400);
    return () => clearTimeout(t);
  }, [laneSavedOutline]);

  const persistLaneAfterMerge = (laneKey: LaneDraftKey, mergedLane: FetcherArrSearchLane) => {
    const d = draftRef.current;
    if (!d) {
      return;
    }
    const payload = { ...d, [laneKey]: mergedLane };
    draftRef.current = payload;
    setDraft(payload);
    setSaveMessage(null);
    laneSaveByKey[laneKey].mutate(mergedLane, {
      onSuccess: () => setLaneSavedOutline(laneKey),
      onError: (e) => setSaveMessage(e instanceof Error ? e.message : "Could not save."),
    });
  };

  if (activeTab === "connections") {
    return (
      <div data-testid="fetcher-arr-operator-settings">
        <FetcherConnectionsPanels role={role} />
      </div>
    );
  }

  const isTv = activeTab === "sonarr";
  const isSchedules = activeTab === "schedules";

  const lanesBody =
    q.isPending ? (
      <PageLoading label="Loading library settings" />
    ) : q.isError ? (
      <p className="text-sm text-red-400" role="alert">
        {isLikelyNetworkFailure(q.error)
          ? "Could not reach the MediaMop API."
          : isHttpErrorFromApi(q.error)
            ? "The server refused this request."
            : "Could not load these settings."}
      </p>
    ) : q.data && draft ? (
      <>
        {isSchedules ? (
          <div className="mm-dash-grid gap-x-5 gap-y-6" data-testid="fetcher-schedules-grid">
            <div className="flex min-w-0 flex-col gap-6">
              <SearchLaneBubble
                variant="scheduleOnly"
                testId="fetcher-tv-lane-missing"
                sectionTitle="Missing TV shows"
                sectionIntro="When and how often missing TV show searches run."
                idPrefix="fetcher-tv-missing"
                lane={draft.sonarr_missing}
                serverLane={q.data.sonarr_missing}
                onLaneChange={(next) => setDraft((d) => (d ? { ...d, sonarr_missing: next } : d))}
                saveLabel="Save missing TV show schedule"
                canEdit={canEdit}
                savePending={laneSaveByKey.sonarr_missing.isPending}
                dirty={laneDirty("sonarr_missing", draft, q.data)}
                saveSuccess={laneSavedOutline === "sonarr_missing"}
                onPersistLane={(merged) => persistLaneAfterMerge("sonarr_missing", merged)}
              />
              <SearchLaneBubble
                variant="scheduleOnly"
                testId="fetcher-tv-lane-upgrade"
                sectionTitle="TV upgrades"
                sectionIntro="When and how often TV upgrade searches run."
                idPrefix="fetcher-tv-upgrade"
                lane={draft.sonarr_upgrade}
                serverLane={q.data.sonarr_upgrade}
                onLaneChange={(next) => setDraft((d) => (d ? { ...d, sonarr_upgrade: next } : d))}
                saveLabel="Save TV upgrades schedule"
                canEdit={canEdit}
                savePending={laneSaveByKey.sonarr_upgrade.isPending}
                dirty={laneDirty("sonarr_upgrade", draft, q.data)}
                saveSuccess={laneSavedOutline === "sonarr_upgrade"}
                onPersistLane={(merged) => persistLaneAfterMerge("sonarr_upgrade", merged)}
              />
            </div>
            <div className="flex min-w-0 flex-col gap-6">
              <SearchLaneBubble
                variant="scheduleOnly"
                testId="fetcher-movies-lane-missing"
                sectionTitle="Missing movies"
                sectionIntro="When and how often missing movie searches run."
                idPrefix="fetcher-movies-missing"
                lane={draft.radarr_missing}
                serverLane={q.data.radarr_missing}
                onLaneChange={(next) => setDraft((d) => (d ? { ...d, radarr_missing: next } : d))}
                saveLabel="Save missing movie schedule"
                canEdit={canEdit}
                savePending={laneSaveByKey.radarr_missing.isPending}
                dirty={laneDirty("radarr_missing", draft, q.data)}
                saveSuccess={laneSavedOutline === "radarr_missing"}
                onPersistLane={(merged) => persistLaneAfterMerge("radarr_missing", merged)}
              />
              <SearchLaneBubble
                variant="scheduleOnly"
                testId="fetcher-movies-lane-upgrade"
                sectionTitle="Movie upgrades"
                sectionIntro="When and how often movie upgrade searches run."
                idPrefix="fetcher-movies-upgrade"
                lane={draft.radarr_upgrade}
                serverLane={q.data.radarr_upgrade}
                onLaneChange={(next) => setDraft((d) => (d ? { ...d, radarr_upgrade: next } : d))}
                saveLabel="Save movie upgrades schedule"
                canEdit={canEdit}
                savePending={laneSaveByKey.radarr_upgrade.isPending}
                dirty={laneDirty("radarr_upgrade", draft, q.data)}
                saveSuccess={laneSavedOutline === "radarr_upgrade"}
                onPersistLane={(merged) => persistLaneAfterMerge("radarr_upgrade", merged)}
              />
            </div>
          </div>
        ) : (
          <div
            className="mm-dash-grid gap-x-5 gap-y-6"
            data-testid={isTv ? "fetcher-tv-lanes-grid" : "fetcher-movies-lanes-grid"}
          >
            {isTv ? (
              <>
                <SearchLaneBubble
                  variant="limitsOnly"
                  testId="fetcher-tv-lane-missing"
                  sectionTitle="Missing TV shows"
                  sectionIntro="Set up searches for missing TV shows."
                  idPrefix="fetcher-tv-missing"
                  lane={draft.sonarr_missing}
                  serverLane={q.data.sonarr_missing}
                  onLaneChange={(next) => setDraft((d) => (d ? { ...d, sonarr_missing: next } : d))}
                  saveLabel="Save missing TV show searches"
                  canEdit={canEdit}
                  savePending={laneSaveByKey.sonarr_missing.isPending}
                  dirty={laneDirty("sonarr_missing", draft, q.data)}
                  saveSuccess={laneSavedOutline === "sonarr_missing"}
                  onPersistLane={(merged) => persistLaneAfterMerge("sonarr_missing", merged)}
                />
                <SearchLaneBubble
                  variant="limitsOnly"
                  testId="fetcher-tv-lane-upgrade"
                  sectionTitle="TV upgrades"
                  sectionIntro="Set up searches for better quality TV episodes."
                  idPrefix="fetcher-tv-upgrade"
                  lane={draft.sonarr_upgrade}
                  serverLane={q.data.sonarr_upgrade}
                  onLaneChange={(next) => setDraft((d) => (d ? { ...d, sonarr_upgrade: next } : d))}
                  saveLabel="Save TV upgrades"
                  canEdit={canEdit}
                  savePending={laneSaveByKey.sonarr_upgrade.isPending}
                  dirty={laneDirty("sonarr_upgrade", draft, q.data)}
                  saveSuccess={laneSavedOutline === "sonarr_upgrade"}
                  onPersistLane={(merged) => persistLaneAfterMerge("sonarr_upgrade", merged)}
                />
              </>
            ) : (
              <>
                <SearchLaneBubble
                  variant="limitsOnly"
                  testId="fetcher-movies-lane-missing"
                  sectionTitle="Missing movies"
                  sectionIntro="Set up searches for missing movies."
                  idPrefix="fetcher-movies-missing"
                  lane={draft.radarr_missing}
                  serverLane={q.data.radarr_missing}
                  onLaneChange={(next) => setDraft((d) => (d ? { ...d, radarr_missing: next } : d))}
                  saveLabel="Save missing movie searches"
                  canEdit={canEdit}
                  savePending={laneSaveByKey.radarr_missing.isPending}
                  dirty={laneDirty("radarr_missing", draft, q.data)}
                  saveSuccess={laneSavedOutline === "radarr_missing"}
                  onPersistLane={(merged) => persistLaneAfterMerge("radarr_missing", merged)}
                />
                <SearchLaneBubble
                  variant="limitsOnly"
                  testId="fetcher-movies-lane-upgrade"
                  sectionTitle="Movie upgrades"
                  sectionIntro="Set up searches for better quality movies."
                  idPrefix="fetcher-movies-upgrade"
                  lane={draft.radarr_upgrade}
                  serverLane={q.data.radarr_upgrade}
                  onLaneChange={(next) => setDraft((d) => (d ? { ...d, radarr_upgrade: next } : d))}
                  saveLabel="Save movie upgrades"
                  canEdit={canEdit}
                  savePending={laneSaveByKey.radarr_upgrade.isPending}
                  dirty={laneDirty("radarr_upgrade", draft, q.data)}
                  saveSuccess={laneSavedOutline === "radarr_upgrade"}
                  onPersistLane={(merged) => persistLaneAfterMerge("radarr_upgrade", merged)}
                />
              </>
            )}
          </div>
        )}

        {!canEdit ? (
          <p className="mt-5 text-sm text-[var(--mm-text3)]">Viewers can read these settings but cannot save.</p>
        ) : null}

        {saveMessage ? (
          <p className="mt-3 text-sm text-[var(--mm-text2)]" role="status">
            {saveMessage}
          </p>
        ) : null}
      </>
    ) : null;

  return (
    <section
      className="mm-fetcher-module-surface mb-6"
      aria-labelledby={`mm-fetcher-arr-tab-${activeTab}-heading`}
      data-testid="fetcher-arr-operator-settings"
    >
      <header className={FETCHER_TAB_PANEL_INTRO_CLASS}>
        {isSchedules ? (
          <h2 id="mm-fetcher-arr-tab-schedules-heading" className={FETCHER_TAB_PANEL_TITLE_CLASS}>
            {FETCHER_SECTION_SCHEDULES_HEADING}
          </h2>
        ) : isTv ? (
          <h2 id="mm-fetcher-arr-tab-sonarr-heading" className={FETCHER_TAB_PANEL_TITLE_CLASS}>
            {FETCHER_SECTION_SONARR_HEADING}
          </h2>
        ) : (
          <h2 id="mm-fetcher-arr-tab-radarr-heading" className={FETCHER_TAB_PANEL_TITLE_CLASS}>
            {FETCHER_SECTION_RADARR_HEADING}
          </h2>
        )}
        <p className={FETCHER_TAB_PANEL_BLURB_CLASS}>
          {isSchedules ? (
            <>
              Turn searches on or off, set how often they run, and limit runs to certain days and times. Per-run limits
              stay on the <strong>{FETCHER_TAB_SONARR_LABEL}</strong> and <strong>{FETCHER_TAB_RADARR_LABEL}</strong> tabs.
              Follow runs on{" "}
              <Link to="/app/activity" className="text-[var(--mm-accent)] underline-offset-2 hover:underline">
                Activity
              </Link>
              .
            </>
          ) : isTv ? (
            <>
              Configure Fetcher search behavior for <strong>{FETCHER_TAB_SONARR_LABEL}</strong>, including missing and
              upgrade lanes. Follow runs on{" "}
              <Link to="/app/activity" className="text-[var(--mm-accent)] underline-offset-2 hover:underline">
                Activity
              </Link>
              .
            </>
          ) : (
            <>
              Configure Fetcher search behavior for <strong>{FETCHER_TAB_RADARR_LABEL}</strong>, including missing and
              upgrade lanes. Follow runs on{" "}
              <Link to="/app/activity" className="text-[var(--mm-accent)] underline-offset-2 hover:underline">
                Activity
              </Link>
              .
            </>
          )}
        </p>
      </header>

      {lanesBody}
    </section>
  );
}
