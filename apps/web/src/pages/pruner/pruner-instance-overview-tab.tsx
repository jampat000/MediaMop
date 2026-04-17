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
        Latest preview numbers below are denormalized for quick reads. Full candidate JSON lives in{" "}
        <code className="text-[0.85em]">pruner_preview_runs</code> (see TV / Movies tabs). Jellyfin, Emby, and Plex
        (missing-primary rule) all use stored preview snapshots for apply-from-preview.
      </p>
      <ul className="space-y-2 text-sm">
        {instance.scopes.map((s) => (
          <li key={s.media_scope} className="rounded border border-[var(--mm-border)] px-3 py-2">
            <div className="font-medium capitalize text-[var(--mm-text)]">{s.media_scope}</div>
            <div className="text-xs text-[var(--mm-text2)]">
              Missing primary art rule: {s.missing_primary_media_reported_enabled ? "on" : "off"} · stale never-played
              rule: {s.never_played_stale_reported_enabled ? "on" : "off"} (min age {s.never_played_min_age_days} days)
              {s.media_scope === "tv" ? (
                <>
                  {" "}
                  · watched TV (episodes) rule: {s.watched_tv_reported_enabled ? "on" : "off"}
                </>
              ) : null}
              {s.media_scope === "movies" ? (
                <>
                  {" "}
                  · watched movies rule: {s.watched_movies_reported_enabled ? "on" : "off"}
                  {" "}
                  · watched low-rating movies: {s.watched_movie_low_rating_reported_enabled ? "on" : "off"} (≤{" "}
                  {s.watched_movie_low_rating_max_community_rating} CommunityRating)
                  {" "}
                  · unwatched stale movies: {s.unwatched_movie_stale_reported_enabled ? "on" : "off"} (≥{" "}
                  {s.unwatched_movie_stale_min_age_days} days)
                </>
              ) : null}{" "}
              · per-scope item cap {s.preview_max_items}{" "}
              <span className="text-[var(--mm-text3)]">
                (Jellyfin/Emby/Plex: preview candidate cap per scope. Legacy Plex-only env ceilings are deprecated.)
              </span>
            </div>
            <div className="mt-1 text-xs text-[var(--mm-text2)]">
              Preview-only narrowing: year{" "}
              {s.preview_year_min != null || s.preview_year_max != null ? (
                <>
                  {s.preview_year_min ?? "—"}–{s.preview_year_max ?? "—"} (inclusive; missing years never match when a
                  bound is set)
                </>
              ) : (
                "none set"
              )}
              {" · "}
              studio include tokens: {(s.preview_include_studios ?? []).length}
              {" · "}
              collection include tokens: {(s.preview_include_collections ?? []).length}
              {instance.provider !== "plex" ? (
                <span className="text-[var(--mm-text3)]">
                  {" "}
                  (collection tokens apply on Plex missing-primary previews only; stored here for operator reference)
                </span>
              ) : null}
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
