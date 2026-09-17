# syntax=docker/dockerfile:1
# All-in-one Weir image: the .NET server (apps/server), SQLite, ffmpeg and the production web UI
# (same origin /api/v1).
#
# Build (your host's architecture):
#   docker build -t weir:local .
# Build both published architectures (needs buildx; QEMU for the non-native final stage):
#   docker buildx build --platform linux/amd64,linux/arm64 -t weir:local .
# Run:
#   docker run --rm -e WEIR_SESSION_SECRET=... -p 8788:8788 -v weir-data:/data/weir weir:local

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

# Runs on the build machine's own architecture (--platform=$BUILDPLATFORM): the .NET SDK cross-publishes
# a self-contained app for another runtime without emulation (it only downloads the target runtime pack),
# so this stage stays fast even when the final stage is emulated for a second architecture.
# Pinned to the exact SDK in apps/server/global.json: newer SDKs add analyzer rules, and warnings are errors.
FROM --platform=$BUILDPLATFORM mcr.microsoft.com/dotnet/sdk:10.0.400-noble AS server-build
ARG TARGETARCH
WORKDIR /src
# The solution-level MSBuild files (Directory.Build.props holds the product version) and the server source.
# Weir.Api embeds the committed OpenAPI document from apps/web/openapi.
COPY apps/server/global.json apps/server/Directory.Build.props apps/server/Directory.Packages.props apps/server/NuGet.Config apps/server/Weir.slnx apps/server/
COPY apps/server/src apps/server/src
COPY apps/web/openapi apps/web/openapi
# Publish through the checked-in per-runtime profile (Weir.Host/Properties/PublishProfiles/*.pubxml), not
# with -r/--self-contained/-p:PublishSingleFile on the command line. A command-line PublishSingleFile is a
# global property that reaches every project, and the single-file analyzer then fails Weir.Infrastructure
# with IL3000 on the Assembly.Location check that detects single-file mode on purpose. The profiles scope
# those properties to Weir.Host. Do not "simplify" this back to explicit flags.
RUN case "$TARGETARCH" in \
      amd64) profile=linux-x64 ;; \
      arm64) profile=linux-arm64 ;; \
      *) echo "Dockerfile: unsupported TARGETARCH '$TARGETARCH'" >&2; exit 1 ;; \
    esac; \
    dotnet publish apps/server/src/Weir.Host -p:PublishProfile="$profile" -p:PublishDir=/out/

# A self-contained single-file publish needs only the native dependencies .NET itself uses (libc,
# OpenSSL; not ICU, because Directory.Build.props sets InvariantGlobalization), which is exactly what
# runtime-deps ships. No second copy of the managed runtime.
# .NET 10 images are Ubuntu 24.04 (noble); there is no Debian bookworm runtime-deps tag.
FROM mcr.microsoft.com/dotnet/runtime-deps:10.0-noble
RUN apt-get update \
  && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    ffmpeg \
    gosu \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/weir
# Ubuntu base images ship an `ubuntu` user and group on uid/gid 1000; free them for `weir`.
RUN if id -u ubuntu >/dev/null 2>&1; then userdel --remove ubuntu; fi   && if getent group ubuntu >/dev/null 2>&1; then groupdel ubuntu; fi   && groupadd --system --gid 1000 weir \
  && useradd --system --uid 1000 --gid 1000 --create-home --home-dir /home/weir --shell /usr/sbin/nologin weir \
  && mkdir -p /data/weir /opt/weir/web-dist \
  && chown -R weir:weir /data/weir /opt/weir /home/weir

COPY --from=server-build --chown=weir:weir /out/Weir /opt/weir/Weir
RUN chmod +x /opt/weir/Weir
COPY --from=web --chown=weir:weir /src/apps/web/dist /opt/weir/web-dist
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

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
