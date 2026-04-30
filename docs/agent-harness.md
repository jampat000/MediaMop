# Agent Harness Operating Model

MediaMop should be easy for coding agents to inspect, modify, validate, and repair without relying on hidden context.

This document adapts the harness-engineering model to this repository: humans steer priorities and acceptance criteria; agents execute changes through repo-local tools, tests, docs, and pull requests.

## Principles

1. **Repository knowledge is the source of truth.**
   If a decision matters after the current conversation ends, put it in docs, tests, scripts, schemas, or issue templates.

2. **The root agent guide is a map, not a manual.**
   [`../AGENTS.md`](../AGENTS.md) points to deeper docs. Keep it short enough that agents can read it on every task.

3. **Make the app legible to agents.**
   Prefer reproducible local commands, deterministic fixtures, logs, health endpoints, screenshots, and smoke scripts over manual-only QA.

4. **Promote repeated review comments into enforcement.**
   If the same rule is repeated twice, encode it in a test, linter, script, checklist, or durable doc.

5. **Preserve safety contracts mechanically.**
   File lifecycle, release, security, and upgrade rules should have tests or smoke checks where practical.

6. **Keep PRs small and recoverable.**
   Agent throughput is useful only when each change has a clear scope, validation path, and rollback story.

## Expected Agent Loop

1. Read [`../AGENTS.md`](../AGENTS.md), then the smallest relevant docs.
2. Inspect current code before proposing implementation details.
3. Implement focused changes on a branch.
4. Run the narrowest meaningful validation first, then broader checks as risk increases.
5. Update docs or execution plans when the change alters durable behavior.
6. Open or update a pull request with summary, validation, and remaining risks.

## Feedback Loops To Prefer

- Backend unit tests for service logic, schema behavior, file lifecycle, and worker decisions.
- Frontend unit tests for query states, dashboard summaries, settings flows, and user-facing text.
- E2E smoke tests for login, app shell navigation, dashboard refresh, and module entry points.
- Windows package smoke for installer, tray, startup, and upgrade behavior.
- Docker smoke for container startup and health.
- GitHub issues for backlog items that should survive beyond the current PR.

## What To Encode Next

Use [`exec-plans/tech-debt-tracker.md`](exec-plans/tech-debt-tracker.md) for cleanup candidates that are real but not release blockers.

Promote items from that tracker into issues or execution plans when they become scoped enough to implement.
