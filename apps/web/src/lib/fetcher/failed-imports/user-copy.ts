/**
 * User-visible copy for Fetcher’s Radarr/Sonarr download-queue failed-import workflow.
 * Refiner (stale files on disk) is explicitly out of scope here.
 */

export const FETCHER_FI_PAGE_FRAMING_PRIMARY =
  "Fetcher runs MediaMop’s Radarr and Sonarr download-queue failed-import review and removal. This section lists recorded tasks and the settings that drive them.";

export const FETCHER_FI_PAGE_FRAMING_SCOPE =
  "These tasks walk each app’s download queue, remove eligible failed-import rows when your policy allows, and record what ran. That is queue work inside Radarr/Sonarr — not Refiner-style stale-file cleanup on disk (Refiner does not own this workflow).";

export const FETCHER_FI_RUNTIME_CARD_TITLE = "Loaded settings (read-only)";
export const FETCHER_FI_RUNTIME_CARD_SUBTITLE =
  "From saved configuration when this loaded — not proof that background runners or timed passes are active.";

export const FETCHER_FI_RUNTIME_RUNNERS_HEADING = "Background runners";
export const FETCHER_FI_RUNTIME_RUNNER_COUNT_LABEL = "Runners (configured):";

export const FETCHER_FI_SCHEDULE_MOVIES_HEADING =
  "Movies (Radarr) — scheduled download-queue failed-import pass";
export const FETCHER_FI_SCHEDULE_TV_HEADING =
  "TV shows (Sonarr) — scheduled download-queue failed-import pass";

export const FETCHER_FI_MANUAL_SECTION_TITLE = "Queue failed-import download-queue pass";
export const FETCHER_FI_MANUAL_SECTION_BODY =
  "Adds or reuses one recorded task that will review that app’s download queue for failed-import rows and apply your removal policy. Nothing runs in this browser session; this does not show whether a runner started or finished.";

export const FETCHER_FI_MANUAL_BTN_MOVIES = "Movies — Radarr queue";
export const FETCHER_FI_MANUAL_BTN_TV = "TV shows — Sonarr queue";
export const FETCHER_FI_MANUAL_PENDING = "Adding to queue…";

export const FETCHER_FI_MANUAL_ERR_MOVIES = "Could not queue the movies failed-import pass.";
export const FETCHER_FI_MANUAL_ERR_TV = "Could not queue the TV failed-import pass.";

export const FETCHER_FI_MANUAL_RESULT_MOVIES_PREFIX = "Movies (Radarr):";
export const FETCHER_FI_MANUAL_RESULT_TV_PREFIX = "TV shows (Sonarr):";

export const FETCHER_FI_PAGE_LOADING_TASKS = "Loading task list…";
export const FETCHER_FI_PAGE_ERR_LOAD_TASKS = "Could not load the task list for this section.";

export const FETCHER_FI_TASKS_SECTION_TITLE = "Recorded tasks";

export const FETCHER_FI_FILTER_DEFAULT_HELP = "Showing the default: finished tasks only.";
export const FETCHER_FI_FILTER_SINGLE_STATUS_HELP =
  "Filtered to one stored status — see the Status column for the exact value.";

export const FETCHER_FI_TABLE_COL_TASK_KIND = "Task kind";
export const FETCHER_FI_TABLE_COL_UNIQUENESS_KEY = "Uniqueness key";
