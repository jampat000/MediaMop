# MediaMop operator messaging standard

MediaMop activity, status, and job messages are for the person operating the app. They must explain what happened in plain language without requiring knowledge of queue keys, worker names, ffmpeg internals, or raw provider payloads.

## Severity

- `info`: normal successful work, no-op/skipped work, and expected empty results.
- `warning`: recoverable provider or environment issue where MediaMop can continue or retry, but the operator may need to know.
- `error`: a workflow failed and needs operator attention before the expected outcome can be trusted.
- `debug`: implementation detail for runtime logs only, not the primary Activity message.

Normal work must not be logged or displayed as a warning. Provider-level recoverable failures must identify the provider and show that the rest of the workflow continued.

## Required fields

Every operational Activity detail should include stable fields when applicable:

- `module`: `refiner`, `pruner`, `subber`, `auth`, or `system`.
- `action`: plain workflow action such as `scan`, `preview`, `apply`, `remux`, `search`, `sync`, `cleanup`, `connection_test`, or `upgrade`.
- `trigger`: `manual`, `scheduled`, `startup`, `worker`, `retry`, or `system`.
- `result`: `success`, `skipped`, `warning`, `retrying`, `running`, or `failed`.
- `severity`: derived from `result`; do not hand-pick a scarier severity.
- `provider`: provider/server name when relevant, for example `Jellyfin`, `Plex`, `Sonarr`, or `Radarr`.
- `media_scope`: machine-stable scope such as `tv` or `movies`.
- `counts`: numeric result counts such as `checked`, `found`, `queued`, `removed`, `skipped`, `failed`, `downloaded`, or `upgraded`.
- `user_message`: one plain-language sentence suitable for the UI.
- `next_action`: only when the operator can do something useful.

## Failure Messages

Failures must use the shared failure helper in `mediamop.platform.observability.failure_messages` before they reach job `last_error`, Activity detail, or provider result arrays.

- Say what failed with module and action, for example `Subber subtitle search`.
- Say where it failed when known, for example provider, server, or media scope.
- Classify why it failed as `rate_limit`, `credential`, `auth`, `network`, `validation`, `not_found`, or `internal`.
- Say what happens next: skipped and continued, will retry, or marked failed.
- Add `next_action` for credential, auth, network, validation, and rate-limit cases.
- Keep raw stack traces and exception internals in structured logs, not primary UI text.

## Wording

- Use product names and user concepts: `Movies`, `TV episodes`, `connection test`, `scan`, `preview`, `saved list`, `removed from library`, `processed file`.
- Avoid engineering jargon in titles: no queue kind, durable job kind, raw exception class, HTTP stack trace, `remux` as the leading user-facing noun, or vague copy such as `this tab`.
- Automated or destructive work must be explicit: `scheduled`, `automatic`, `from saved preview list`, `removed`, `deleted`, `skipped`, and counts must be visible.
- No-op work is still successful when the target already matched the configured plan. It should say `No changes needed`, not `warning`.
- Secrets must never appear in messages, Activity details, or logs.

## Visible = Truthful

- Any feature, provider, rule, or setting shown in the UI must either work in this release or be explicitly labelled `Not available`, `Coming soon`, or `Unsupported in this version`.
- Backend handlers must never silently no-op on operator-visible work. If nothing was done, log at least a debug line; if a configured capability is unavailable, log a warning and make the UI disclose that state.
- MediaMop must not spend provider/network quota on features whose results will always be discarded.

## Implementation

Backend producers should use `mediamop.platform.observability.operator_messages` for shared labels, titles, and detail envelopes. Frontend pages may render richer layouts, but must preserve the same result/severity meaning and must not invent success states that the backend did not report.
