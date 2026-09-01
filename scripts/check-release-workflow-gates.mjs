import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const scriptDir = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(scriptDir, "..");
const releasePath = resolve(repoRoot, ".github", "workflows", "release.yml");
const ciPath = resolve(repoRoot, ".github", "workflows", "ci.yml");
const release = readFileSync(releasePath, "utf8");
const ci = readFileSync(ciPath, "utf8");

function requireText(source, marker, file) {
  const index = source.indexOf(marker);
  if (index < 0) {
    throw new Error(
      `${file} is missing required release gate marker: ${marker}`,
    );
  }
  return index;
}

function requireOrder(source, markers, file) {
  let previous = -1;
  for (const marker of markers) {
    const current = requireText(source, marker, file);
    if (current <= previous) {
      throw new Error(
        `${file} has an unsafe release gate order near: ${marker}`,
      );
    }
    previous = current;
  }
}

function requireJob(source, jobName, file) {
  const marker = `\n  ${jobName}:\n`;
  const start = source.indexOf(marker);
  if (start < 0) {
    throw new Error(`${file} is missing required job: ${jobName}`);
  }
  const bodyStart = start + marker.length;
  const remaining = source.slice(bodyStart);
  const nextJob = remaining.search(/\n  [a-zA-Z0-9_-]+:\n/);
  return nextJob < 0 ? remaining : remaining.slice(0, nextJob);
}

function rejectText(source, marker, file) {
  if (source.includes(marker)) {
    throw new Error(`${file} contains forbidden workflow text: ${marker}`);
  }
}

const invalidRunnerTempFixture =
  "MEDIAMOP_LIVE_E2E_FIXTURE_HOST_ROOT: ${{ runner.temp }}";
rejectText(release, invalidRunnerTempFixture, ".github/workflows/release.yml");
rejectText(ci, invalidRunnerTempFixture, ".github/workflows/ci.yml");

const releasePublish = requireJob(
  release,
  "publish",
  ".github/workflows/release.yml",
);
const ciDockerSmoke = requireJob(
  ci,
  "docker-smoke",
  ".github/workflows/ci.yml",
);

requireOrder(
  release,
  [
    "- name: Build unpushed Docker release candidate",
    "push: false",
    "- name: Full live E2E against unpushed Docker release candidate",
    "- name: Cleanup unpushed Docker release candidate",
    "uses: docker/login-action@",
    "- name: Publish release Docker image",
    "- name: Verify published Docker manifest",
    "- name: Publish GitHub Release",
  ],
  ".github/workflows/release.yml",
);

for (const marker of [
  "MEDIAMOP_LIVE_EXPECTED_VERSION: ${{ steps.version.outputs.plain }}",
  "MEDIAMOP_SESSION_COOKIE_SECURE=false",
  "MEDIAMOP_LIVE_E2E_FIXTURE_SERVER_ROOT: /e2e-fixture",
  "MEDIAMOP_LIVE_E2E_FIXTURE_HOST_ROOT:$MEDIAMOP_LIVE_E2E_FIXTURE_SERVER_ROOT",
  "name: mediamop-docker-release-candidate-audit",
]) {
  requireText(releasePublish, marker, ".github/workflows/release.yml publish job");
}

requireOrder(
  ci,
  [
    "- name: Build MediaMop Docker image",
    "- name: Start MediaMop Docker candidate",
    "- name: Full live E2E against Docker candidate",
    "- name: Upload Docker live-audit evidence",
    "- name: Cleanup MediaMop Docker smoke",
  ],
  ".github/workflows/ci.yml",
);

for (const marker of [
  "MEDIAMOP_SESSION_COOKIE_SECURE=false",
  "MEDIAMOP_LIVE_E2E_FIXTURE_SERVER_ROOT: /e2e-fixture",
  "MEDIAMOP_LIVE_E2E_FIXTURE_HOST_ROOT:$MEDIAMOP_LIVE_E2E_FIXTURE_SERVER_ROOT",
  "name: mediamop-docker-live-audit",
]) {
  requireText(ciDockerSmoke, marker, ".github/workflows/ci.yml docker-smoke job");
}

console.log(
  "Docker candidate E2E and mounted pass-through lifecycle gates run before registry login and release publication.",
);
