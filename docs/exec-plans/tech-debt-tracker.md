# Technical Debt Tracker

This is the durable cleanup queue for non-release-blocking work. Use GitHub issues for scoped backlog items and this file for cross-cutting cleanup themes that are not ready to implement yet.

## Current Items

| Area | Item | Why It Matters | Next Action |
| --- | --- | --- | --- |
| Frontend dependencies | Evaluate React 19 upgrade | Major runtime dependency should be isolated from release blocker fixes. | Track in GitHub issue #129. |
| Agent harness | Add more mechanical doc freshness checks | Agent guidance rots unless basic links and required maps are checked automatically. | Keep `scripts/check-agent-docs.mjs` in CI and expand only when drift appears. |
| Observability | Make local logs and key metrics easier for agents to query | Faster bug reproduction and validation without manual log scraping. | Identify minimum local log query helper after current release fixes. |
| UI validation | Add repeatable browser screenshot checks for high-risk pages | Dashboard/settings regressions are easier to catch visually. | Scope after current release backlog settles. |

## Maintenance Rules

- Remove items when they become issues, execution plans, or completed work.
- Keep entries short and actionable.
- Do not use this file for release blockers; those should become issues with priority labels.
