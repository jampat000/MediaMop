/**
 * Element screenshots for the three overview sections (At a glance, Needs attention, Next steps)
 * on Fetcher, Refiner, Subber, and Pruner — plus Refiner's "Next steps" card (data-testid refiner-overview-go-deeper).
 *
 * Prerequisites:
 *   cd scripts && npm install && npx playwright install chromium
 *
 * Requires a running web+API stack (cookies on same origin), e.g. `npm run dev` from apps/web
 * with default proxy to API (http://127.0.0.1:8782 in dev-ports.json).
 *
 *   node scripts/capture-overview-sections.cjs
 *
 * Env:
 *   OVERVIEW_SHOT_BASE_URL   default http://127.0.0.1:8782
 *   OVERVIEW_SHOT_OUT        default <repo>/tmp/overview-sections
 *   OVERVIEW_SHOT_USER       default admin
 *   OVERVIEW_SHOT_PASS       default password123
 */

const fs = require("fs");
const path = require("path");
const { createRequire } = require("module");

const repoRoot = path.resolve(__dirname, "..");
const baseUrl = (process.env.OVERVIEW_SHOT_BASE_URL || "http://127.0.0.1:8782").replace(/\/$/, "");
const outDir = process.env.OVERVIEW_SHOT_OUT || path.join(repoRoot, "tmp", "overview-sections");

const requirePlaywright = createRequire(path.join(__dirname, "package.json"));
let chromium;
try {
  ({ chromium } = requirePlaywright("playwright"));
} catch {
  // eslint-disable-next-line no-console
  console.error(
    "Playwright missing. Run:\n  cd scripts && npm install && npx playwright install chromium\n",
  );
  process.exit(1);
}

async function loginViaApi(page) {
  const csrfRes = await page.request.get(`${baseUrl}/api/v1/auth/csrf`);
  if (!csrfRes.ok()) throw new Error(`csrf failed ${csrfRes.status()}`);
  const csrf = await csrfRes.json();
  const loginRes = await page.request.post(`${baseUrl}/api/v1/auth/login`, {
    data: {
      username: process.env.OVERVIEW_SHOT_USER || "admin",
      password: process.env.OVERVIEW_SHOT_PASS || "password123",
      csrf_token: csrf.csrf_token,
    },
    headers: {
      Origin: baseUrl,
      Referer: `${baseUrl}/login`,
    },
  });
  if (!loginRes.ok()) throw new Error(`login failed ${loginRes.status()} ${await loginRes.text()}`);
}

async function shotLocator(locator, filePath) {
  await locator.waitFor({ state: "visible", timeout: 60000 });
  await locator.screenshot({ path: filePath });
}

(async () => {
  await fs.promises.mkdir(outDir, { recursive: true });
  // eslint-disable-next-line no-console
  console.log("Writing overview section PNGs to:", outDir);

  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });

  await loginViaApi(page);
  await page.goto(`${baseUrl}/app`, { waitUntil: "domcontentloaded" });
  await page.locator('[data-testid="shell-ready"]').waitFor({ timeout: 90000 });

  const modules = [
    {
      name: "fetcher",
      path: "/app/fetcher",
      sections: [
        { testId: "fetcher-overview-at-a-glance", file: "fetcher-at-a-glance.png" },
        { testId: "fetcher-overview-needs-attention", file: "fetcher-needs-attention.png" },
        { testId: "fetcher-overview-next-steps", file: "fetcher-next-steps.png" },
      ],
    },
    {
      name: "refiner",
      path: "/app/refiner",
      sections: [
        { testId: "refiner-overview-at-a-glance", file: "refiner-at-a-glance.png" },
        { testId: "refiner-overview-needs-attention", file: "refiner-needs-attention.png" },
        { testId: "refiner-overview-go-deeper", file: "refiner-next-steps.png" },
      ],
    },
    {
      name: "subber",
      path: "/app/subber",
      sections: [
        { testId: "subber-overview-at-a-glance", file: "subber-at-a-glance.png" },
        { testId: "subber-overview-needs-attention", file: "subber-needs-attention.png" },
        { testId: "subber-overview-next-steps", file: "subber-next-steps.png" },
      ],
    },
    {
      name: "pruner",
      path: "/app/pruner",
      sections: [
        { testId: "pruner-overview-at-a-glance", file: "pruner-at-a-glance.png" },
        { testId: "pruner-overview-needs-attention", file: "pruner-needs-attention.png" },
        { testId: "pruner-overview-next-steps", file: "pruner-next-steps.png" },
      ],
    },
  ];

  for (const mod of modules) {
    await page.goto(`${baseUrl}${mod.path}`, { waitUntil: "domcontentloaded", timeout: 120000 });
    await page.waitForTimeout(600);
    for (const { testId, file } of mod.sections) {
      const loc = page.locator(`[data-testid="${testId}"]`);
      await shotLocator(loc, path.join(outDir, file));
      // eslint-disable-next-line no-console
      console.log("wrote", file);
    }
  }

  await browser.close();
  // eslint-disable-next-line no-console
  console.log("Done.");
})().catch((e) => {
  // eslint-disable-next-line no-console
  console.error(e);
  process.exit(1);
});
