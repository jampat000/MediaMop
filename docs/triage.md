# Issue Triage

Weir issues should stay practical and reproducible. Every issue needs a clear user impact, an affected area, and a next action.

## Labels

- `type: bug` - something is broken or behaves incorrectly.
- `type: enhancement` - a new feature or workflow improvement.
- `type: docs` - documentation, screenshots, release notes, or support text.
- `area: refiner` - file remuxing, folder paths, processing events, or Processing settings. **The label
  still carries the old product name**; nothing user-visible has said "Refiner" since #563/#567, and
  #584 removed the name from the code. It has not been renamed because renaming it relabels every
  issue that already carries it. Read it as "Processing" until someone decides to rename it.
- `area: dashboard` - runtime health and summary metrics. Also carries the old page name: #459 folded
  the Dashboard into **Home** and 3.0.0 dropped the `/dashboard` route, so this is the Home and
  Processing Overview label now.
- `area: activity` - Activity timeline, filters, events, and live updates.
- `area: settings` - settings, security, logs, backup, and support screens.
- `area: logs` - runtime logs, diagnostics, retention, and observability.
- `area: web` - shared web shell, responsive layout, accessibility, and frontend delivery.
- `area: setup` - first-run setup and local development startup.
- `area: installer` - Windows setup, startup behavior, tray app, or upgrade flow.
- `area: docker` - image build, runtime config, ports, volumes, or container startup.
- `area: docs` - documentation site, build, dependencies, and publishing.
- `area: ci` - GitHub Actions, release automation, packaging, or dependency automation.

`area: pruner` also still exists on the repository. Pruner moved to Deluno in #473 and its tables were
dropped by migration `0036_drop_pruner_tables`; do not put it on new issues.
- `priority: critical` - data loss, security exposure, or release-blocking install failure.
- `priority: high` - core workflow broken with no reasonable workaround.
- `priority: normal` - important but not release-blocking.
- `priority: low` - small polish, cleanup, or nice-to-have.
- `status: needs triage` - newly opened and not yet confirmed.
- `status: blocked` - waiting on external information or a decision.
- `status: ready` - scoped enough to implement.

## Triage rules

1. Confirm the issue has version, install type, affected area, reproduction steps, expected result, and actual result.
2. Remove secrets, tokens, and private filesystem paths from logs before discussing them publicly.
3. Assign exactly one `type:*` label and at least one `area:*` label.
4. Add one `priority:*` label after impact is understood.
5. Close issues only when the fix is merged, intentionally declined, or superseded by a better issue.

## Backlog references

- Silent failure and truthfulness audit completed in the 1.0.30 backlog hardening tranche. New operator-visible no-op paths must log at debug or higher and disclose unavailable functionality explicitly.
- Release governance: [`release-governance.md`](release-governance.md)
- Windows and Docker smoke checks: [`smoke-checklists.md`](smoke-checklists.md)
- Security hardening: [`security-hardening.md`](security-hardening.md)
- UX polish baseline: [`ux-polish.md`](ux-polish.md)

