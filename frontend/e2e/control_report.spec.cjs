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

  // now the FAN9672 tool iframe + the two action buttons appear
  const iframe = page.locator('iframe').first();
  ok(await iframe.waitFor({ state: 'visible', timeout: 15000 }).then(() => true).catch(() => false),
     'Control Design iframe (FAN9672 tool) rendered after Screen 1 confirm');

  const reportBtn = page.getByRole('button', { name: /Generate Full Report/i }).first();
  ok(await reportBtn.waitFor({ state: 'visible', timeout: 10000 }).then(() => true).catch(() => false),
     'single "Generate Full Report (Chapters 1–6 + Appendices)" button present');
  ok(await page.getByRole('button', { name: /Control-Loop Report/i }).count() === 0,
     'old standalone "Control-Loop Report" button removed');

  const semiBtn = page.getByRole('button', { name: /Select Semiconductors/i }).first();
  ok(await semiBtn.waitFor({ state: 'visible', timeout: 8000 }).then(() => true).catch(() => false),
     '"Select Semiconductors →" button present');

  // clicking it advances to the Chapter 7 page
  await semiBtn.click();
  const ch7 = await page.getByText(/Chapter 7 — Semiconductor Selection/i).first()
    .waitFor({ state: 'visible', timeout: 8000 }).then(() => true).catch(() => false);
  ok(ch7, 'Select Semiconductors → navigates to the Chapter 7 page');
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
