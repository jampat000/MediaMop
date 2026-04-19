import { useEffect, useState } from "react";
import { fetchCsrfToken } from "../../lib/api/auth-api";
import { MmOnOffSwitch } from "../../components/ui/mm-on-off-switch";
import {
  MM_SCHEDULE_DAYS_HELPER,
  MM_SCHEDULE_TIME_WINDOW_HEADING,
  MM_SCHEDULE_TIME_WINDOW_HELPER,
  MmScheduleDayChips,
  MmScheduleTimeFields,
} from "../../components/ui/mm-schedule-window-controls";
import { mmActionButtonClass } from "../../lib/ui/mm-control-roles";
import { usePutSubberSettingsMutation, useSubberSettingsQuery } from "../../lib/subber/subber-queries";

function fmtTs(iso: string | null | undefined): string {
  if (!iso) return "Never run";
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

type CardProps = {
  title: string;
  helper: string;
  canOperate: boolean;
  enabled: boolean;
  setEnabled: (v: boolean) => void;
  intervalMinutes: number;
  setIntervalMinutes: (v: number) => void;
  hoursLimited: boolean;
  setHoursLimited: (v: boolean) => void;
  daysCsv: string;
  setDaysCsv: (v: string) => void;
  start: string;
  setStart: (v: string) => void;
  end: string;
  setEnd: (v: string) => void;
  lastRun: string | null | undefined;
  lastRunLabel?: string;
  saveLabel: string;
  idPrefix: string;
  onSave: () => Promise<void>;
  busy: boolean;
  timedSwitchLabel?: string;
  intervalHelper?: string;
};

function ScheduleCard({
  title,
  helper,
  canOperate,
  enabled,
  setEnabled,
  intervalMinutes,
  setIntervalMinutes,
  hoursLimited,
  setHoursLimited,
  daysCsv,
  setDaysCsv,
  start,
  setStart,
  end,
  setEnd,
  lastRun,
  lastRunLabel = "Last automatic scan",
  saveLabel,
  idPrefix,
  onSave,
  busy,
  timedSwitchLabel = "Enable timed scans",
  intervalHelper = "How often Subber checks this library for missing subtitles.",
}: CardProps) {
  const dis = !canOperate || busy;
  return (
    <section className="rounded-md border border-[var(--mm-border)] bg-[var(--mm-card-bg)] p-5">
      <h2 className="text-base font-semibold text-[var(--mm-text)]">{title}</h2>
      <p className="mt-1 text-sm text-[var(--mm-text2)]">{helper}</p>
      <div className="mt-4 space-y-4">
        <MmOnOffSwitch id={`${idPrefix}-en`} label={timedSwitchLabel} enabled={enabled} disabled={dis} onChange={setEnabled} />
        <label className="block text-sm text-[var(--mm-text2)]">
          Run interval (minutes)
          <p className="mt-1 text-xs text-[var(--mm-text2)]">{intervalHelper}</p>
          <input
            type="number"
            min={1}
            max={10080}
            className="mm-input mt-1 w-full max-w-xs"
            value={intervalMinutes}
            disabled={dis}
            onChange={(e) => setIntervalMinutes(Math.max(1, Math.min(10080, Number(e.target.value) || 1)))}
          />
        </label>
        <div className="space-y-3">
          <div>
            <span className="text-sm font-medium text-[var(--mm-text)]">{MM_SCHEDULE_TIME_WINDOW_HEADING}</span>
            <p className="mt-1 text-xs text-[var(--mm-text2)]">{MM_SCHEDULE_TIME_WINDOW_HELPER}</p>
          </div>
          <MmOnOffSwitch
            id={`${idPrefix}-hours`}
            label="Limit to these hours"
            enabled={hoursLimited}
            disabled={dis}
            onChange={setHoursLimited}
          />
          <div>
            <span className="text-sm font-medium text-[var(--mm-text)]">Days</span>
            <p className="mt-1 text-xs text-[var(--mm-text2)]">{MM_SCHEDULE_DAYS_HELPER}</p>
            <MmScheduleDayChips scheduleDaysCsv={daysCsv} disabled={dis} onChangeCsv={setDaysCsv} />
          </div>
          <MmScheduleTimeFields idPrefix={idPrefix} start={start} end={end} disabled={dis} onStart={setStart} onEnd={setEnd} />
        </div>
        <p className="text-xs text-[var(--mm-text2)]">
          {lastRunLabel}: <span className="font-medium text-[var(--mm-text)]">{fmtTs(lastRun)}</span>
        </p>
        <button
          type="button"
          className={mmActionButtonClass({ variant: "primary", disabled: dis })}
          disabled={dis}
          onClick={() => void onSave()}
        >
          {saveLabel}
        </button>
      </div>
    </section>
  );
}

export function SubberScheduleTab({ canOperate }: { canOperate: boolean }) {
  const q = useSubberSettingsQuery();
  const put = usePutSubberSettingsMutation();
  const [tvEn, setTvEn] = useState(false);
  const [tvMin, setTvMin] = useState(360);
  const [tvHl, setTvHl] = useState(false);
  const [tvDays, setTvDays] = useState("");
  const [tvStart, setTvStart] = useState("00:00");
  const [tvEnd, setTvEnd] = useState("23:59");
  const [mvEn, setMvEn] = useState(false);
  const [mvMin, setMvMin] = useState(360);
  const [mvHl, setMvHl] = useState(false);
  const [mvDays, setMvDays] = useState("");
  const [mvStart, setMvStart] = useState("00:00");
  const [mvEnd, setMvEnd] = useState("23:59");
  const [upEn, setUpEn] = useState(false);
  const [upSched, setUpSched] = useState(false);
  const [upMin, setUpMin] = useState(10080);
  const [upHl, setUpHl] = useState(false);
  const [upDays, setUpDays] = useState("");
  const [upStart, setUpStart] = useState("00:00");
  const [upEnd, setUpEnd] = useState("23:59");

  useEffect(() => {
    const d = q.data;
    if (!d) return;
    setTvEn(d.tv_schedule_enabled);
    setTvMin(Math.max(1, Math.round(d.tv_schedule_interval_seconds / 60)));
    setTvHl(d.tv_schedule_hours_limited);
    setTvDays(d.tv_schedule_days ?? "");
    setTvStart(d.tv_schedule_start ?? "00:00");
    setTvEnd(d.tv_schedule_end ?? "23:59");
    setMvEn(d.movies_schedule_enabled);
    setMvMin(Math.max(1, Math.round(d.movies_schedule_interval_seconds / 60)));
    setMvHl(d.movies_schedule_hours_limited);
    setMvDays(d.movies_schedule_days ?? "");
    setMvStart(d.movies_schedule_start ?? "00:00");
    setMvEnd(d.movies_schedule_end ?? "23:59");
    setUpEn(Boolean(d.upgrade_enabled));
    setUpSched(Boolean(d.upgrade_schedule_enabled));
    setUpMin(Math.max(1, Math.round((d.upgrade_schedule_interval_seconds ?? 604800) / 60)));
    setUpHl(Boolean(d.upgrade_schedule_hours_limited));
    setUpDays(d.upgrade_schedule_days ?? "");
    setUpStart(d.upgrade_schedule_start ?? "00:00");
    setUpEnd(d.upgrade_schedule_end ?? "23:59");
  }, [q.data]);

  async function saveTv() {
    const csrf_token = await fetchCsrfToken();
    await put.mutateAsync({
      csrf_token,
      tv_schedule_enabled: tvEn,
      tv_schedule_interval_seconds: Math.max(60, Math.min(7 * 24 * 3600, tvMin * 60)),
      tv_schedule_hours_limited: tvHl,
      tv_schedule_days: tvDays,
      tv_schedule_start: tvStart,
      tv_schedule_end: tvEnd,
    });
  }

  async function saveMovies() {
    const csrf_token = await fetchCsrfToken();
    await put.mutateAsync({
      csrf_token,
      movies_schedule_enabled: mvEn,
      movies_schedule_interval_seconds: Math.max(60, Math.min(7 * 24 * 3600, mvMin * 60)),
      movies_schedule_hours_limited: mvHl,
      movies_schedule_days: mvDays,
      movies_schedule_start: mvStart,
      movies_schedule_end: mvEnd,
    });
  }

  async function saveUpgrade() {
    const csrf_token = await fetchCsrfToken();
    await put.mutateAsync({
      csrf_token,
      upgrade_enabled: upEn,
      upgrade_schedule_enabled: upSched,
      upgrade_schedule_interval_seconds: Math.max(60, Math.min(365 * 24 * 3600, upMin * 60)),
      upgrade_schedule_hours_limited: upHl,
      upgrade_schedule_days: upDays,
      upgrade_schedule_start: upStart,
      upgrade_schedule_end: upEnd,
    });
  }

  if (q.isLoading) return <p className="text-sm text-[var(--mm-text2)]">Loading schedule…</p>;
  if (q.isError) return <p className="text-sm text-red-600">{(q.error as Error).message}</p>;

  return (
    <div className="grid gap-4 lg:grid-cols-3" data-testid="subber-schedule-tab">
      <ScheduleCard
        title="TV automatic subtitle scan"
        helper="Subber also searches immediately when Sonarr imports a file, regardless of this schedule."
        canOperate={canOperate}
        enabled={tvEn}
        setEnabled={setTvEn}
        intervalMinutes={tvMin}
        setIntervalMinutes={setTvMin}
        hoursLimited={tvHl}
        setHoursLimited={setTvHl}
        daysCsv={tvDays}
        setDaysCsv={setTvDays}
        start={tvStart}
        setStart={setTvStart}
        end={tvEnd}
        setEnd={setTvEnd}
        lastRun={q.data?.tv_last_scheduled_scan_enqueued_at}
        saveLabel="Save TV schedule"
        idPrefix="subber-tv-sched"
        onSave={saveTv}
        busy={put.isPending}
      />
      <ScheduleCard
        title="Movies automatic subtitle scan"
        helper="Subber also searches immediately when Radarr imports a file, regardless of this schedule."
        canOperate={canOperate}
        enabled={mvEn}
        setEnabled={setMvEn}
        intervalMinutes={mvMin}
        setIntervalMinutes={setMvMin}
        hoursLimited={mvHl}
        setHoursLimited={setMvHl}
        daysCsv={mvDays}
        setDaysCsv={setMvDays}
        start={mvStart}
        setStart={setMvStart}
        end={mvEnd}
        setEnd={setMvEnd}
        lastRun={q.data?.movies_last_scheduled_scan_enqueued_at}
        saveLabel="Save Movies schedule"
        idPrefix="subber-movies-sched"
        onSave={saveMovies}
        busy={put.isPending}
      />
      <section className="rounded-md border border-[var(--mm-border)] bg-[var(--mm-card-bg)] p-5">
        <h2 className="text-base font-semibold text-[var(--mm-text)]">Subtitle upgrade</h2>
        <p className="mt-1 text-sm text-[var(--mm-text2)]">
          Subber periodically re-searches for better subtitle files for movies and episodes that already have subtitles.
        </p>
        <div className="mt-4 space-y-4">
          <MmOnOffSwitch
            id="subber-up-en"
            label="Enable subtitle upgrades"
            enabled={upEn}
            disabled={!canOperate || put.isPending}
            onChange={setUpEn}
          />
          <p className="text-xs text-[var(--mm-text2)]">
            {upEn ? "Subtitle upgrade is on." : "Subtitle upgrade is off. Subtitles already downloaded will not be re-searched."}
          </p>
          <MmOnOffSwitch
            id="subber-up-sched-en"
            label="Enable timed upgrade scans"
            enabled={upSched}
            disabled={!canOperate || put.isPending}
            onChange={setUpSched}
          />
          <label className="block text-sm text-[var(--mm-text2)]">
            Run interval (minutes)
            <p className="mt-1 text-xs text-[var(--mm-text2)]">
              How often Subber checks for subtitle upgrades. Default is 10080 minutes (1 week).
            </p>
            <input
              type="number"
              min={1}
              max={525600}
              className="mm-input mt-1 w-full max-w-xs"
              value={upMin}
              disabled={!canOperate || put.isPending}
              onChange={(e) => setUpMin(Math.max(1, Math.min(525600, Number(e.target.value) || 1)))}
            />
          </label>
          <div className="space-y-3">
            <div>
              <span className="text-sm font-medium text-[var(--mm-text)]">{MM_SCHEDULE_TIME_WINDOW_HEADING}</span>
              <p className="mt-1 text-xs text-[var(--mm-text2)]">{MM_SCHEDULE_TIME_WINDOW_HELPER}</p>
            </div>
            <MmOnOffSwitch
              id="subber-upgrade-sched-hours"
              label="Limit to these hours"
              enabled={upHl}
              disabled={!canOperate || put.isPending}
              onChange={setUpHl}
            />
            <div>
              <span className="text-sm font-medium text-[var(--mm-text)]">Days</span>
              <p className="mt-1 text-xs text-[var(--mm-text2)]">{MM_SCHEDULE_DAYS_HELPER}</p>
              <MmScheduleDayChips scheduleDaysCsv={upDays} disabled={!canOperate || put.isPending} onChangeCsv={setUpDays} />
            </div>
            <MmScheduleTimeFields
              idPrefix="subber-upgrade-sched"
              start={upStart}
              end={upEnd}
              disabled={!canOperate || put.isPending}
              onStart={setUpStart}
              onEnd={setUpEnd}
            />
          </div>
          <p className="text-xs text-[var(--mm-text2)]">
            Last upgrade scan: <span className="font-medium text-[var(--mm-text)]">{fmtTs(q.data?.upgrade_last_scheduled_at)}</span>
          </p>
          <button
            type="button"
            className={mmActionButtonClass({ variant: "primary", disabled: !canOperate || put.isPending })}
            disabled={!canOperate || put.isPending}
            onClick={() => void saveUpgrade()}
          >
            Save upgrade schedule
          </button>
        </div>
      </section>
    </div>
  );
}
