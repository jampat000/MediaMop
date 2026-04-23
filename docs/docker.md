# Docker

Full Docker instructions live in [`docker/README.md`](../docker/README.md).

Short summary:

- one container: FastAPI + SQLite + bundled web UI on port `8788`
- same-origin API under `/api/v1`
- stable tags are published by `.github/workflows/release.yml`
- root `compose.yaml` pulls `ghcr.io/jampat000/mediamop:latest`
