/**
 * Full-page screenshots of each Subber top-level tab (current tab labels).
 *
 * Prerequisites: same as capture-overview-sections.cjs — Playwright in scripts/,
 *   running web+API (e.g. npm run dev from apps/web, default http://127.0.0.1:8782).
 *
 *   node scripts/capture-subber-tabs.cjs
 *
 * Env:
 *   SUBBER_SHOT_BASE_URL   default http://127.0.0.1:8782
 *   SUBBER_SHOT_OUT        default <repo>/tmp/subber-tabs
 *   SUBBER_SHOT_USER       required unless OVERVIEW_SHOT_USER is set
 *   SUBBER_SHOT_PASS       required unless OVERVIEW_SHOT_PASS is set
 */

const fs = require("fs");
const path = require("path");
const { createRequire } = require("module");

const repoRoot = path.resolve(__dirname, "..");
const baseUrl = (process.env.SUBBER_SHOT_BASE_URL || process.env.OVERVIEW_SHOT_BASE_URL || "http://127.0.0.1:8782").replace(/\/$/, "");
const outDir = process.env.SUBBER_SHOT_OUT || path.join(repoRoot, "tmp", "subber-tabs");

const requirePlaywright = createRequire(path.join(__dirname, "package.json"));
let chromium;
try {
  ({ chromium } = requirePlaywright("playwright"));
} catch {
  // eslint-disable-next-line no-console
  console.error("Playwright missing. Run:\n  cd scripts && npm install && npx playwright install chromium\n");
  process.exit(1);
}

async function loginViaApi(page) {
  const csrfRes = await page.request.get(`${baseUrl}/api/v1/auth/csrf`);
  if (!csrfRes.ok()) throw new Error(`csrf failed ${csrfRes.status()}`);
  const csrf = await csrfRes.json();
  const user = process.env.SUBBER_SHOT_USER || process.env.OVERVIEW_SHOT_USER;
  const pass = process.env.SUBBER_SHOT_PASS || process.env.OVERVIEW_SHOT_PASS;
  if (!user || !pass) {
    throw new Error("Set SUBBER_SHOT_USER/SUBBER_SHOT_PASS or OVERVIEW_SHOT_USER/OVERVIEW_SHOT_PASS before capturing screenshots.");
  }
  const loginRes = await page.request.post(`${baseUrl}/api/v1/auth/login`, {
    data: {
      username: user,
      password: pass,
      csrf_token: csrf.csrf_token,
    },
    headers: {
      Origin: baseUrl,
      Referer: `${baseUrl}/login`,
    },
  });
  if (!loginRes.ok()) throw new Error(`login failed ${loginRes.status()} ${await loginRes.text()}`);
}

const TAB_LABELS = ["Overview", "TV", "Movies", "Connections", "Providers", "Preferences", "Schedule", "Jobs"];

function slug(label) {
  return label.toLowerCase().replace(/\s+/g, "-");
}

(async () => {
  await fs.promises.mkdir(outDir, { recursive: true });
  // eslint-disable-next-line no-console
  console.log("Writing Subber tab PNGs to:", outDir);

  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });

  await loginViaApi(page);
  await page.goto(`${baseUrl}/app`, { waitUntil: "domcontentloaded" });
  await page.locator('[data-testid="shell-ready"]').waitFor({ timeout: 90000 });
  await page.goto(`${baseUrl}/app/subber`, { waitUntil: "domcontentloaded", timeout: 120000 });
  await page.locator('[data-testid="subber-scope-page"]').waitFor({ timeout: 60000 });

  for (const label of TAB_LABELS) {
    await page.getByRole("tab", { name: label }).click();
    await page.waitForTimeout(500);
    const filePath = path.join(outDir, `subber-${slug(label)}.png`);
    await page.screenshot({ path: filePath, fullPage: true });
    // eslint-disable-next-line no-console
    console.log("wrote", path.basename(filePath));
  }

  await browser.close();
  // eslint-disable-next-line no-console
  console.log("Done.");
})().catch((e) => {
  // eslint-disable-next-line no-console
  console.error(e);
  process.exit(1);
});
