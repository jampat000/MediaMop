# syntax=docker/dockerfile:1
# Preparation for #523 (epic #514, ADR-0017): a .NET build of the Weir image, kept SIDE BY SIDE
# with ./Dockerfile (the shipped Python image). Not wired into any workflow yet — build and run it
# by hand while the .NET server is still being ported area by area. Mirrors ./Dockerfile's user,
# paths, env defaults, port, volume, healthcheck and web build step; see docs/packaging-dotnet.md
# for what differs and what CI/release wiring #523 still needs.
#
# Build (single arch, matching your host):
#   docker build -f docker/server.Dockerfile -t weir-dotnet:local .
# Build multi-arch (needs buildx + QEMU for the arm64 apt-get step; see docs/packaging-dotnet.md):
#   docker buildx build -f docker/server.Dockerfile --platform linux/amd64,linux/arm64 -t weir-dotnet:local .
# Run:
#   docker run --rm -e WEIR_SESSION_SECRET=... -p 8788:8788 -v weir-dotnet-data:/data/weir weir-dotnet:local

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

# Built with --platform=$BUILDPLATFORM: the .NET SDK cross-publishes a self-contained app for
# another RID without emulation (only the target runtime's NuGet package is downloaded, nothing
# target-arch is executed at build time), so this stage always runs at native speed even when the
# final stage below is emulated for a second architecture.
FROM --platform=$BUILDPLATFORM mcr.microsoft.com/dotnet/sdk:10.0 AS server-build
ARG TARGETARCH
WORKDIR /src
# Only what `dotnet publish apps/server/src/Weir.Host` needs: the solution-level MSBuild files
# (Directory.Build.props reads apps/backend/pyproject.toml for the one shared product version —
# see apps/server/Directory.Build.props — so that file comes along too, unmodified) and the
# server source tree itself.
COPY apps/server/global.json apps/server/Directory.Build.props apps/server/Directory.Packages.props apps/server/NuGet.Config apps/server/Weir.slnx apps/server/
COPY apps/server/src apps/server/src
COPY apps/backend/pyproject.toml apps/backend/pyproject.toml
# Publish via the checked-in per-RID profile (Weir.Host/Properties/PublishProfiles/*.pubxml —
# the same command apps/server/README.md documents), NOT via --self-contained/-p:PublishSingleFile
# etc. as separate command-line switches. That distinction matters: a command-line
# -p:PublishSingleFile=true is a *global* MSBuild property applied to every project in the build
# graph including Weir.Infrastructure, which then fails to build with error IL3000
# ("Assembly.Location always returns an empty string in a single-file app") on the
# Assembly.Location check in Runtime/SystemServices.cs (DetectInstallType) — code that reads
# that empty string ON PURPOSE, to detect single-file mode. The profiles (and Weir.Host.csproj's
# own RID-conditioned PropertyGroup they build on) scope the same properties to the Weir.Host
# project only, which is what the analyzer actually expects; this never triggers IL3000.
# Verified locally for both linux-x64 and linux-arm64 (see docs/packaging-dotnet.md) — do not
# "simplify" this back to explicit -p: flags.
RUN case "$TARGETARCH" in \
      amd64) profile=linux-x64 ;; \
      arm64) profile=linux-arm64 ;; \
      *) echo "server.Dockerfile: unsupported TARGETARCH '$TARGETARCH'" >&2; exit 1 ;; \
    esac; \
    dotnet publish apps/server/src/Weir.Host -p:PublishProfile="$profile" -p:PublishDir=/out/

# Self-contained single-file (ADR-0017: "Publish: self-contained single-file for win-x64,
# linux-x64, linux-arm64") rather than a framework-dependent publish on the `aspnet` runtime
# image: it is the one publish shape already used for every other Weir.Host target (see
# apps/server/src/Weir.Host/Properties/PublishProfiles/*.pubxml), so Docker does not add a second
# publish mode to maintain. `runtime-deps` (not `aspnet` or `runtime`) is the correct base for a
# self-contained app: it ships only the native OS dependencies (libc, ICU is unused here because
# apps/server/Directory.Build.props sets InvariantGlobalization=true, OpenSSL, etc.) that .NET
# itself needs, without a second, unused copy of the managed runtime the single-file publish
# already bundles. `-bookworm-slim` matches the Debian release the Python image already uses, so
# the apt package set and the user/group setup below are identical to ./Dockerfile's.
FROM mcr.microsoft.com/dotnet/runtime-deps:10.0-bookworm-slim
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
  && mkdir -p /data/weir /opt/weir/web-dist \
  && chown -R weir:weir /data/weir /opt/weir /home/weir

COPY --from=server-build --chown=weir:weir /out/Weir /opt/weir/Weir
RUN chmod +x /opt/weir/Weir
COPY --from=web --chown=weir:weir /src/apps/web/dist /opt/weir/web-dist
COPY docker/server-entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENV WEIR_WEB_DIST=/opt/weir/web-dist
ENV WEIR_ENV=production
# Same reasoning as ./Dockerfile: the sign-in cookie is marked HTTPS-only automatically once a
# request actually arrives over HTTPS (directly, or via a proxy listed in
# WEIR_TRUSTED_PROXY_IPS); forcing it here would lock an operator out of a plain-HTTP LAN install.
# Set WEIR_SESSION_COOKIE_SECURE=true to force it.

EXPOSE 8788

HEALTHCHECK --interval=30s --timeout=5s --start-period=50s --retries=3 \
  CMD curl -fsS "http://127.0.0.1:${PORT:-8788}/health" >/dev/null || exit 1

ENTRYPOINT ["/entrypoint.sh"]
