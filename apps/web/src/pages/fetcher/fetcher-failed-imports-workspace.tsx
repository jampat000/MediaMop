import { useMeQuery } from "../../lib/auth/queries";
import { FetcherFailedImportsCleanupPolicySection } from "./fetcher-failed-imports-cleanup-policy";

/** Failed imports UI embedded under Sonarr (TV) or Radarr (movies). */
export function FetcherFailedImportsEmbedded({ axis }: { axis: "tv" | "movies" }) {
  const me = useMeQuery();

  return (
    <div data-testid="fetcher-failed-imports-embedded" data-embedded-axis={axis}>
      <FetcherFailedImportsCleanupPolicySection role={me.data?.role} axes={axis === "tv" ? "tv" : "movies"} />
    </div>
  );
}
