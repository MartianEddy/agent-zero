// Browser end-to-end check: real Chrome, a production build of the web app, and the real
// local API with its database. Only one scenario stubs the AI step (claim review), because
// that needs a working model key; every other request reaches the real backend.
//
// Prerequisites: the API on http://127.0.0.1:18000 and `npm run build` in frontend/.
// Run:  cd e2e && npm run web            (CHROME_PATH overrides /usr/bin/google-chrome)

import { spawn } from "node:child_process";
import { setTimeout as sleep } from "node:timers/promises";
import puppeteer from "puppeteer-core";

const WEB_PORT = 3200;
const BASE = `http://127.0.0.1:${WEB_PORT}`;
const API = process.env.AGENT_ZERO_API_URL ?? "http://127.0.0.1:18000";
const results = [];
const check = (name, ok, detail = "") => results.push({ name, ok: Boolean(ok), detail });
// Next.js links navigate on the client, so wait for the URL rather than a page load.
const clickAndWaitForPath = async (page, selector, path) => {
  await page.click(selector);
  return page.waitForFunction((p) => location.pathname === p, { timeout: 15000 }, path).then(() => true, () => false);
};

async function waitFor(url, tries = 60) {
  for (let i = 0; i < tries; i += 1) {
    try { if ((await fetch(url)).ok) return true; } catch { /* not up yet */ }
    await sleep(500);
  }
  return false;
}

const history = await (await fetch(`${API}/api/v1/investigations/history`)).json();
const finished = history.find((item) => item.finding_status);
if (!finished) throw new Error("The local database has no finished case to open.");

const web = spawn("node_modules/.bin/next", ["start", "-p", String(WEB_PORT), "-H", "127.0.0.1"], {
  cwd: new URL("../frontend/", import.meta.url).pathname,
  env: { ...process.env, AGENT_ZERO_API_URL: API },
  stdio: "ignore",
});
const browser = await puppeteer.launch({
  executablePath: process.env.CHROME_PATH ?? "/usr/bin/google-chrome",
  headless: true,
  args: ["--no-sandbox", "--ignore-gpu-blocklist", "--enable-unsafe-swiftshader"],
});

try {
  await run();
} catch (error) {
  check("Run completed without crashing", false, String(error).slice(0, 200));
} finally {
  await browser.close();
  web.kill();
}

async function run() {
  check("Web app starts", await waitFor(`${BASE}/`));
  const page = await browser.newPage();
  const consoleErrors = [];
  const failedRequests = [];
  page.on("console", (message) => {
    if (message.type() === "error" && !/GPU stall|ReadPixels|Failed to load resource/.test(message.text())) consoleErrors.push(message.text());
  });
  page.on("pageerror", (error) => consoleErrors.push(`pageerror: ${error.message}`));
  page.on("response", (response) => {
    const url = response.url();
    if (url.startsWith(BASE) && response.status() >= 400 && !url.includes("/api/investigations/triage")) failedRequests.push(`${response.status()} ${url}`);
  });
  await page.setViewport({ width: 1280, height: 800 });

  // Public pages render with one heading and no broken images.
  for (const path of ["/", "/how-it-works", "/methodology", "/whatsapp", "/newsrooms", "/about", "/faq", "/privacy"]) {
    const response = await page.goto(`${BASE}${path}`, { waitUntil: "load" });
    const facts = await page.evaluate(() => ({
      h1: document.querySelectorAll("h1").length,
      imagesWithoutAlt: [...document.images].filter((img) => !img.hasAttribute("alt")).length,
      unnamedButtons: [...document.querySelectorAll("button")].filter((b) => !(b.textContent.trim() || b.getAttribute("aria-label"))).length,
    }));
    check(`${path} loads with one heading, alt text and named buttons`, response.ok() && facts.h1 === 1 && !facts.imagesWithoutAlt && !facts.unnamedButtons, JSON.stringify(facts));
  }

  await page.goto(`${BASE}/`, { waitUntil: "load" });
  await sleep(4000);
  const scene = await page.$eval("[data-scene]", (el) => el.getAttribute("data-scene")).catch(() => "missing");
  check("Home 3D scene mounts, or falls back cleanly", ["live", "static", "ready"].includes(scene), scene);
  check("Start a check opens the new-check page", await clickAndWaitForPath(page, 'header a[href="/investigate"]', "/investigate"));

  const redirect = await page.goto(`${BASE}/product`, { waitUntil: "load" });
  check("Old /product link redirects to How it works", redirect.status() < 400 && new URL(page.url()).pathname === "/how-it-works", `${redirect.status()} ${page.url()}`);
  await page.goto(`${BASE}/investigate?investigation=${finished.id}`, { waitUntil: "load" });
  check("Old case links redirect to the case permalink", new URL(page.url()).pathname === `/investigations/${finished.id}`, page.url());

  // Dashboard and cases read the real history.
  await page.goto(`${BASE}/dashboard`, { waitUntil: "load" });
  await page.waitForFunction(() => /\d/.test(document.querySelector("section[aria-label] p")?.textContent ?? ""), { timeout: 15000 }).catch(() => {});
  const checks = await page.$eval("section[aria-label] p", (el) => el.textContent).catch(() => "");
  check("Dashboard shows the real case count", Number(checks) === history.length, `${checks} vs ${history.length}`);

  await page.goto(`${BASE}/investigations`, { waitUntil: "load" });
  await page.waitForSelector('a[href^="/investigations/"]', { timeout: 15000 }).catch(() => {});
  const rows = await page.$$eval('a[href^="/investigations/"]', (links) => links.length);
  check("Cases list shows the real cases", rows === history.length, `${rows} rows`);
  await page.type("#case-search", finished.reference);
  const filtered = await page.$$eval('a[href^="/investigations/"]', (links) => links.length);
  check("Search narrows the list to the matching case", filtered === 1, `${filtered} rows`);
  await page.type("#case-reference", finished.reference);
  check("Open by reference goes to the case", await clickAndWaitForPath(page, 'form button[type="submit"]', `/investigations/${finished.id}`));

  // Case view renders the real saved result and its evidence.
  await page.waitForFunction(() => document.querySelector("h1")?.textContent.includes("What Agent 0 found"), { timeout: 20000 }).catch(() => {});
  const caseFacts = await page.evaluate(() => ({ h1: document.querySelector("h1")?.textContent, tabs: [...document.querySelectorAll('[role="tab"]')].map((t) => t.textContent) }));
  check("Case page shows the saved result with tabs", caseFacts.h1?.includes("What Agent 0 found") && caseFacts.tabs.some((t) => t.startsWith("Evidence")), JSON.stringify(caseFacts));
  const evidenceTab = await page.$('[role="tab"]:nth-child(2)');
  if (evidenceTab) {
    await evidenceTab.click();
    await page.keyboard.press("Enter");
  }
  await sleep(600);
  const evidenceHeading = await page.evaluate(() => document.querySelector('[role="tabpanel"] h2')?.textContent ?? "");
  check("Evidence tab lists the sources", /Sources (reviewed|found)/.test(evidenceHeading), evidenceHeading);

  // Real API: claim review fails safely when the AI service rejects its key.
  await page.goto(`${BASE}/investigate`, { waitUntil: "load" });
  await page.type("textarea", "Nairobi is the capital of Kenya.");
  await page.click('button[type="submit"]');
  await page.waitForSelector('[role="alert"]', { timeout: 60000 }).catch(() => {});
  const alertText = await page.$eval('[role="alert"]', (el) => el.textContent).catch(() => "");
  check("Real API: claim review shows a plain error when the AI service is unavailable", alertText.length > 10 && !/Method Not Allowed|Internal Server Error/.test(alertText), alertText.slice(0, 120));

  // Stubbed AI step: review, edit and confirm, then land on a real case.
  const caseJson = await (await fetch(`${API}/api/v1/investigations/${finished.id}`)).json();
  await page.setRequestInterception(true);
  let confirmedClaims = null;
  const onRequest = (request) => {
    const url = request.url();
    if (url.endsWith("/api/investigations/triage")) {
      return request.respond({ status: 200, contentType: "application/json", body: JSON.stringify({ draft_id: "draft-e2e", claims: [{ text: "Nairobi is the capital of Kenya.", claim_type: "SETTLED_FACT", needs_deep_investigation: false }] }) });
    }
    if (url.endsWith("/api/investigations/draft-e2e/continue")) {
      confirmedClaims = JSON.parse(request.postData() ?? "{}").claims;
      return request.respond({ status: 202, contentType: "application/json", body: JSON.stringify(caseJson) });
    }
    return request.continue();
  };
  page.on("request", onRequest);
  await page.goto(`${BASE}/investigate?q=${encodeURIComponent("Nairobi is the capital of Kenya.")}`, { waitUntil: "load" });
  await sleep(300);
  const prefilled = await page.$eval("textarea", (el) => el.value);
  check("Overview hand-off pre-fills the claim", prefilled === "Nairobi is the capital of Kenya.");
  await page.click('button[type="submit"]');
  await page.waitForSelector("#claim-0", { timeout: 10000 }).catch(() => {});
  check("Review step shows the proposed claim", Boolean(await page.$("#claim-0")));
  await page.click("#claim-0", { clickCount: 3 });
  await page.type("#claim-0", "Nairobi has been Kenya's capital since 1963.");
  const confirm = await page.$$("button");
  for (const button of confirm) {
    if ((await button.evaluate((b) => b.textContent)).includes("Confirm and start checking")) {
      await button.click();
      await page.waitForFunction((p) => location.pathname === p, { timeout: 15000 }, `/investigations/${finished.id}`).catch(() => {});
      break;
    }
  }
  check("Edited claim is the one sent for checking", confirmedClaims?.[0]?.text === "Nairobi has been Kenya's capital since 1963.", JSON.stringify(confirmedClaims));
  check("Confirming opens the case permalink", page.url().endsWith(`/investigations/${finished.id}`));
  page.off("request", onRequest);
  await page.setRequestInterception(false);

  // Mobile layout.
  await page.setViewport({ width: 390, height: 844, isMobile: true, hasTouch: true });
  for (const path of ["/", "/dashboard", `/investigations/${finished.id}`]) {
    await page.goto(`${BASE}${path}`, { waitUntil: "load" });
    await sleep(800);
    const fit = await page.evaluate(() => ({ overflow: document.documentElement.scrollWidth - window.innerWidth }));
    check(`Mobile ${path} has no sideways scrolling`, fit.overflow <= 1, `${fit.overflow}px`);
  }
  await page.goto(`${BASE}/dashboard`, { waitUntil: "load" });
  const tabs = await page.$$eval('nav[aria-label="Workspace tabs"] a', (links) => links.filter((l) => l.offsetParent !== null).length);
  check("Mobile workspace shows the bottom tab bar", tabs === 4, `${tabs} tabs`);

  check("No console errors on any page", consoleErrors.length === 0, consoleErrors.slice(0, 3).join(" | "));
  check("No failed requests besides the expected claim-review error", failedRequests.length === 0, failedRequests.slice(0, 3).join(" | "));
}

const width = Math.max(...results.map((r) => r.name.length));
for (const r of results) console.log(`${r.ok ? "PASS" : "FAIL"}  ${r.name.padEnd(width)}  ${r.ok ? "" : r.detail}`);
const failed = results.filter((r) => !r.ok).length;
console.log(`\n${results.length - failed}/${results.length} checks passed`);
process.exit(failed ? 1 : 0);
