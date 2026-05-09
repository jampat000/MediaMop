# Docker

Full Docker instructions live in [`docker/README.md`](../docker/README.md).

Short summary:

- one container: FastAPI + SQLite + bundled web UI on port `8788`
- same-origin API under `/api/v1`
- stable tags are published by `.github/workflows/release.yml`
- root `compose.yaml` pulls `ghcr.io/jampat000/mediamop:latest`
- release smoke validation is defined in [`smoke-checklists.md`](smoke-checklists.md)

Upgrade continuity requirements:

- persist `MEDIAMOP_HOME` on a durable volume so SQLite data survives container replacement
- keep `MEDIAMOP_SESSION_SECRET` stable across upgrades so browser sessions remain valid
- if either value changes unexpectedly, users can be forced back through sign-in/setup flows
