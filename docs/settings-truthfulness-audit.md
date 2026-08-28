# Settings truthfulness audit

MediaMop settings must describe runtime behaviour as shipped, not intended behaviour.

## Global settings

- Setup wizard: reopens the guided setup route immediately. It is not a sidebar item.
- Timezone: saved to the database and affects suite time labels after save.
- Log retention: saved to the database and enforced by runtime log pruning; no restart is required.
- Display density: browser-local preference and applies immediately in that browser only.
- Backup schedule: saved to the database. The running backup worker reads the saved schedule before each tick.
- Upgrade: reflects the running backend version and the latest public release known to the update service.
- Security settings shown in the UI are database-backed. Server-only auth cookie, HTTPS, and rate-limit configuration is labelled as startup configuration, not editable UI state.

## Refiner settings

- Libraries: each library carries its own folders, file types, exclusions, schedule and guardrails, saved in the database and used by new scans and per-file work after save. Missing folders are warnings at runtime, not save blockers. Removing a library is refused while it still has queued or running work, because those jobs resolve their folders from it.
- Rule sets: audio and subtitle handling is a named object a library points at, so two libraries can share one. Deleting a rule set a library still references is refused rather than silently stripping that handling.
- Processing settings: files-at-once and age/size guardrails are database-backed operator settings used by active Refiner worker gating and new watched-folder scans.
- Audio/subtitle defaults: saved rules are used by new Refiner file passes after save.
- Runtime settings endpoint: read-only startup configuration. Any value requiring environment changes and restart must remain labelled as restart-required.
- Watched-folder scan schedule: whether each scope is scanned, and how often, is **per scope on the Libraries tab**, saved in the database and applied without a restart. There is no environment variable for it. `MEDIAMOP_REFINER_WATCHED_FOLDER_REMUX_SCAN_DISPATCH_SCHEDULE_ENABLED` and `..._SCHEDULE_INTERVAL_SECONDS` were removed in #329: the scheduler never read either, while the runtime-settings endpoint reported the flag as live configuration — so an operator could read `false` while scheduled scans ran.
- Worker count: `MEDIAMOP_REFINER_WORKER_COUNT` is an internal startup slot cap (default 8), not the number of files processed at once. The operator-facing "Files at once" value is the effective limit and needs no restart.

## Pruner settings

- Connection settings: saved server URL and credentials are tested by provider-specific connection checks.
- Rule/filter settings: saved settings are used by the next preview scan.
- Scheduled scans: create saved review snapshots. Deletion only happens from a saved snapshot, either by explicit operator confirmation or by clearly labelled automatic apply.
- Older preview controls must not use "dry run" or "cleanup now" wording when the action only scans and creates a review snapshot.

