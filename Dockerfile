# syntax=docker/dockerfile:1
# All-in-one: FastAPI + SQLite + bundled Vite production UI (same origin /api/v1).
# Build: docker build -t mediamop:local .
# Run:  docker run --rm -e MEDIAMOP_SESSION_SECRET=... -p 8788:8788 -v mediamop-data:/data/mediamop mediamop:local

FROM node:20-bookworm-slim AS web
WORKDIR /src/apps/web
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci
COPY apps/web .
COPY scripts/dev-ports.json /src/scripts/dev-ports.json
RUN npm run build

FROM python:3.11-slim-bookworm
RUN apt-get update \
  && apt-get install -y --no-install-recommends \
    ca-certificates \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/mediamop
COPY apps/backend /opt/mediamop/apps/backend
RUN pip install --no-cache-dir --upgrade pip \
  && pip install --no-cache-dir -e "/opt/mediamop/apps/backend"

COPY --from=web /src/apps/web/dist /opt/mediamop/web-dist
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENV PYTHONPATH=/opt/mediamop/apps/backend/src
ENV MEDIAMOP_WEB_DIST=/opt/mediamop/web-dist
ENV MEDIAMOP_ENV=production

EXPOSE 8788
ENTRYPOINT ["/entrypoint.sh"]
