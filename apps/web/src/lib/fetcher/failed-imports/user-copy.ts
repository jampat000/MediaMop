/** Copy for the Fetcher failed-imports section only. */

export const FETCHER_FI_SECTION_INTRO_PRIMARY =
  "Radarr and Sonarr on the Fetcher lane: failed-import passes below, automation in the card, manual checks if you have access. The history table lists every persisted Fetcher job row—including Arr missing/upgrade search—not only failed-import drives.";

export const FETCHER_FI_RUNTIME_CARD_TITLE = "Automation";
export const FETCHER_FI_RUNTIME_CARD_SUBTITLE = "Saved when this loaded—not live status.";

export const FETCHER_FI_RUNTIME_WORKERS_HEADING = "Background automation";
export const FETCHER_FI_RUNTIME_WORKER_COUNT_LABEL = "Parallel slots (saved setting):";

export const FETCHER_FI_SCHEDULE_MOVIES_HEADING = "Movies (Radarr) — scheduled sweep";
export const FETCHER_FI_SCHEDULE_TV_HEADING = "TV (Sonarr) — scheduled sweep";

export const FETCHER_FI_MANUAL_SECTION_TITLE = "Run a check now";
export const FETCHER_FI_MANUAL_SECTION_BODY =
  "Adds one download-queue pass for that app to the worker list. Nothing runs in this browser.";

export const FETCHER_FI_MANUAL_BTN_MOVIES = "Movies (Radarr)";
export const FETCHER_FI_MANUAL_BTN_TV = "TV (Sonarr)";
export const FETCHER_FI_MANUAL_PENDING = "Sending…";

export const FETCHER_FI_MANUAL_ERR_MOVIES = "Could not start the movies check.";
export const FETCHER_FI_MANUAL_ERR_TV = "Could not start the TV check.";

export const FETCHER_FI_MANUAL_RESULT_MOVIES_PREFIX = "Movies (Radarr):";
export const FETCHER_FI_MANUAL_RESULT_TV_PREFIX = "TV (Sonarr):";

export const FETCHER_FI_PAGE_LOADING_TASKS = "Loading Fetcher jobs…";
export const FETCHER_FI_PAGE_ERR_LOAD_TASKS = "Could not load Fetcher jobs.";

export const FETCHER_FI_TASKS_SECTION_TITLE = "Fetcher jobs history";

export const FETCHER_FI_FILTER_DEFAULT_HELP = "Default: finished outcomes only.";
export const FETCHER_FI_FILTER_SINGLE_STATUS_HELP = "One outcome — see Status for the exact value.";

export const FETCHER_FI_TABLE_COL_WORK_TYPE = "What ran";
export const FETCHER_FI_TABLE_COL_STABLE_KEY = "Internal id";

export const FETCHER_FI_LIST_EMPTY = "Nothing matches this filter.";

export const FETCHER_FI_TECHNICAL_SUMMARY_LABEL = "Technical detail";

export const FETCHER_FI_POLICY_CARD_TITLE = "Removal rules (download queue)";
export const FETCHER_FI_POLICY_CARD_LEAD =
  "When a rule is on, a failed-import pass may remove matching Radarr or Sonarr download-queue rows. Saving does not run a pass.";
export const FETCHER_FI_POLICY_STORAGE_NOTE =
  "Stored in the MediaMop database. The first read creates that row from the server's environment defaults if needed; after that, only this saved row is used.";
export const FETCHER_FI_POLICY_VIEWER_NOTE = "Sign in as an operator to change removal rules.";
export const FETCHER_FI_POLICY_SAVE = "Save rules";
export const FETCHER_FI_POLICY_SAVING = "Saving…";
export const FETCHER_FI_POLICY_SAVED_HINT = "Rules apply on the next failed-import pass; nothing runs immediately.";
export const FETCHER_FI_POLICY_MOVIES_HEADING = "Movies (Radarr)";
export const FETCHER_FI_POLICY_TV_HEADING = "TV (Sonarr)";
export const FETCHER_FI_POLICY_TOGGLE_QUALITY = "Remove quality rejections";
export const FETCHER_FI_POLICY_TOGGLE_UNMATCHED = "Remove unmatched or manual-import rejections";
export const FETCHER_FI_POLICY_TOGGLE_CORRUPT = "Remove corrupt imports";
export const FETCHER_FI_POLICY_TOGGLE_DOWNLOAD_FAILED = "Remove failed downloads";
export const FETCHER_FI_POLICY_TOGGLE_IMPORT_FAILED = "Remove failed imports";
