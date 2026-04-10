import { Link } from "react-router-dom";

/**
 * Refiner product surface: movies/TV refinement (agnostic tooling).
 * Radarr/Sonarr download-queue failed-import review/removal is owned by Fetcher — see `/app/fetcher`.
 */
export function RefinerPage() {
  return (
    <div className="mm-page" data-testid="refiner-scope-page">
      <header className="mm-page__intro">
        <p className="mm-page__eyebrow">MediaMop</p>
        <h1 className="mm-page__title">Refiner</h1>
        <p className="mm-page__subtitle">
          Refiner is where MediaMop focuses on refining movies and TV — structural and editorial cleanup of media
          metadata and files. It stays app-agnostic: not defined by a specific downloader stack.
        </p>
        <p className="mm-page__lead">
          <strong>Radarr</strong> and <strong>Sonarr</strong> <strong>download-queue</strong> failed-import review and
          removal (the queue-driven workflow you can inspect in the UI) is a{" "}
          <Link to="/app/fetcher" className="text-[var(--mm-accent)] underline-offset-2 hover:underline">
            Fetcher
          </Link>{" "}
          concern — not Refiner’s product identity.
        </p>
        <p className="mt-3 text-sm text-[var(--mm-text3)]">
          Future Refiner-native work can include stale-file cleanup on disk after importing is finished. That is
          different from walking *arr download queues; this page does not host the queue workflow.
        </p>
      </header>
    </div>
  );
}
