/**
 * Capture Pruner UI screenshots (Playwright + Chromium).
 *
 * Prerequisites (once, from repo root):
 *   cd scripts && npm install
 *   npx playwright install chromium
 *
 * Run (stack on http://127.0.0.1:8782 with operator login):
 *   node scripts/capture-pruner-screenshots.cjs
 *
 * Environment (optional):
 *   PRUNER_SCREENSHOT_BASE_URL   default http://127.0.0.1:8782
 *   PRUNER_SCREENSHOT_OUT        default <repo>/tmp/pruner-screenshots
 *   PRUNER_SCREENSHOT_USER       required
 *   PRUNER_SCREENSHOT_PASS       required
 */

const fs = require("fs");
const path = require("path");
const { createRequire } = require("module");

const repoRoot = path.resolve(__dirname, "..");
const baseUrl = process.env.PRUNER_SCREENSHOT_BASE_URL || "http://127.0.0.1:8782";
const outDir = process.env.PRUNER_SCREENSHOT_OUT || path.join(repoRoot, "tmp", "pruner-screenshots");
const screenshotUser = process.env.PRUNER_SCREENSHOT_USER;
const screenshotPass = process.env.PRUNER_SCREENSHOT_PASS;

if (!screenshotUser || !screenshotPass) {
  // eslint-disable-next-line no-console
  console.error("Set PRUNER_SCREENSHOT_USER and PRUNER_SCREENSHOT_PASS for the local account before capturing screenshots.");
  process.exit(1);
}

const requirePlaywright = createRequire(path.join(__dirname, "package.json"));
let chromium;
try {
  ({ chromium } = requirePlaywright("playwright"));
} catch {
  // eslint-disable-next-line no-console
  console.error(
    "Playwright is not installed. From the repo root run:\n  cd scripts && npm install && npx playwright install chromium\n",
  );
  process.exit(1);
}

async function ensureDir() {
  await fs.promises.mkdir(outDir, { recursive: true });
}

async function clearPngs() {
  const files = await fs.promises.readdir(outDir).catch(() => []);
  await Promise.all(
    files.filter((f) => f.endsWith(".png")).map((f) => fs.promises.unlink(path.join(outDir, f)).catch(() => {})),
  );
}

async function loginViaApi(page) {
  const csrfRes = await page.request.get(`${baseUrl}/api/v1/auth/csrf`);
  if (!csrfRes.ok()) throw new Error(`csrf failed ${csrfRes.status()}`);
  const csrf = await csrfRes.json();
  const loginRes = await page.request.post(`${baseUrl}/api/v1/auth/login`, {
    data: {
      username: screenshotUser,
      password: screenshotPass,
      csrf_token: csrf.csrf_token,
    },
    headers: {
      Origin: baseUrl,
      Referer: `${baseUrl}/login`,
    },
  });
  if (!loginRes.ok()) throw new Error(`login failed ${loginRes.status()} ${await loginRes.text()}`);
}

async function shot(page, file) {
  await page.waitForTimeout(700);
  await page.screenshot({ path: path.join(outDir, file), fullPage: true });
}

async function clickTopTab(page, label) {
  const nav = page.getByTestId("pruner-top-level-tabs");
  await nav.getByRole("tab", { name: label, exact: true }).click();
  await page.waitForTimeout(500);
}

async function clickProviderSub(page, provider, label) {
  const section = page.getByTestId(`pruner-provider-tab-${provider}`);
  await section.getByTestId(`pruner-provider-subnav-${provider}`).getByRole("button", { name: label }).click();
  await page.waitForTimeout(500);
}

(async () => {
  await ensureDir();
  await clearPngs();
  // eslint-disable-next-line no-console
  console.log("Writing Pruner screenshots to:", outDir);

  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } });

  await loginViaApi(page);
  await page.goto(`${baseUrl}/app/pruner`, { waitUntil: "domcontentloaded" });
  await page.getByTestId("pruner-top-level-tabs").waitFor({ timeout: 30000 });

  await shot(page, "01-overview.png");

  let n = 2;
  for (const provider of ["emby", "jellyfin", "plex"]) {
    const p = provider.charAt(0).toUpperCase() + provider.slice(1);
    await clickTopTab(page, p);
    await shot(page, `${String(n++).padStart(2, "0")}-${provider}-connection.png`);
    await clickProviderSub(page, provider, "Cleanup");
    await shot(page, `${String(n++).padStart(2, "0")}-${provider}-cleanup.png`);
    await clickProviderSub(page, provider, "Schedule");
    await shot(page, `${String(n++).padStart(2, "0")}-${provider}-schedule.png`);
  }

  await clickTopTab(page, "Jobs");
  await shot(page, `${String(n++).padStart(2, "0")}-jobs.png`);

  await browser.close();
  // eslint-disable-next-line no-console
  console.log("Done.");
})().catch((e) => {
  // eslint-disable-next-line no-console
  console.error(e);
  process.exit(1);
});
