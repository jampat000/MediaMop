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

- Libraries/path settings: saved paths are used by new scans and per-file work after save. Missing folders are warnings at runtime, not save blockers.
- Processing settings: files-at-once and age/size guardrails are database-backed operator settings used by active Refiner worker gating and new watched-folder scans.
- Audio/subtitle defaults: saved rules are used by new Refiner file passes after save.
- Runtime settings endpoint: read-only startup configuration. Any value requiring environment changes and restart must remain labelled as restart-required.

## Pruner settings

- Connection settings: saved server URL and credentials are tested by provider-specific connection checks.
- Rule/filter settings: saved settings are used by the next preview scan.
- Scheduled scans: create saved review snapshots. Deletion only happens from a saved snapshot, either by explicit operator confirmation or by clearly labelled automatic apply.
- Older preview controls must not use "dry run" or "cleanup now" wording when the action only scans and creates a review snapshot.

## Subber settings

- Sonarr/Radarr connections and path mappings are saved immediately and used by new sync/search work.
- Provider settings are saved per provider and used by the next subtitle search.
- Schedule windows affect scheduled search work; import/webhook searches can still run immediately and are labelled separately.
- Preference and upgrade settings are database-backed and used by new Subber jobs after save.
