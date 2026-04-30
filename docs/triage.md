# Issue Triage

MediaMop issues should stay practical and reproducible. Every issue needs a clear user impact, an affected area, and a next action.

## Labels

- `type: bug` - something is broken or behaves incorrectly.
- `type: enhancement` - a new feature or workflow improvement.
- `type: docs` - documentation, screenshots, release notes, or support text.
- `area: refiner` - file remuxing, folder paths, processing events, or Refiner settings.
- `area: pruner` - media server cleanup previews, deletes, savings, or Pruner settings.
- `area: subber` - subtitle downloads, Sonarr/Radarr integration, language preferences, or Subber settings.
- `area: dashboard` - overview, module health, runtime health, and summary metrics.
- `area: installer` - Windows setup, startup behavior, tray app, or upgrade flow.
- `area: docker` - image build, runtime config, ports, volumes, or container startup.
- `area: ci` - GitHub Actions, release automation, packaging, or dependency automation.
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

