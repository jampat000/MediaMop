#!/usr/bin/env node
// Release gate: refuse to publish a tag unless `.github/workflows/ci.yml` already passed on the exact
// commit the tag points at.
//
// The release used to rebuild and re-run the server tests, the web tests and the whole contract suite
// on a commit main's CI had just tested. This replaces that second run with proof of the first. A CI
// run counts only when all of these hold:
//
// - it ran ci.yml for exactly this commit, as a `push` (to main) or a `workflow_dispatch` run. A
//   `pull_request` run is never accepted: its head_sha is the branch head, but what it tested was that
//   head merged into the base branch as it stood then, which is not this tree;
// - its latest attempt finished `success` (a run that failed and passed on re-run counts; a run that
//   passed and was then re-run into a failure does not);
// - every job and step in REQUIRED_EVIDENCE below concluded `success` in that latest attempt. `skipped`
//   is not enough: ci.yml's path filter skips work a push did not touch, and a skip proves nothing
//   about this tree. That is what separates "some run succeeded" from "the tests ran and passed".
//
// While a qualifying run could still appear (a CI run for this commit is queued or in progress, or the
// tag was pushed seconds after the merge and the run does not exist yet) the gate waits. When nothing
// can qualify it fails with the one command that fixes it: a manual ci.yml run on the tag, which runs
// every job whatever changed, followed by re-running the release's failed jobs.
//
// Usage (in release.yml): node scripts/verify-ci-for-release.mjs
//   env GITHUB_TOKEN (actions: read), GITHUB_REPOSITORY; commit defaults to `git rev-parse HEAD`.
// Diagnose one run by id, whatever its event:  node scripts/verify-ci-for-release.mjs --run-id <id>
// Options: --sha <sha> --wait-minutes <n> --appear-minutes <n> --poll-seconds <n>

import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");

export const CI_WORKFLOW = "ci.yml";
export const ACCEPTED_EVENTS = ["push", "workflow_dispatch"];

// What the release used to re-run itself, as ci.yml names it. `{area}` expands to every area
// tests/contract/areas.json requires on the .NET server. scripts/check-release-workflow-gates.mjs
// fails if ci.yml stops declaring any of these names, so a rename cannot silently disarm the gate.
export const REQUIRED_EVIDENCE = [
  {
    job: "weir",
    steps: [
      "Build Weir server (warnings are errors)",
      "Test Weir server",
      "Weir web - install, lint, format, build, unit tests",
      "Weir dead-code guard",
    ],
  },
  { job: "weir-server (windows-latest)", steps: ["Test Weir server"] },
  { job: "contract ({area})", steps: ["Contract suite, required area ({area})"], perArea: true },
  { job: "contract", steps: ["Every required contract area passed"] },
];

export function requiredContractAreas(areasJson) {
  const areas = (areasJson.areas || [])
    .filter((area) => (area.required || []).includes("dotnet"))
    .map((area) => area.name);
  if (areas.length === 0) {
    throw new Error("tests/contract/areas.json requires no area on dotnet; refusing to treat that as proof.");
  }
  return areas;
}

export function expandEvidence(areas) {
  const expanded = [];
  for (const entry of REQUIRED_EVIDENCE) {
    if (!entry.perArea) {
      expanded.push({ job: entry.job, steps: entry.steps });
      continue;
    }
    for (const area of areas) {
      expanded.push({
        job: entry.job.replaceAll("{area}", area),
        steps: entry.steps.map((step) => step.replaceAll("{area}", area)),
      });
    }
  }
  return expanded;
}

// Judges one completed run against the evidence. `jobs` must be the run's latest attempt
// (GET .../runs/{id}/jobs?filter=latest). Returns the reasons it does not qualify; empty means it does.
export function evaluateRun(run, jobs, evidence) {
  const problems = [];
  if (!ACCEPTED_EVENTS.includes(run.event)) {
    problems.push(`event is ${run.event}, and only ${ACCEPTED_EVENTS.join(" or ")} runs test this exact tree`);
  }
  if (run.status !== "completed") {
    problems.push(`still ${run.status}`);
    return problems;
  }
  if (run.conclusion !== "success") {
    problems.push(`attempt ${run.run_attempt} concluded ${run.conclusion}`);
  }
  for (const want of evidence) {
    const matches = jobs.filter((job) => job.name === want.job);
    if (matches.length !== 1) {
      problems.push(
        matches.length === 0 ? `job "${want.job}" is missing` : `job "${want.job}" appears ${matches.length} times`,
      );
      continue;
    }
    const [job] = matches;
    if (job.conclusion !== "success") {
      problems.push(`job "${want.job}" concluded ${job.conclusion}`);
      continue;
    }
    for (const stepName of want.steps) {
      const step = (job.steps || []).find((candidate) => candidate.name === stepName);
      if (!step) {
        problems.push(`job "${want.job}" has no step "${stepName}"`);
      } else if (step.conclusion !== "success") {
        problems.push(`job "${want.job}" step "${stepName}" concluded ${step.conclusion}`);
      }
    }
  }
  return problems;
}

function parseArgs(argv) {
  const options = { waitMinutes: 45, appearMinutes: 3, pollSeconds: 30 };
  for (let i = 0; i < argv.length; i += 1) {
    const flag = argv[i];
    const value = argv[i + 1];
    if (value === undefined) throw new Error(`${flag} needs a value`);
    i += 1;
    if (flag === "--sha") options.sha = value;
    else if (flag === "--run-id") options.runId = value;
    else if (flag === "--wait-minutes") options.waitMinutes = Number(value);
    else if (flag === "--appear-minutes") options.appearMinutes = Number(value);
    else if (flag === "--poll-seconds") options.pollSeconds = Number(value);
    else throw new Error(`Unknown option ${flag}`);
  }
  return options;
}

function createApi(repository, token) {
  return async function api(path) {
    const url = `https://api.github.com/repos/${repository}${path}`;
    // Transient failures (network, 5xx, 429) are retried; anything else (a bad token, a 404) is final.
    let lastError;
    for (let attempt = 1; attempt <= 4; attempt += 1) {
      let response;
      try {
        response = await fetch(url, {
          headers: {
            Accept: "application/vnd.github+json",
            Authorization: `Bearer ${token}`,
            "X-GitHub-Api-Version": "2022-11-28",
          },
        });
      } catch (error) {
        lastError = error;
      }
      if (response?.ok) return await response.json();
      if (response) {
        lastError = new Error(`GET ${path} returned ${response.status}: ${(await response.text()).slice(0, 300)}`);
        if (response.status < 500 && response.status !== 429) throw lastError;
      }
      await sleep(attempt * 5000);
    }
    throw lastError;
  };
}

async function latestJobs(api, runId) {
  const jobs = [];
  for (let page = 1; ; page += 1) {
    const body = await api(`/actions/runs/${runId}/jobs?filter=latest&per_page=100&page=${page}`);
    jobs.push(...body.jobs);
    if (body.jobs.length < 100) return jobs;
  }
}

function sleep(ms) {
  return new Promise((done) => setTimeout(done, ms));
}

function describe(run) {
  return `run ${run.id} (${run.event}, attempt ${run.run_attempt}, ${run.html_url})`;
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  const repository = process.env.GITHUB_REPOSITORY;
  const token = process.env.GITHUB_TOKEN;
  if (!repository || !token) throw new Error("GITHUB_REPOSITORY and GITHUB_TOKEN must be set.");
  const api = createApi(repository, token);
  const areas = requiredContractAreas(
    JSON.parse(readFileSync(resolve(repoRoot, "tests", "contract", "areas.json"), "utf8")),
  );
  const evidence = expandEvidence(areas);

  if (options.runId) {
    const run = await api(`/actions/runs/${options.runId}`);
    const problems = evaluateRun(run, await latestJobs(api, run.id), evidence);
    console.log(`${describe(run)} for ${run.head_sha}:`);
    for (const problem of problems) console.log(`  - ${problem}`);
    console.log(problems.length ? "Would NOT satisfy the release gate." : "Would satisfy the release gate.");
    process.exit(problems.length ? 1 : 0);
  }

  const sha = options.sha || execFileSync("git", ["rev-parse", "HEAD^{commit}"], { cwd: repoRoot, encoding: "utf8" }).trim();
  if (!/^[0-9a-f]{40}$/.test(sha)) throw new Error(`Not a full commit SHA: ${sha}`);
  const tag = process.env.GITHUB_REF_NAME || "<tag>";
  console.log(`Release gate: ${CI_WORKFLOW} must have passed on ${sha}.`);
  console.log(`Required contract areas (areas.json): ${areas.join(", ")}`);

  const started = Date.now();
  const verdicts = new Map(); // `${id}:${attempt}` -> problems, for completed runs only
  for (;;) {
    const body = await api(`/actions/workflows/${CI_WORKFLOW}/runs?head_sha=${sha}&per_page=100`);
    const runs = body.workflow_runs.filter(
      (run) => run.head_sha === sha && ACCEPTED_EVENTS.includes(run.event) && run.head_repository?.full_name === repository,
    );
    const ignored = body.workflow_runs.length - runs.length;

    for (const run of runs.filter((candidate) => candidate.status === "completed")) {
      const key = `${run.id}:${run.run_attempt}`;
      if (!verdicts.has(key)) verdicts.set(key, { run, problems: evaluateRun(run, await latestJobs(api, run.id), evidence) });
      if (verdicts.get(key).problems.length === 0) {
        console.log(`PASS: ${describe(run)} ran and passed every required job on ${sha}.`);
        return;
      }
    }

    const elapsedMinutes = (Date.now() - started) / 60000;
    const pending = runs.filter((run) => run.status !== "completed");
    const waitingForFirstRun = runs.length === 0 && elapsedMinutes < options.appearMinutes;
    if ((pending.length > 0 && elapsedMinutes < options.waitMinutes) || waitingForFirstRun) {
      const what = pending.length
        ? pending.map((run) => `${describe(run)} is ${run.status}`).join("; ")
        : `no ${CI_WORKFLOW} run for this commit yet`;
      console.log(`[${elapsedMinutes.toFixed(1)} min] waiting: ${what}`);
      await sleep(options.pollSeconds * 1000);
      continue;
    }

    console.error(`::error::No ${CI_WORKFLOW} run proves ${sha}. The release will not publish.`);
    if (pending.length > 0) {
      console.error(`Gave up after ${options.waitMinutes} minutes with CI still running: ${pending.map(describe).join("; ")}`);
    }
    if (runs.length === 0) {
      console.error(`No push or workflow_dispatch run of ${CI_WORKFLOW} exists for this commit${ignored ? ` (${ignored} pull_request run(s) ignored)` : ""}.`);
    }
    for (const { run, problems } of verdicts.values()) {
      console.error(`${describe(run)} does not qualify:`);
      for (const problem of problems) console.error(`  - ${problem}`);
    }
    console.error("To prove this commit, run the full CI on the tag (a manual run skips nothing), wait for it to pass,");
    console.error("then re-run this release's failed jobs:");
    console.error(`  gh workflow run ${CI_WORKFLOW} --repo ${repository} --ref ${tag}`);
    process.exit(1);
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  main().catch((error) => {
    console.error(`::error::${error.message}`);
    process.exit(1);
  });
}
