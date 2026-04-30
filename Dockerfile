# syntax=docker/dockerfile:1
# All-in-one: FastAPI + SQLite + bundled Vite production UI (same origin /api/v1).
# Build: docker build -t mediamop:local .
# Run:  docker run --rm -e MEDIAMOP_SESSION_SECRET=... -p 8788:8788 -v mediamop-data:/data/mediamop mediamop:local

FROM node:20-bookworm-slim AS web
WORKDIR /src/apps/web
COPY apps/web/package.json apps/web/package-lock.json ./
# Resilient installs in CI/buildx (registry flakes, slow links); lockfile must stay in sync with package.json.
RUN npm config set fund false \
  && npm config set audit false \
  && npm config set fetch-retries 10 \
  && npm config set fetch-retry-mintimeout 20000 \
  && npm config set fetch-retry-maxtimeout 180000 \
  && npm ci --no-audit --no-fund
COPY apps/web .
COPY scripts/dev-ports.json /src/scripts/dev-ports.json
RUN npm run build

FROM python:3.11-slim-bookworm
RUN apt-get update \
  && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    ffmpeg \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/mediamop
RUN groupadd --system --gid 1000 mediamop \
  && useradd --system --uid 1000 --gid 1000 --create-home --home-dir /home/mediamop --shell /usr/sbin/nologin mediamop \
  && mkdir -p /data/mediamop /opt/mediamop/apps/backend /opt/mediamop/web-dist \
  && chown -R mediamop:mediamop /data/mediamop /opt/mediamop /home/mediamop
COPY --chown=mediamop:mediamop apps/backend /opt/mediamop/apps/backend
RUN python -m venv /opt/mediamop/.venv \
  && /opt/mediamop/.venv/bin/pip install --no-cache-dir --upgrade pip \
  && /opt/mediamop/.venv/bin/pip install --no-cache-dir --prefer-binary -e "/opt/mediamop/apps/backend"

COPY --from=web --chown=mediamop:mediamop /src/apps/web/dist /opt/mediamop/web-dist
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENV PYTHONPATH=/opt/mediamop/apps/backend/src
ENV PATH=/opt/mediamop/.venv/bin:$PATH
ENV MEDIAMOP_WEB_DIST=/opt/mediamop/web-dist
ENV MEDIAMOP_ENV=production
# All-in-one is usually reached over plain HTTP first (localhost / LAN). Secure cookies would
# never be sent on http://, which breaks sign-in. Set MEDIAMOP_SESSION_COOKIE_SECURE=true when
# browsers always use HTTPS (e.g. TLS terminated at a reverse proxy in front of this container).
ENV MEDIAMOP_SESSION_COOKIE_SECURE=false

USER mediamop

EXPOSE 8788

HEALTHCHECK --interval=30s --timeout=5s --start-period=50s --retries=3 \
  CMD curl -fsS "http://127.0.0.1:${PORT:-8788}/health" >/dev/null || exit 1

ENTRYPOINT ["/entrypoint.sh"]
