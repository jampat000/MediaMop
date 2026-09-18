// node --test scripts/verify-ci-for-release.test.mjs
// The release gate's judgement of a CI run, on hand-built runs. The polling loop is exercised against
// the real API instead (see the script's --run-id mode).
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { evaluateRun, expandEvidence, requiredContractAreas } from "./verify-ci-for-release.mjs";

const areas = ["auth", "processing"];
const evidence = expandEvidence(areas);

function passingJobs() {
  return evidence.map((want) => ({
    name: want.job,
    conclusion: "success",
    steps: want.steps.map((name) => ({ name, conclusion: "success" })),
  }));
}

const pushRun = { id: 1, event: "push", status: "completed", conclusion: "success", run_attempt: 1 };

test("a completed push run where every required job and step passed qualifies", () => {
  assert.deepEqual(evaluateRun(pushRun, passingJobs(), evidence), []);
});

test("a manual (workflow_dispatch) run qualifies too", () => {
  assert.deepEqual(evaluateRun({ ...pushRun, event: "workflow_dispatch" }, passingJobs(), evidence), []);
});

test("a pull_request run never qualifies: it tested a merge, not this commit", () => {
  const problems = evaluateRun({ ...pushRun, event: "pull_request" }, passingJobs(), evidence);
  assert.equal(problems.length, 1);
  assert.match(problems[0], /pull_request/);
});

test("a run that passed on its second attempt qualifies (latest attempt is what counts)", () => {
  assert.deepEqual(evaluateRun({ ...pushRun, run_attempt: 2 }, passingJobs(), evidence), []);
});

test("a failed, cancelled or unfinished run does not qualify", () => {
  assert.notDeepEqual(evaluateRun({ ...pushRun, conclusion: "failure" }, passingJobs(), evidence), []);
  assert.notDeepEqual(evaluateRun({ ...pushRun, conclusion: "cancelled" }, passingJobs(), evidence), []);
  assert.match(evaluateRun({ ...pushRun, status: "in_progress", conclusion: null }, passingJobs(), evidence)[0], /in_progress/);
});

test("a path-filtered skip is not proof: a skipped step or job fails the gate", () => {
  const skippedStep = passingJobs();
  skippedStep.find((job) => job.name === "weir").steps.find((step) => step.name === "Test Weir server").conclusion =
    "skipped";
  assert.match(evaluateRun(pushRun, skippedStep, evidence).join("\n"), /"Test Weir server" concluded skipped/);

  const skippedLeg = passingJobs().map((job) => (job.name === "contract (processing)" ? { ...job, conclusion: "skipped" } : job));
  assert.match(evaluateRun(pushRun, skippedLeg, evidence).join("\n"), /"contract \(processing\)" concluded skipped/);
});

test("every required area needs its own passing leg; the aggregate alone is not enough", () => {
  const missingLeg = passingJobs().filter((job) => job.name !== "contract (auth)");
  assert.match(evaluateRun(pushRun, missingLeg, evidence).join("\n"), /"contract \(auth\)" is missing/);
});

test("the required areas come from areas.json, and an empty list is refused", () => {
  const real = JSON.parse(readFileSync(new URL("../tests/contract/areas.json", import.meta.url), "utf8"));
  const expected = real.areas.filter((area) => (area.required || []).includes("dotnet")).map((area) => area.name);
  assert.ok(expected.length > 0);
  assert.deepEqual(requiredContractAreas(real), expected);
  assert.throws(() => requiredContractAreas({ areas: [{ name: "auth", required: [] }] }));
});
