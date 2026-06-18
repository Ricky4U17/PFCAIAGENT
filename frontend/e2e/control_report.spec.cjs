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

async function testReportButton(browser) {
  console.log('\n=== Test B: real Control Design page + report button (live backend) ===');
  const ctx = await browser.newContext({ acceptDownloads: true });
  await ctx.addInitScript(() => { window.__E2E_CONTROL__ = true; });
  const page = await ctx.newPage();
  const errs = [];
  page.on('console', m => { if (m.type() === 'error') errs.push(m.text()); });
  page.on('pageerror', e => errs.push(String(e)));
  await page.goto(APP, { waitUntil: 'load' });

  // the real ControlDesign component renders the FAN9672 tool iframe + the button
  const iframe = page.locator('iframe').first();
  ok(await iframe.waitFor({ state: 'visible', timeout: 15000 }).then(() => true).catch(() => false),
     'Control Design iframe (FAN9672 tool) rendered');

  const btn = page.getByRole('button', { name: /Control-Loop Report/i }).first();
  ok(await btn.waitFor({ state: 'visible', timeout: 10000 }).then(() => true).catch(() => false),
     'Control-Loop Report button present');

  const dl = page.waitForEvent('download', { timeout: 90000 });
  await btn.click();
  const download = await dl;
  const path = await download.path();
  const buf = fs.readFileSync(path);
  const magic = buf.slice(0, 5).toString('latin1');
  ok(download.suggestedFilename().endsWith('.pdf'), 'download filename is a .pdf: ' + download.suggestedFilename());
  ok(magic === '%PDF-', 'downloaded file is a real PDF (magic ' + JSON.stringify(magic) + ')');
  ok(buf.length > 500000, 'PDF is substantial (' + buf.length + ' bytes)');
  const errText = await page.getByText(/Control report failed/i).count();
  ok(errText === 0, 'no "Control report failed" banner');
  ok(errs.length === 0, 'no console/page errors' + (errs.length ? ': ' + errs.slice(0,2).join(' | ') : ''));
  await ctx.close();
}

(async () => {
  const browser = await chromium.launch();
  try { await testWorkflow(browser); } catch (e) { ok(false, 'Test A threw: ' + e.message); }
  try { await testReportButton(browser); } catch (e) { ok(false, 'Test B threw: ' + e.message); }
  await browser.close();
  console.log('\n' + (failures === 0 ? 'ALL CHECKS PASSED' : failures + ' CHECK(S) FAILED'));
  process.exit(failures === 0 ? 0 : 1);
})();
