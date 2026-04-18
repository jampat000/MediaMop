import type { ReactNode } from "react";
import type { FetcherArrOperatorSettingsOut, FetcherArrSearchLane } from "../../lib/fetcher/arr-operator-settings/types";
import { FETCHER_TAB_RADARR_LABEL, FETCHER_TAB_SONARR_LABEL } from "./fetcher-display-names";

function lanesFieldEqual(
  missing: FetcherArrSearchLane,
  upgrade: FetcherArrSearchLane,
  pick: (lane: FetcherArrSearchLane) => unknown,
): boolean {
  return pick(missing) === pick(upgrade);
}

function laneScheduleSignature(lane: FetcherArrSearchLane): string {
  return `${lane.schedule_enabled}|${lane.schedule_days}|${lane.schedule_start}|${lane.schedule_end}`;
}

function formatOnOff(on: boolean): string {
  return on ? "On" : "Off";
}

function formatIntervalPhrase(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 1) {
    return String(seconds);
  }
  if (seconds % 3600 === 0) {
    const h = seconds / 3600;
    return h === 1 ? "Every hour" : `Every ${h} hours`;
  }
  if (seconds % 60 === 0) {
    const m = seconds / 60;
    return m === 1 ? "Every minute" : `Every ${m} minutes`;
  }
  const approxMin = Math.max(1, Math.round(seconds / 60));
  return approxMin === 1 ? "About every minute" : `About every ${approxMin} minutes`;
}

function toDayMinutes(hhmm: string): number | null {
  const p = hhmm.trim().split(":");
  if (p.length !== 2) {
    return null;
  }
  const h = Number(p[0]);
  const m = Number(p[1]);
  if (!Number.isFinite(h) || !Number.isFinite(m)) {
    return null;
  }
  return h * 60 + m;
}

function formatSearchSchedule(lane: FetcherArrSearchLane): string {
  if (!lane.schedule_enabled) {
    return "All day";
  }
  const s = lane.schedule_start.trim();
  const e = lane.schedule_end.trim();
  if (s === "00:00" && e === "23:59") {
    return "All day";
  }
  const sm = toDayMinutes(s);
  const em = toDayMinutes(e);
  if (sm === null || em === null) {
    return "Custom hours";
  }
  if (sm > em) {
    return "Overnight";
  }
  const days = lane.schedule_days.trim();
  if (days) {
    return `${days} · ${s}–${e}`;
  }
  return `${s}–${e}`;
}

function formatRetryCooldown(minutes: number): string {
  if (!Number.isFinite(minutes) || minutes < 1) {
    return String(minutes);
  }
  if (minutes % (60 * 24) === 0) {
    const d = minutes / (60 * 24);
    return d === 1 ? "1 day" : `${d} days`;
  }
  if (minutes % 60 === 0) {
    const h = minutes / 60;
    return h === 1 ? "1 hour" : `${h} hours`;
  }
  return `${minutes} minutes`;
}

function splitRowBody(
  missingLabel: string,
  upgradeLabel: string,
  missingText: string,
  upgradeText: string,
  same: boolean,
): ReactNode {
  if (same) {
    return missingText;
  }
  return (
    <div className="space-y-1.5">
      <div className="leading-snug">
        <span className="text-xs font-medium text-[var(--mm-text3)]">{missingLabel}: </span>
        <span className="font-semibold text-[var(--mm-text1)]">{missingText}</span>
      </div>
      <div className="leading-snug">
        <span className="text-xs font-medium text-[var(--mm-text3)]">{upgradeLabel}: </span>
        <span className="font-semibold text-[var(--mm-text1)]">{upgradeText}</span>
      </div>
    </div>
  );
}

function SearchSetupAxisCard({
  title,
  missingLabel,
  upgradeLabel,
  missing,
  upgrade,
}: {
  title: string;
  missingLabel: string;
  upgradeLabel: string;
  missing: FetcherArrSearchLane;
  upgrade: FetcherArrSearchLane;
}) {
  const row = (label: string, value: string | number | ReactNode) => (
    <div className="space-y-0.5">
      <dt className="text-xs text-[var(--mm-text3)]">{label}</dt>
      <dd className="text-sm font-semibold leading-snug text-[var(--mm-text1)]">{value}</dd>
    </div>
  );
  const sameInterval = lanesFieldEqual(missing, upgrade, (l) => l.schedule_interval_seconds);
  const sameSchedule = lanesFieldEqual(missing, upgrade, (l) => laneScheduleSignature(l));
  const sameLimit = lanesFieldEqual(missing, upgrade, (l) => l.max_items_per_run);
  const sameRetry = lanesFieldEqual(missing, upgrade, (l) => l.retry_delay_minutes);
  return (
    <div className="space-y-2.5 rounded-md border border-[var(--mm-border)] bg-[var(--mm-surface2)]/40 p-5">
      <h3 className="text-sm font-semibold text-[var(--mm-text1)]">{title}</h3>
      <dl className="space-y-1.5">
        {row(missingLabel, formatOnOff(missing.enabled))}
        {row(upgradeLabel, formatOnOff(upgrade.enabled))}
        {row(
          "Run interval",
          splitRowBody(
            missingLabel,
            upgradeLabel,
            formatIntervalPhrase(missing.schedule_interval_seconds),
            formatIntervalPhrase(upgrade.schedule_interval_seconds),
            sameInterval,
          ),
        )}
        {row(
          "Time window",
          splitRowBody(
            missingLabel,
            upgradeLabel,
            formatSearchSchedule(missing),
            formatSearchSchedule(upgrade),
            sameSchedule,
          ),
        )}
        {row(
          "Items per run",
          splitRowBody(
            missingLabel,
            upgradeLabel,
            String(missing.max_items_per_run),
            String(upgrade.max_items_per_run),
            sameLimit,
          ),
        )}
        {row(
          "Retry cooldown",
          splitRowBody(
            missingLabel,
            upgradeLabel,
            formatRetryCooldown(missing.retry_delay_minutes),
            formatRetryCooldown(upgrade.retry_delay_minutes),
            sameRetry,
          ),
        )}
      </dl>
    </div>
  );
}

/** Current search setup — saved *arr* search preferences only (Overview and anywhere else read-only). */
export function FetcherCurrentSearchSetupSection({ arr }: { arr: FetcherArrOperatorSettingsOut }) {
  return (
    <section
      className="mm-card mm-dash-card mm-fetcher-module-surface"
      aria-labelledby="fetcher-current-search-setup-heading"
      data-testid="fetcher-automation-summary"
      data-overview-order="3"
    >
      <h2 id="fetcher-current-search-setup-heading" className="mm-card__title text-lg">
        Current search setup
      </h2>
      <p className="mm-card__body mm-card__body--tight text-sm text-[var(--mm-text3)]">
        This shows your current TV and movie search settings.
      </p>
      <div className="mt-5 grid gap-3.5 md:grid-cols-2 md:gap-x-5 md:gap-y-3.5">
        <SearchSetupAxisCard
          title={FETCHER_TAB_SONARR_LABEL}
          missingLabel="Missing searches"
          upgradeLabel="Upgrades"
          missing={arr.sonarr_missing}
          upgrade={arr.sonarr_upgrade}
        />
        <SearchSetupAxisCard
          title={FETCHER_TAB_RADARR_LABEL}
          missingLabel="Missing searches"
          upgradeLabel="Upgrades"
          missing={arr.radarr_missing}
          upgrade={arr.radarr_upgrade}
        />
      </div>
    </section>
  );
}
