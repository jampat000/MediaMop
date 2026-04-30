# MediaMop Agent Map

This file is the short entry point for coding agents. Keep detailed rules in linked docs so this stays readable.

## Repository Boundaries

- Canonical checkout: `C:\Users\User\Projects\MediaMop`.
- Do not use old duplicate checkouts or copied source trees.
- Treat `main` as protected. Use short-lived branches and pull requests.
- Never revert user changes unless the user explicitly asks for that exact revert.

## Start Here

- Project overview: [`README.md`](README.md)
- Architecture map: [`ARCHITECTURE.md`](ARCHITECTURE.md)
- Local development: [`docs/local-development.md`](docs/local-development.md)
- Documentation index: [`docs/README.md`](docs/README.md)
- Agent operating model: [`docs/agent-harness.md`](docs/agent-harness.md)
- Issue triage: [`docs/triage.md`](docs/triage.md)
- Release governance: [`docs/release-governance.md`](docs/release-governance.md)

## High-Risk Invariants

- Media mutation safety lives in [`docs/file-lifecycle-contract.md`](docs/file-lifecycle-contract.md).
- Windows installer and upgrade behavior must follow [`docs/release.md`](docs/release.md) and [`docs/smoke-checklists.md`](docs/smoke-checklists.md).
- Secrets and credential rotation rules live in [`docs/security-hardening.md`](docs/security-hardening.md).
- Operator-facing messages should follow [`docs/operator-messaging-standard.md`](docs/operator-messaging-standard.md).

## Validation Defaults

- Backend: from `apps/backend`, run `pytest -q` after setting local dev env.
- Frontend: from `apps/web`, run `npm run build` and `npm run test`.
- E2E and packaging smoke checks are documented in [`CONTRIBUTING.md`](CONTRIBUTING.md).
- Docs map validation: `node scripts/check-agent-docs.mjs`.

## Working Style

- Encode recurring lessons in docs, scripts, tests, or CI instead of relying on chat memory.
- Prefer small PRs with focused validation.
- If a task exposes missing tooling or missing repository knowledge, add that capability as part of the fix or open a backlog issue.
