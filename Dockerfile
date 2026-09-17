# syntax=docker/dockerfile:1
# All-in-one: FastAPI + SQLite + bundled Vite production UI (same origin /api/v1).
# Build: docker build -t weir:local .
# Run:  docker run --rm -e WEIR_SESSION_SECRET=... -p 8788:8788 -v weir-data:/data/weir weir:local

FROM node:24-bookworm-slim AS web
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
    gosu \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/weir
RUN groupadd --system --gid 1000 weir \
  && useradd --system --uid 1000 --gid 1000 --create-home --home-dir /home/weir --shell /usr/sbin/nologin weir \
  && mkdir -p /data/weir /opt/weir/apps/backend /opt/weir/web-dist \
  && chown -R weir:weir /data/weir /opt/weir /home/weir
COPY --chown=weir:weir apps/backend /opt/weir/apps/backend
RUN python -m venv /opt/weir/.venv \
  && /opt/weir/.venv/bin/pip install --no-cache-dir --prefer-binary --require-hashes -r /opt/weir/apps/backend/requirements-runtime.lock \
  && /opt/weir/.venv/bin/pip install --no-cache-dir --no-deps --no-build-isolation -e "/opt/weir/apps/backend"

COPY --from=web --chown=weir:weir /src/apps/web/dist /opt/weir/web-dist
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENV PYTHONPATH=/opt/weir/apps/backend/src
ENV PATH=/opt/weir/.venv/bin:$PATH
ENV WEIR_WEB_DIST=/opt/weir/web-dist
ENV WEIR_ENV=production
# The sign-in cookie is marked HTTPS-only automatically when a request actually arrives over
# HTTPS (directly, or via a proxy listed in WEIR_TRUSTED_PROXY_IPS). Forcing it on here
# would discard the cookie on a plain-HTTP LAN install and lock the operator out for nothing,
# so the default is left as `auto`. Set WEIR_SESSION_COOKIE_SECURE=true to force it.

EXPOSE 8788

HEALTHCHECK --interval=30s --timeout=5s --start-period=50s --retries=3 \
  CMD curl -fsS "http://127.0.0.1:${PORT:-8788}/health" >/dev/null || exit 1

ENTRYPOINT ["/entrypoint.sh"]
