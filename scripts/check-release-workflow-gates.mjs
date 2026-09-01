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
  requireText(release, marker, ".github/workflows/release.yml");
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
  requireText(ci, marker, ".github/workflows/ci.yml");
}

console.log(
  "Docker candidate E2E and mounted pass-through lifecycle gates run before registry login and release publication.",
);
