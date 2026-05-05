# MediaMop Documentation Index

This directory is the repository-local system of record. Keep durable decisions here instead of relying on chat history, issue comments, or local notes.

## Operating Model

- [`agent-harness.md`](agent-harness.md) - agent-first working model, feedback loops, and cleanup cadence.
- [`triage.md`](triage.md) - issue labels, impact triage, and backlog expectations.
- [`release-governance.md`](release-governance.md) - release controls and pre/post-release gates.
- [`release.md`](release.md) - release procedure and artifacts.
- [`release-notes/TEMPLATE.md`](release-notes/TEMPLATE.md) - required plain-language release notes template.
- [`smoke-checklists.md`](smoke-checklists.md) - Windows and Docker smoke paths.

## Architecture And Runtime

- [`../ARCHITECTURE.md`](../ARCHITECTURE.md) - top-level architecture map.
- [`adr/README.md`](adr/README.md) - architecture decision records.
- [`deployment-model.md`](deployment-model.md) - deployment assumptions.
- [`docker.md`](docker.md) - Docker runtime behavior.
- [`ports.md`](ports.md) - canonical ports.
- [`local-development.md`](local-development.md) - local setup and dev workflow.

## Product And UX Rules

- [`visual-identity.md`](visual-identity.md) - brand and visual identity.
- [`ux-polish.md`](ux-polish.md) - UI polish baseline.
- [`operator-messaging-standard.md`](operator-messaging-standard.md) - operator-facing wording.
- [`pruner-forward-design-constraints.md`](pruner-forward-design-constraints.md) - Pruner safety/design constraints.

## Reliability And Safety

- [`file-lifecycle-contract.md`](file-lifecycle-contract.md) - file mutation and deletion safety.
- [`diagnostics-contract.md`](diagnostics-contract.md) - diagnostics behavior.
- [`security-hardening.md`](security-hardening.md) - security posture and credential handling.
- [`settings-truthfulness-audit.md`](settings-truthfulness-audit.md) - settings truthfulness audit history.

## Execution Plans

- [`exec-plans/README.md`](exec-plans/README.md) - plan format and lifecycle.
- [`exec-plans/tech-debt-tracker.md`](exec-plans/tech-debt-tracker.md) - durable technical debt and cleanup queue.

## Maintenance Rule

When code behavior changes a documented invariant, update the relevant doc in the same pull request. If a doc cannot be updated confidently, open a follow-up issue with the missing context.
