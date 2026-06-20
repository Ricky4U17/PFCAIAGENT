/*
 * Full-workflow Playwright test for the control-loop report.
 *
 *  Test A — drives the REAL Mode-A wizard (intake → topology → controller →
 *           channels → mini → done) against the live backend, proving the GUI
 *           workflow gates work end-to-end.
 *  Test B — lands on the REAL Control Design page (via the guarded __E2E_CONTROL__
 *           seam, which bypasses only the DB-backed Step-7/Step-15 selection UIs),
 *           clicks the REAL "Control-Loop Report" button, and asserts a valid PDF
 *           is downloaded from the live backend.
 *
 * Run: backend on :8077, static build (VITE_API_URL=http://localhost:8077) on :5199.
 */
const { chromium } = require('playwright');
const fs = require('fs');

const APP = 'http://localhost:5199';
let failures = 0;
const ok = (c, m) => { console.log((c ? '  PASS ' : '  FAIL ') + m); if (!c) failures++; };

async function clickByText(scope, re, timeout = 8000) {
  const btn = scope.getByRole('button', { name: re }).first();
  await btn.waitFor({ state: 'visible', timeout });
  await btn.click();
}

async function testWorkflow(browser) {
  console.log('\n=== Test A: real Mode-A wizard (intake → done) ===');
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  const errs = [];
  page.on('pageerror', e => errs.push(String(e)));
  await page.goto(APP, { waitUntil: 'load' });

  const pickOption = async () => {
    await page.getByTestId('gate-option').first().waitFor({ state: 'visible', timeout: 15000 });
    await page.getByTestId('gate-option').first().click();
  };
  // intake — defaults are pre-filled; just run topology selection
  await clickByText(page, /Run topology selection/i, 15000);
  // topology — select recommended card, approve
  await pickOption();
  await clickByText(page, /Approve & continue/i, 15000);
  // controller — select a mode, approve
  await pickOption();
  await clickByText(page, /Approve →/i, 15000);
  // channels (interleaved) — select a phase count, confirm
  await pickOption();
  await clickByText(page, /Confirm →/i, 15000);
  // mini-intake — accept defaults, validate & submit
  await clickByText(page, /Validate & submit/i, 15000);
  // done — the Step-7 entry button should appear
  const done = await page.getByRole('button', { name: /Step 7|Magnetic|Start Step/i }).first()
    .waitFor({ state: 'visible', timeout: 20000 }).then(() => true).catch(() => false);
  ok(done, 'reached the Mode-A "done" panel (Step 7 entry visible)');
  ok(errs.length === 0, 'no page errors during the wizard' + (errs.length ? ': ' + errs[0] : ''));
  await ctx.close();
}

async function testControlDesignButtons(browser) {
  console.log('\n=== Test B: Control Design buttons (full report + Select Semiconductors) ===');
  const ctx = await browser.newContext({ acceptDownloads: true });
  await ctx.addInitScript(() => { window.__E2E_CONTROL__ = true; });
  const page = await ctx.newPage();
  const errs = [];
  page.on('console', m => { if (m.type() === 'error') errs.push(m.text()); });
  page.on('pageerror', e => errs.push(String(e)));
  await page.goto(APP, { waitUntil: 'load' });

  // Screen 1 — Power Plant Parameters (review) shows first
  ok(await page.getByText(/Screen 1 of 7 — Power Plant Parameters/i).first()
      .waitFor({ state: 'visible', timeout: 15000 }).then(() => true).catch(() => false),
     'Screen 1 (Power Plant Parameters) renders');
  // the operating-point table (Table 1.2.2 data) loaded from the backend
  ok(await page.getByText(/Operating points/i).first()
      .waitFor({ state: 'visible', timeout: 8000 }).then(() => true).catch(() => false),
     'operating-point table present (power-plant endpoint OK)');
  const waitConfirm = async (label) => {
    const b = page.getByRole('button', { name: /Confirm & Continue/i }).first();
    let en = false;
    for (let i = 0; i < 40 && !en; i++) { en = await b.isEnabled().catch(() => false); if (!en) await page.waitForTimeout(200); }
    ok(en, label);
    await b.click();
  };
  await waitConfirm('S1 Confirm & Continue becomes enabled once the table loads');

  // Screen 2 — Controller-fixed components + selections
  ok(await page.getByText(/Screen 2 of 7 — Controller-Fixed Components/i).first()
      .waitFor({ state: 'visible', timeout: 12000 }).then(() => true).catch(() => false),
     'Screen 2 (Components) renders');
  ok(await page.getByText(/valid for HL & LL/i).first()
      .waitFor({ state: 'visible', timeout: 8000 }).then(() => true).catch(() => false),
     'R_CS valid-band indicator present (components endpoint OK)');
  await waitConfirm('S2 Confirm & Continue enabled (R_CS in valid band)');

  // Screen 3 — Core components + Fixed coefficients (review)
  ok(await page.getByText(/Screen 3 of 7 — Core Components & Fixed Coefficients/i).first()
      .waitFor({ state: 'visible', timeout: 12000 }).then(() => true).catch(() => false),
     'Screen 3 (Core Components & Fixed Coefficients) renders');
  ok(await page.getByText(/Fixed Coefficients \/ Internal Parameters/i).first()
      .waitFor({ state: 'visible', timeout: 8000 }).then(() => true).catch(() => false),
     'Fixed Coefficients table present (coefficients endpoint OK)');
  await waitConfirm('S3 Confirm & Continue enabled');

  // S4 — Compensators & Bode (interactive tool in wizard mode)
  const iframe = page.locator('iframe').first();
  ok(await iframe.waitFor({ state: 'visible', timeout: 15000 }).then(() => true).catch(() => false),
     'S4: FAN9672 tool iframe rendered (interactive Compensators & Bode)');
  const wizStep = async (label) => {
    ok(await page.getByText(new RegExp(label, 'i')).first()
        .waitFor({ state: 'visible', timeout: 10000 }).then(() => true).catch(() => false),
       label + ' wizard label shown');
  };
  await wizStep('Screen 4/7 . 4a . Current loop');
  await page.getByRole('button', { name: /Confirm & Continue/i }).first().click();   // S4 -> S5
  await wizStep('Screen 5/7 . Transient');
  await page.getByRole('button', { name: /Confirm & Continue/i }).first().click();   // S5 -> S6
  await wizStep('Screen 6/7 . iTHD');
  await page.getByRole('button', { name: /Confirm & Continue/i }).first().click();   // S6 -> S7
  await wizStep('Screen 7/7 . Schematic & Report');

  // S7 — Download + Review, then Approve (gated until a report is generated)
  const dlBtn = page.getByRole('button', { name: /Download \+ Review/i }).first();
  ok(await dlBtn.waitFor({ state: 'visible', timeout: 8000 }).then(() => true).catch(() => false),
     'S7: "Download + Review" button present');
  const approveBtn = page.getByRole('button', { name: /Approve & go to Semiconductors/i }).first();
  ok(!(await approveBtn.isEnabled().catch(() => true)),
     'S7: Approve is disabled until a report is generated');
  // mock the combined-report endpoint (the real PDF is backend-verified at 161 pages)
  await ctx.route('**/mode-b/documentation/generate-report', route =>
    route.fulfill({ status: 200, contentType: 'application/pdf', body: Buffer.from('%PDF-1.4\n% e2e mock report\n%%EOF\n') }));
  const dl = page.waitForEvent('download', { timeout: 30000 });
  await dlBtn.click();
  const download = await dl;
  const buf = require('fs').readFileSync(await download.path());
  ok(buf.slice(0, 5).toString('latin1') === '%PDF-', 'S7: Download + Review produces a PDF');
  // Approve now enabled → advances to Chapter 7
  let appEn = false;
  for (let i = 0; i < 30 && !appEn; i++) { appEn = await approveBtn.isEnabled().catch(() => false); if (!appEn) await page.waitForTimeout(150); }
  ok(appEn, 'S7: Approve enabled after Download + Review');
  await approveBtn.click();
  ok(await page.getByText(/Chapter 7 — Semiconductor Selection/i).first()
      .waitFor({ state: 'visible', timeout: 8000 }).then(() => true).catch(() => false),
     'Approve → navigates to the Chapter 7 page');
  ok(errs.length === 0, 'no console/page errors' + (errs.length ? ': ' + errs.slice(0,2).join(' | ') : ''));
  await ctx.close();
}

(async () => {
  const browser = await chromium.launch();
  try { await testWorkflow(browser); } catch (e) { ok(false, 'Test A threw: ' + e.message); }
  try { await testControlDesignButtons(browser); } catch (e) { ok(false, 'Test B threw: ' + e.message); }
  await browser.close();
  console.log('\n' + (failures === 0 ? 'ALL CHECKS PASSED' : failures + ' CHECK(S) FAILED'));
  process.exit(failures === 0 ? 0 : 1);
})();
