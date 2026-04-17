import { useOutletContext } from "react-router-dom";
import type { PrunerServerInstance } from "../../lib/pruner/api";

type Ctx = { instanceId: number; instance: PrunerServerInstance | undefined };

export function PrunerInstanceOverviewTab() {
  const { instance } = useOutletContext<Ctx>();

  if (!instance) {
    return null;
  }

  return (
    <section
      className="max-w-3xl space-y-3 rounded-md border border-[var(--mm-border)] bg-[var(--mm-card-bg)] px-4 py-4"
      aria-labelledby="pruner-overview-heading"
    >
      <h2 id="pruner-overview-heading" className="text-base font-semibold text-[var(--mm-text)]">
        Scopes (summary)
      </h2>
      <p className="text-sm text-[var(--mm-text2)]">
        Latest preview numbers below are denormalized for quick reads (Jellyfin/Emby preview snapshots). Full candidate
        JSON for those providers lives in <code className="text-[0.85em]">pruner_preview_runs</code> (see TV / Movies
        tabs). Plex uses the live path on scope tabs when enabled — it does not consume preview snapshots.
      </p>
      <ul className="space-y-2 text-sm">
        {instance.scopes.map((s) => (
          <li key={s.media_scope} className="rounded border border-[var(--mm-border)] px-3 py-2">
            <div className="font-medium capitalize text-[var(--mm-text)]">{s.media_scope}</div>
            <div className="text-xs text-[var(--mm-text2)]">
              Missing primary art rule: {s.missing_primary_media_reported_enabled ? "on" : "off"} · stale never-played
              rule: {s.never_played_stale_reported_enabled ? "on" : "off"} (min age {s.never_played_min_age_days} days) ·
              per-scope item cap {s.preview_max_items}{" "}
              <span className="text-[var(--mm-text3)]">
                (Jellyfin/Emby: preview list max. Plex: same number caps live removals together with the env absolute
                ceiling.)
              </span>
            </div>
            <div className="mt-1 text-xs text-[var(--mm-text2)]">
              Last preview:{" "}
              {s.last_preview_outcome
                ? `${s.last_preview_outcome} (${s.last_preview_candidate_count ?? 0} candidates)`
                : "none yet"}
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
