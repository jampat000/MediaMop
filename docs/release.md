# MediaMop releases

MediaMop ships as a **tested source release**: a **git tag** on `main` that passed CI, plus a **GitHub Release** that documents how to run from source. There is **no** Docker image, **no** Windows installer, and **no** PyPI package in this path.

## Contract

1. **Version bump** — Update semver in **both** files in a **normal PR** (same version string):
   - `apps/backend/pyproject.toml` → `[project] version`
   - `apps/web/package.json` → `version`  
   The web shell also exposes this at runtime via `WEB_APP_VERSION` (Vite `define` from `package.json`).
2. **Merge to `main`** — PR must pass the **`Test`** workflow (`Test / mediamop`) on GitHub Actions.
3. **Tag** — Repository owner creates an **annotated** tag on the **merge commit** (not a random local commit):
   ```bash
   git fetch origin
   git checkout main
   git pull origin main
   git tag -a vX.Y.Z -m "MediaMop vX.Y.Z"
   git push origin vX.Y.Z
   ```
   Tag format: **`vX.Y.Z`** (semver, leading `v`), e.g. `v0.1.0`.
4. **GitHub Release** — Pushing `v*` triggers the **`Release`** workflow, which re-runs the same checks as **`Test`**, attaches **`mediamop-web-dist.zip`** (contents of `apps/web/dist/` after `npm run build`), and creates the GitHub Release for that tag (with generated notes plus the short body from the workflow). You can edit the Release description in the GitHub UI afterward if needed.

## What is shipped

| Deliverable | Meaning |
|-------------|---------|
| **Tag + source tree** | Authoritative snapshot; backend via `pip install -e ./apps/backend`, SQLite under `MEDIAMOP_HOME`, migrations, env per `docs/local-development.md`. |
| **`mediamop-web-dist.zip`** | Optional convenience: production **static** web build only. It is **not** a standalone app; the API is still required. |

## Not supported yet

- **Stable** Docker registry publishing (no semver-tagged GA image pipeline). **Alpha:** optional all-in-one image via **Actions → Docker alpha** and `docs/docker.md` (`Dockerfile` + GHCR).
- **Windows** installer / MSIX / signed `.exe` pipeline.
- **npm / PyPI** registry publishing.
- **Automation that commits to `main`** (no release bots or version-push workflows).

## CI alignment

- Day-to-day: **`.github/workflows/ci.yml`** — workflow name **`Test`**, job id **`mediamop`** (GitHub UI: **`Test / mediamop`**).
- **`Test`** triggers on **push** to **any** branch, on **`pull_request`**, and on **`workflow_dispatch`** (manual run from the Actions tab).
- Tag releases: **`.github/workflows/release.yml`** — workflow name **`Release`**, job **`tagged-release`**. It **re-runs the same validation steps** as **`Test`**, then publishes the GitHub Release and attaches **`mediamop-web-dist.zip`**. **Keep the two workflow step blocks aligned** when you change checks.

## Branch protection (GitHub Settings — manual)

Nothing in this repository turns on branch rules for you. Repo admins configure **rulesets** or **classic branch protection** for **`main`** (or your default branch) in GitHub. Typical expectation here:

- Require the **`Test / mediamop`** status check before merge (exact label can vary slightly by UI; it is the **`mediamop`** job from workflow **`Test`**).
- Whether PRs are required, who can push, and linear-history rules are **team policy** — not encoded in workflow files.

## Permissions note

The **`Release`** workflow sets workflow-wide **`contents: read`** and grants **`contents: write`** **only** on the **`tagged-release`** job, so the release action can create the GitHub Release and upload the zip. It does **not** push branches or open PRs.
