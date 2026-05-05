import type { TopTab } from "./pruner-page-types";

export const PRUNER_TAB_BLURBS: Record<TopTab, string> = {
  overview:
    "See cross-provider status for connections, cleanup coverage, and items that need attention.",
  emby: "Manage one Emby server: test connection, set cleanup rules, and control run windows.",
  jellyfin:
    "Manage one Jellyfin server: test connection, set cleanup rules, and control run windows.",
  plex: "Manage one Plex server: test connection, set cleanup rules, and control run windows.",
  jobs: "View queued, running, and recent Pruner jobs across providers.",
  schedule:
    "Edit scheduled prune windows in the provider workspace and save changes per library.",
};

export const PRUNER_JOB_FILTER_OPTIONS = [
  { value: "recent", label: "Recent (all statuses, newest first)" },
  { value: "pending", label: "Pending" },
  { value: "running", label: "Running" },
  { value: "failed", label: "Failed" },
  { value: "completed", label: "Completed" },
] as const;
