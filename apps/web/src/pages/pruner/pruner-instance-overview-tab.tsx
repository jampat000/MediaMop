import { Link, useOutletContext } from "react-router-dom";
import type {
  PrunerScopeSummary,
  PrunerServerInstance,
} from "../../lib/pruner/api";
import {
  formatPrunerDateTime,
  plexUnsupportedRuleFamilies,
} from "./pruner-ui-utils";

type Ctx = { instanceId: number; instance: PrunerServerInstance | undefined };

function scopeHeading(media: string): string {
  return media === "tv" ? "TV shows" : "Movies";
}

function activeRuleLines(
  scope: PrunerScopeSummary,
  provider: string,
): string[] {
  const lines: string[] = [];
  if (scope.missing_primary_media_reported_enabled) {
    lines.push(
      "Delete items missing a main poster or episode image when the server supports it.",
    );
  }
  if (scope.never_played_stale_reported_enabled) {
    lines.push(
      `Delete never-started titles older than ${scope.never_played_min_age_days} days.`,
    );
  }
  if (scope.media_scope === "tv" && scope.watched_tv_reported_enabled) {
    lines.push("Delete watched TV episodes.");
  }
  if (scope.media_scope === "movies") {
    if (scope.watched_movies_reported_enabled)
      lines.push("Delete watched movies.");
    if (scope.watched_movie_low_rating_reported_enabled) {
      lines.push(
        provider === "plex"
          ? `Delete watched Plex movies rated below ${scope.watched_movie_low_rating_max_plex_audience_rating}.`
          : `Delete watched movies rated below ${scope.watched_movie_low_rating_max_jellyfin_emby_community_rating}.`,
      );
    }
    if (scope.unwatched_movie_stale_reported_enabled) {
      lines.push(
        `Delete unwatched movies older than ${scope.unwatched_movie_stale_min_age_days} days.`,
      );
    }
  }
  return lines.length > 0
    ? lines
    : ["No cleanup rules are turned on for this library yet."];
}

function scheduleLine(scope: PrunerScopeSummary): string {
  if (!scope.scheduled_preview_enabled) return "Automatic previews are off.";
  const every = Math.max(
    1,
    Math.floor(scope.scheduled_preview_interval_seconds / 60),
  );
  const window = scope.scheduled_preview_hours_limited
    ? `Window: ${scope.scheduled_preview_days || "Every day"} ${scope.scheduled_preview_start || "00:00"}-${scope.scheduled_preview_end || "23:59"}`
    : "No hour limit";
  return `Automatic previews run every ${every} minutes. ${window}`;
}

function connectionStatus(instance: PrunerServerInstance): {
  title: string;
  detail: string;
} {
  if (instance.last_connection_test_ok === true) {
    return {
      title: "Connection tested",
      detail:
        instance.last_connection_test_detail ||
        "The most recent media server connection test succeeded.",
    };
  }
  if (instance.last_connection_test_ok === false) {
    return {
      title: "Connection needs review",
      detail:
        instance.last_connection_test_detail ||
        "The most recent media server connection test failed.",
    };
  }
  return {
    title: "Credentials saved",
    detail: "No connection test has been recorded yet.",
  };
}

function ScopeWorkspaceCard({
  instanceId,
  provider,
  scope,
}: {
  instanceId: number;
  provider: string;
  scope: PrunerScopeSummary;
}) {
  const toTab = scope.media_scope === "tv" ? "tv" : "movies";
  const unsupported =
    provider === "plex"
      ? plexUnsupportedRuleFamilies(scope.media_scope as "tv" | "movies")
      : [];

  return (
    <div
      className="flex h-full flex-col gap-4 rounded-md border border-[var(--mm-border)] bg-[var(--mm-card-bg)] p-4 text-sm"
      data-testid={`pruner-overview-scope-${scope.media_scope}`}
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h3 className="text-sm font-semibold text-[var(--mm-text1)]">
            {scopeHeading(scope.media_scope)}
          </h3>
          <p className="mt-1 text-xs text-[var(--mm-text3)]">
            {scheduleLine(scope)}
          </p>
        </div>
        <Link
          to={`/app/pruner/instances/${instanceId}/${toTab}`}
          className="text-xs font-semibold text-[var(--mm-accent)] underline-offset-2 hover:underline"
        >
          Open tab
        </Link>
      </div>

      <div>
        <p className="text-xs font-medium uppercase tracking-wide text-[var(--mm-text3)]">
          Rules turned on
        </p>
        <ul className="mt-1 list-inside list-disc space-y-1 text-[var(--mm-text2)]">
          {activeRuleLines(scope, provider).map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      </div>

      <div className="rounded-md border border-[var(--mm-border)] bg-black/10 px-3 py-3">
        <p className="text-xs font-medium uppercase tracking-wide text-[var(--mm-text3)]">
          Last library scan
        </p>
        <p className="mt-1 text-sm text-[var(--mm-text2)]">
          <span className="font-medium text-[var(--mm-text1)]">
            {formatPrunerDateTime(scope.last_preview_at)}
          </span>
        </p>
        <p className="mt-1 text-xs text-[var(--mm-text2)]">
          Result:{" "}
          <span className="font-medium text-[var(--mm-text1)]">
            {scope.last_preview_outcome ?? "No scan yet"}
          </span>
          {scope.last_preview_candidate_count != null ? (
            <>
              {" "}
              · Candidates:{" "}
              <span className="font-medium text-[var(--mm-text1)]">
                {scope.last_preview_candidate_count}
              </span>
            </>
          ) : null}
        </p>
        {scope.last_preview_error ? (
          <p className="mt-2 text-xs text-red-200" role="status">
            {scope.last_preview_error}
          </p>
        ) : null}
      </div>

      {unsupported.length ? (
        <div className="rounded-md border border-amber-900/40 bg-amber-950/20 px-3 py-3 text-xs text-amber-100/95">
          <p className="font-semibold text-amber-50">
            Not available for this Plex library
          </p>
          <ul className="mt-2 list-inside list-disc space-y-1">
            {unsupported.map((u) => (
              <li key={u}>{u}</li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

export function PrunerInstanceOverviewTab(props: { contextOverride?: Ctx }) {
  const outletCtx = useOutletContext<Ctx>();
  const { instanceId, instance } = props.contextOverride ?? outletCtx;

  if (!instance) {
    return null;
  }

  const tv = instance.scopes.find((s) => s.media_scope === "tv");
  const movies = instance.scopes.find((s) => s.media_scope === "movies");
  const connection = connectionStatus(instance);

  return (
    <div
      className="mm-bubble-stack w-full min-w-0"
      data-testid="pruner-instance-overview"
    >
      <header className="mm-page__intro !mb-0 border-0 p-0 shadow-none">
        <p className="mm-page__eyebrow">This server</p>
        <h2 className="mm-page__title text-xl sm:text-2xl">Overview</h2>
        <p className="mm-page__subtitle max-w-3xl">
          One{" "}
          <strong className="text-[var(--mm-text)]">{instance.provider}</strong>{" "}
          library connection. TV shows and movies are separate tabs under this
          server. Each scan saves a list you can review. Cleanup runs only use
          the saved preview you confirm.
        </p>
      </header>

      <section
        className="mm-card mm-dash-card mm-module-surface border border-[var(--mm-border)] bg-[var(--mm-card-bg)] p-4 sm:p-5"
        aria-labelledby="pruner-overview-status-heading"
      >
        <h3
          id="pruner-overview-status-heading"
          className="text-sm font-semibold text-[var(--mm-text1)]"
        >
          Server status
        </h3>
        <div className="mt-3 grid gap-4 lg:grid-cols-2">
          <div className="rounded-md border border-[var(--mm-border)] bg-black/10 px-4 py-4">
            <p className="text-xs font-medium uppercase tracking-wide text-[var(--mm-text3)]">
              Connection
            </p>
            <p className="mt-1 text-sm font-semibold text-[var(--mm-text1)]">
              {connection.title}
            </p>
            <p className="mt-2 text-sm text-[var(--mm-text2)]">
              {connection.detail}
            </p>
            <p className="mt-2 text-xs text-[var(--mm-text3)]">
              Last checked:{" "}
              <span className="font-medium text-[var(--mm-text2)]">
                {formatPrunerDateTime(instance.last_connection_test_at)}
              </span>
            </p>
          </div>
          <div className="rounded-md border border-[var(--mm-border)] bg-black/10 px-4 py-4">
            <p className="text-xs font-medium uppercase tracking-wide text-[var(--mm-text3)]">
              Next step
            </p>
            <p className="mt-1 text-sm text-[var(--mm-text2)]">
              Open the TV or Movies tab to review filters, schedules, and the
              most recent preview before running cleanup.
            </p>
          </div>
        </div>
      </section>

      <section
        className="mm-card mm-dash-card mm-module-surface border border-[var(--mm-border)] bg-[var(--mm-card-bg)] p-4 sm:p-5"
        aria-labelledby="pruner-overview-at-a-glance"
      >
        <h3
          id="pruner-overview-at-a-glance"
          className="text-sm font-semibold text-[var(--mm-text1)]"
        >
          At a glance
        </h3>
        <div className="mt-3 grid gap-4 md:grid-cols-2">
          {tv ? (
            <ScopeWorkspaceCard
              instanceId={instanceId}
              provider={instance.provider}
              scope={tv}
            />
          ) : null}
          {movies ? (
            <ScopeWorkspaceCard
              instanceId={instanceId}
              provider={instance.provider}
              scope={movies}
            />
          ) : null}
        </div>
      </section>

      <section
        className="rounded-md border border-[var(--mm-border)] bg-[var(--mm-surface2)]/40 px-4 py-3 text-sm text-[var(--mm-text2)]"
        aria-labelledby="pruner-overview-apply-note"
      >
        <h3
          id="pruner-overview-apply-note"
          className="text-sm font-semibold text-[var(--mm-text)]"
        >
          After cleanup runs
        </h3>
        <p className="mt-1 text-xs sm:text-sm">
          Removed, skipped, and failed counts for each cleanup run are written
          to <strong className="text-[var(--mm-text)]">Activity</strong> when
          the job finishes.
        </p>
        <p className="mt-2">
          <Link
            className="font-semibold text-[var(--mm-accent)] underline-offset-2 hover:underline"
            to="/app/activity"
          >
            Open Activity
          </Link>
        </p>
      </section>
    </div>
  );
}
