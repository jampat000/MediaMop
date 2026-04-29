# MediaMop diagnostics contract

MediaMop is a single-node media automation app that can move, write, and delete user media. Diagnostics must be useful to an operator without exposing secrets or hiding unsafe states.

## Structured events

Operational events should use the shared diagnostics vocabulary in `mediamop.platform.observability.diagnostics`.

Events should include the fields that apply:

- `module`: `refiner`, `pruner`, `subber`, `system`, or shared service name.
- `provider`: upstream system such as Plex, Jellyfin, Emby, Radarr, Sonarr, or subtitle provider.
- `media_scope`: `tv`, `movies`, or both when the operation spans both.
- `action`: scan, preview, apply, remux, cleanup, search, import, connection test, schedule run, or upgrade.
- `trigger`: manual, scheduled, worker, startup, retry, or system.
- `result`: success, skipped, retrying, warning, failed, or running.
- `counts`: scanned, matched, previewed, applied, deleted, skipped, failed, retried, or written.
- `correlation_id`: request, job, run, or preview snapshot identifier when the workflow spans multiple steps.
- `reason` and `next_action`: plain operator-readable explanation when an operation fails, skips, or needs attention.

## Severity rules

- `debug`: routine diagnostics, commands, normal probe details.
- `info`: successful user-visible work and normal scheduled work.
- `warning`: recoverable issue needing operator awareness.
- `error`: failed job/action or unrecoverable failure.

Normal operation must not be warning-level output.

## Correlation

Long-running work must preserve a correlation identifier across API requests, durable queue jobs, worker execution, provider calls, activity rows, and logs. A job id, preview snapshot id, run id, or request id is acceptable if it is stable for that workflow.

## Operator wording

Messages must explain what happened and what the user should do next. Do not expose raw exceptions as the only message. Do not expose secrets, tokens, passwords, API keys, cookie values, or signed session data.

## Runtime truthfulness

Readiness, dashboard status, metrics, activity, and settings pages must reflect real runtime behaviour. A disabled worker, unavailable dependency, queued but unprocessed job, or skipped deletion must be shown as degraded/skipped, not successful.

Dashboard and overview success totals must be derived from explicit terminal outcome components. Do not calculate a success total from queued jobs, scanned files, attempted work, or broad completed queue rows unless that queue row itself proves finalized work.
