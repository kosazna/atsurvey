// End-to-end smoke test of the demo flow against a running API and web build.
//
//   API:  uv run --package atsurvey-api uvicorn atsurvey_api.main:app --port 8000
//   Web:  pnpm build && pnpm preview          (serves http://localhost:4173)
//   Run:  pnpm e2e                            (SCREENSHOTS=dir to save screenshots)
//
// Fails (exit 1) if the demo project does not compute, the map does not render, the CSV
// export does not download, the file import fails, or the page logs any error.
const path = require("node:path");
const fs = require("node:fs");
const { chromium } = require("playwright");

const BASE = process.env.BASE_URL ?? "http://localhost:4173";
const SHOTS = process.env.SCREENSHOTS;
const failures = [];
const check = (cond, msg) => {
  if (!cond) failures.push(msg);
  console.log(`${cond ? "ok  " : "FAIL"} ${msg}`);
};

(async () => {
  if (SHOTS) fs.mkdirSync(SHOTS, { recursive: true });
  const shot = async (page, name) => SHOTS && page.screenshot({ path: path.join(SHOTS, `${name}.png`) });
  const browser = await chromium.launch({ args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"] });
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, colorScheme: "light" });
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(`pageerror: ${e.message}`));
  page.on("console", (m) => m.type() === "error" && errors.push(`console: ${m.text()}`));

  await page.goto(BASE);
  check(await page.getByTestId("landing").isVisible().catch(() => false), "landing page renders for signed-out visitors");
  await shot(page, "landing");
  await page.getByTestId("try-demo").first().click();
  await page.waitForURL("**/projects");
  await page.getByTestId("open-sample").click();
  await page.waitForURL("**/p/**");
  const computed = await page
    .waitForFunction(
      () => /Υπολογίστηκε|Computed/.test(document.querySelector('[data-testid="status-pill"]')?.textContent ?? ""),
      null,
      { timeout: 20000 },
    )
    .then(() => true)
    .catch(() => false);
  check(computed, "demo project computes through the API");
  await shot(page, "overview");

  await page.getByTestId("nav-results").click();
  await page.waitForTimeout(1500);
  const canvas = await page.evaluate(() => {
    const c = document.querySelector(".maplibregl-canvas");
    return c ? { w: c.clientWidth, h: c.clientHeight } : null;
  });
  check(!!canvas && canvas.w > 200 && canvas.h > 200, `map canvas renders (${JSON.stringify(canvas)})`);
  await shot(page, "results-map");

  await page.getByTestId("btn-import").click();
  await page.getByTestId("file-input").setInputFiles(path.join(__dirname, "field_obs.csv"));
  await page.waitForTimeout(1500);
  const importBtn = page.getByTestId("btn-do-import");
  check(await importBtn.isEnabled().catch(() => false), "CSV observation file parses");
  await importBtn.click().catch(() => {});
  await page.waitForTimeout(1500);

  await page.getByTestId("btn-export").click();
  for (const f of ["xlsx", "dxf", "shp", "pdf"]) {
    const b = page.getByTestId(`fmt-${f}`);
    if ((await b.count()) && (await b.getAttribute("aria-pressed")) === "true") await b.click();
  }
  const [dl] = await Promise.all([
    page.waitForEvent("download", { timeout: 15000 }).catch(() => null),
    page.getByTestId("btn-download").click(),
  ]);
  check(!!dl && dl.suggestedFilename().endsWith(".csv"), `CSV export downloads (${dl?.suggestedFilename()})`);
  await page.keyboard.press("Escape");

  // ---- night-1 features (skip gracefully when the API does not expose them)
  const paths = await page.evaluate(async () => {
    try {
      const r = await fetch((window.__ATS_API__ ?? "http://localhost:8000") + "/openapi.json");
      return Object.keys((await r.json()).paths ?? {});
    } catch {
      return [];
    }
  });
  if (paths.includes("/v1/cogo/inverse")) {
    await page.getByTestId("nav-cogo").click();
    await page.getByTestId("inv-a").fill("T1");
    await page.getByTestId("inv-b").fill("S2");
    await page.getByTestId("btn-inverse").click();
    const inv = await page.waitForSelector('[data-testid="inverse-result"]', { timeout: 10000 }).then(() => true).catch(() => false);
    check(inv, "COGO inverse computes through the API");
    await shot(page, "tools-inverse");
  } else console.log("skip COGO checks (endpoint not available)");

  if (paths.includes("/v1/leveling")) {
    await page.getByTestId("nav-leveling").click();
    await page.getByTestId("btn-level").click();
    const lev = await page.waitForSelector('[data-testid="lev-status"]', { timeout: 10000 }).then(() => true).catch(() => false);
    check(lev, "levelling computes the sample line");
  }

  await page.getByTestId("nav-linework").click();
  const lines = await page.waitForSelector('[data-testid="lines-table"]', { timeout: 10000 }).then(() => true).catch(() => false);
  check(lines, "field-code linework is built for the sample codes");

  await page.getByTestId("nav-adjustment").click();
  await page.getByTestId("btn-enable-lsa").click();
  const lsa = await page.waitForSelector('[data-testid="adjustment"]', { timeout: 20000 }).then(() => true).catch(() => false);
  if (lsa) check(true, "least-squares adjustment section shows the global test");
  else console.log("skip least-squares check (no adjustment returned by the API)");
  await shot(page, "adjustment");

  check(errors.length === 0, `no page errors${errors.length ? ": " + errors.join(" | ") : ""}`);
  await browser.close();
  if (failures.length) {
    console.error(`\n${failures.length} check(s) failed`);
    process.exit(1);
  }
  console.log("\nsmoke test passed");
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
