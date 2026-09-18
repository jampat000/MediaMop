import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

import { REQUIRED_EVIDENCE } from "./verify-ci-for-release.mjs";

// The release's safety rule: nothing reaches ghcr or the Releases page unless every check passed.
// release.yml runs its checks as parallel jobs, so the rule is expressed as the shape of the workflow:
// one `publish` job needs every other job and is the only one able to publish anything, and inside
// each job the steps come in a safe order.

const scriptDir = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(scriptDir, "..");
const releasePath = resolve(repoRoot, ".github", "workflows", "release.yml");
const ciPath = resolve(repoRoot, ".github", "workflows", "ci.yml");
const release = readFileSync(releasePath, "utf8").replace(/\r\n/g, "\n");
const ci = readFileSync(ciPath, "utf8").replace(/\r\n/g, "\n");
const RELEASE = ".github/workflows/release.yml";
const CI = ".github/workflows/ci.yml";

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

function jobIds(source) {
  const jobsStart = source.indexOf("\njobs:\n");
  if (jobsStart < 0) throw new Error("A workflow has no jobs: section.");
  return [...source.slice(jobsStart).matchAll(/\n {2}([a-zA-Z0-9_-]+):\n/g)].map((match) => match[1]);
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
  "WEIR_LIVE_E2E_FIXTURE_HOST_ROOT: ${{ runner.temp }}";
rejectText(release, invalidRunnerTempFixture, RELEASE);
rejectText(ci, invalidRunnerTempFixture, CI);

// --- release.yml ------------------------------------------------------------------------------------

// No write access for the workflow as a whole; publish grants itself what it needs.
const releaseTop = release
  .slice(0, release.indexOf("\njobs:\n"))
  .split("\n")
  .filter((line) => !line.trimStart().startsWith("#"))
  .join("\n");
if (/:\s*write\b|write-all/.test(releaseTop)) {
  throw new Error(`${RELEASE} grants write access at workflow level; only the publish job may have it.`);
}

const releaseJobs = jobIds(release);
const publish = requireJob(release, "publish", RELEASE);

// Anything that can put something in public is confined to publish.
const publishingText = [
  "uses: docker/login-action@",
  "push: true",
  "docker push",
  "packages: write",
  "contents: write",
  "uses: softprops/action-gh-release@",
  "gh release",
];
for (const job of releaseJobs.filter((name) => name !== "publish")) {
  const body = requireJob(release, job, RELEASE);
  for (const marker of publishingText) {
    rejectText(body, marker, `${RELEASE} job ${job} (only publish may publish)`);
  }
}

// publish waits for every other job, and only when they all succeeded.
const needsLine = publish.match(/\n {4}needs: \[([^\]]*)\]\n/);
if (!needsLine) {
  throw new Error(`${RELEASE} publish must declare its gates as needs: [job, ...] on one line.`);
}
const publishNeeds = needsLine[1].split(",").map((name) => name.trim()).filter(Boolean);
for (const job of releaseJobs.filter((name) => name !== "publish")) {
  if (!publishNeeds.includes(job)) {
    throw new Error(`${RELEASE} publish does not need ${job}; it could publish before ${job} passes.`);
  }
}
const publishIf = (publish.match(/\n {4}if: (.*)\n/) || [])[1] || "";
for (const override of ["always()", "failure()", "cancelled()", "success() ||"]) {
  if (publishIf.includes(override)) {
    throw new Error(`${RELEASE} publish's if: must not contain ${override}; it would run past a failed gate.`);
  }
}

requireOrder(
  publish,
  [
    "uses: docker/setup-qemu-action@",
    "uses: docker/login-action@",
    "- name: Publish release Docker image",
    "platforms: linux/amd64,linux/arm64",
    "push: true",
    "- name: Verify published Docker manifest",
    "- name: Smoke test published Docker image",
    "- name: Prepare user-facing release notes",
    "- name: Publish GitHub Release",
  ],
  `${RELEASE} publish job`,
);

// The tagged commit must be one ci.yml already passed on.
const ciPassed = requireJob(release, "ci-passed", RELEASE);
for (const marker of ["actions: read", "node scripts/verify-ci-for-release.mjs"]) {
  requireText(ciPassed, marker, `${RELEASE} ci-passed job`);
}

const validate = requireJob(release, "validate", RELEASE);
for (const marker of [
  "- name: Release notes file present",
  "node scripts/check-dotnet-vulnerabilities.mjs",
  "- name: Weir E2E smoke (Playwright + real .NET server)",
  "name: weir-web-dist",
]) {
  requireText(validate, marker, `${RELEASE} validate job`);
}

// The amd64 candidate: built unpushed, started, audited end to end, evidence kept.
const candidate = requireJob(release, "docker-candidate", RELEASE);
requireOrder(
  candidate,
  [
    "- name: Build unpushed Docker release candidate",
    "platforms: linux/amd64",
    "push: false",
    "- name: Start unpushed Docker release candidate",
    "- name: Full live E2E against unpushed Docker release candidate",
    "- name: Upload Docker release-candidate evidence",
    "- name: Cleanup unpushed Docker release candidate",
  ],
  `${RELEASE} docker-candidate job`,
);
for (const marker of [
  "WEIR_LIVE_EXPECTED_VERSION: ${{ steps.version.outputs.plain }}",
  "WEIR_SESSION_COOKIE_SECURE=false",
  "WEIR_LIVE_E2E_FIXTURE_SERVER_ROOT: /e2e-fixture",
  "WEIR_LIVE_E2E_FIXTURE_HOST_ROOT:$WEIR_LIVE_E2E_FIXTURE_SERVER_ROOT",
  "name: weir-docker-release-candidate-audit",
]) {
  requireText(candidate, marker, `${RELEASE} docker-candidate job`);
}

// Both published architectures must build before registry credentials exist.
requireOrder(
  requireJob(release, "docker-arm64", RELEASE),
  [
    "uses: docker/setup-qemu-action@",
    "- name: Build unpushed Docker release candidate (linux/arm64)",
    "platforms: linux/arm64",
    "push: false",
  ],
  `${RELEASE} docker-arm64 job`,
);

// Checksums describe the files as published. Signing rewrites Setup.exe, so hashing must come after it.
requireOrder(
  requireJob(release, "windows-smoke", RELEASE),
  [
    "- name: Validate release version alignment",
    "- name: Sign Velopack release artifacts",
    "- name: Verify Velopack setup signature",
    "- name: Generate release artifact checksums",
    "- name: Upload Velopack release artifacts",
  ],
  `${RELEASE} windows-smoke job`,
);

// --- ci.yml -----------------------------------------------------------------------------------------

const ciDockerSmoke = requireJob(ci, "docker-smoke", CI);
requireOrder(
  ciDockerSmoke,
  [
    "- name: Build Weir Docker image",
    "- name: Start Weir Docker candidate",
    "- name: Full live E2E against Docker candidate",
    "- name: Upload Docker live-audit evidence",
    "- name: Cleanup Weir Docker smoke",
  ],
  `${CI} docker-smoke job`,
);
for (const marker of [
  "WEIR_SESSION_COOKIE_SECURE=false",
  "WEIR_LIVE_E2E_FIXTURE_SERVER_ROOT: /e2e-fixture",
  "WEIR_LIVE_E2E_FIXTURE_HOST_ROOT:$WEIR_LIVE_E2E_FIXTURE_SERVER_ROOT",
  "name: weir-docker-live-audit",
]) {
  requireText(ciDockerSmoke, marker, `${CI} docker-smoke job`);
}

// The contract suite runs one leg per required area, and `contract` fails unless every leg passed.
const contractArea = requireJob(ci, "contract-area", CI);
for (const marker of [
  "area: ${{ fromJSON(needs.changes.outputs.contract_areas) }}",
  "--contract-required-only --contract-area",
  "WEIR_CONTRACT_LEDGER: ${{ runner.temp }}/",
]) {
  requireText(contractArea, marker, `${CI} contract-area job`);
}
const contractVerdict = requireJob(ci, "contract", CI);
for (const marker of ["needs: [changes, contract-area]", "if: ${{ always() }}", "LEGS: ${{ needs.contract-area.result }}"]) {
  requireText(contractVerdict, marker, `${CI} contract job`);
}

// Every job and step the release gate asks CI for must still exist under that name.
const ciJobIds = jobIds(ci);
function ciJobBody(displayName) {
  const template = displayName.replaceAll("{area}", "${{ matrix.area }}");
  for (const id of ciJobIds) {
    const body = requireJob(ci, id, CI);
    const named = body.match(/^ {4}name: (.*)$/m);
    if ((named ? named[1] : id) === template) return body;
  }
  throw new Error(
    `${CI} has no job named "${template}", which scripts/verify-ci-for-release.mjs requires. Update one to match the other.`,
  );
}
for (const want of REQUIRED_EVIDENCE) {
  const body = ciJobBody(want.job);
  for (const step of want.steps) {
    requireText(body, `- name: ${step.replaceAll("{area}", "${{ matrix.area }}")}\n`, `${CI} job "${want.job}"`);
  }
}

console.log(
  "Every release check gates publish, only publish can publish, the Docker candidate's live E2E runs " +
    "unpushed, and ci.yml still names every job and step the release's CI gate relies on.",
);
