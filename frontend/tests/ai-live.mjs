import assert from 'node:assert/strict';
import { readFile, writeFile } from 'node:fs/promises';
import { randomUUID } from 'node:crypto';
import path from 'node:path';
import { browser, base, root } from './helpers.mjs';

const instance = await browser(), context = await instance.newContext({ viewport: { width: 1440, height: 1000 } });
const page = await context.newPage(), marker = 'section-5-browser-' + randomUUID();
const checks = [], errors = [], external = [];
let createdId, generated;
page.on('pageerror', error => errors.push(error.message));
page.on('request', request => { if (request.url().startsWith('http') && new URL(request.url()).origin !== base) external.push(request.url()); });
try {
  const baseline = await (await context.request.get(base + '/api/system/database')).json();
  const aiBaseline = await (await context.request.get(base + '/api/ai/status')).json();
  assert.equal(aiBaseline.status, 'ready');
  const old = JSON.parse(await readFile(path.join(root, 'examples/orders-v1.json'), 'utf8'));
  const next = JSON.parse(await readFile(path.join(root, 'examples/orders-v2-breaking.json'), 'utf8'));
  old.info.title = marker; next.info.title = marker;
  await page.goto(base);
  await page.getByText('History ready', { exact: true }).waitFor();
  await page.getByLabel('Old specification', { exact: true }).setInputFiles({ name: 'old.json', mimeType: 'application/json', buffer: Buffer.from(JSON.stringify(old)) });
  await page.getByLabel('New specification', { exact: true }).setInputFiles({ name: 'new.json', mimeType: 'application/json', buffer: Buffer.from(JSON.stringify(next)) });
  const saved = page.waitForResponse(r => new URL(r.url()).pathname === '/api/comparisons' && r.request().method() === 'POST');
  await page.getByRole('button', { name: 'Compare specifications', exact: true }).click();
  const snapshot = await (await saved).json();
  assert.equal(snapshot.old.title, marker); createdId = snapshot.id;
  await page.locator('.report-title').waitFor();
  assert.equal(await page.locator('.finding-row').count(), 3);
  const originalExport = await (await context.request.get(base + '/api/comparisons/' + createdId + '/export')).text();
  await page.getByRole('button', { name: 'Explain finding', exact: true }).waitFor();
  assert.equal(await page.getByRole('button', { name: 'Explain finding', exact: true }).isDisabled(), true);
  assert.equal((await (await context.request.get(base + '/api/ai/status')).json()).calls_this_process_today, aiBaseline.calls_this_process_today);
  checks.push('saving and viewing findings makes zero automatic AI calls; explicit consent is required');
  await page.getByRole('checkbox', { name: /Send this finding/ }).check();
  const generation = page.waitForResponse(r => new URL(r.url()).pathname.endsWith('/explanations'));
  await page.getByRole('button', { name: 'Explain finding', exact: true }).click();
  const response = await generation;
  generated = await response.json();
  assert.equal(response.status(), 200, JSON.stringify(generated));
  assert.equal(generated.cached, false); assert.equal(generated.provenance.attempts, 1);
  await page.locator('.ai-content').waitFor();
  assert.match(await page.locator('.ai-provenance').innerText(), /openai\/gpt-oss-120b/);
  assert.equal(generated.finding_id, snapshot.result.comparison.findings[0].id);
  checks.push('real browser -> FastAPI -> LangChain -> Groq returns an explanation bound to the selected finding');
  assert.equal((await (await context.request.get(base + '/api/ai/status')).json()).calls_this_process_today, aiBaseline.calls_this_process_today + 1);
  const current = await (await context.request.get(base + '/api/comparisons/' + createdId)).json();
  assert.deepEqual(current.result, snapshot.result);
  assert.equal(await (await context.request.get(base + '/api/comparisons/' + createdId + '/export')).text(), originalExport);
  checks.push('one provider attempt; saved findings, severity, coverage, and exports remain identical');
  await page.locator('.ai-panel').scrollIntoViewIfNeeded();
  await page.screenshot({ path: path.join(root, 'docs/section-5-guidance.png') });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole('tab', { name: 'Evidence', exact: true }).click();
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
  await page.locator('.ai-panel').screenshot({ path: path.join(root, 'docs/section-5-mobile.png') });
  checks.push('real AI guidance renders on desktop and mobile without horizontal overflow');
  await page.reload();
  await page.locator('.report-title').waitFor();
  await page.getByRole('tab', { name: /Findings/ }).click();
  await page.locator('.finding-row').first().click();
  await page.getByRole('checkbox', { name: /Send this finding/ }).check();
  const reused = page.waitForResponse(r => new URL(r.url()).pathname.endsWith('/explanations'));
  await page.getByRole('button', { name: 'Explain finding', exact: true }).click();
  const cacheResponse = await (await reused).json();
  assert.equal(cacheResponse.cached, true); assert.deepEqual(cacheResponse.content, generated.content);
  assert.equal((await (await context.request.get(base + '/api/ai/status')).json()).calls_this_process_today, aiBaseline.calls_this_process_today + 1);
  checks.push('reopened saved review reuses the backend cache without a second provider request');
  const removed = await context.request.delete(base + '/api/comparisons/' + createdId);
  assert.equal(removed.status(), 204);
  assert.equal((await context.request.post(base + '/api/comparisons/' + createdId + '/explanations', { data: { finding_id: generated.finding_id, allow_external_processing: true } })).status(), 404);
  assert.equal((await (await context.request.get(base + '/api/system/database')).json()).saved_comparisons, baseline.saved_comparisons);
  assert.deepEqual(errors, []); assert.deepEqual(external, []);
  assert.deepEqual(await page.evaluate(() => [localStorage.length, sessionStorage.length]), [0, 0]);
  checks.push('deletion removes the test report and its accessible guidance; no private rows or browser data remain');
  await writeFile(path.join(root, 'docs/section-5-live.json'), JSON.stringify({ status: 'passed', mode: 'actual Chrome, FastAPI, SQLite, LangChain and Groq', checks, provider_requests: 1, generated, synthetic_examples_only: true, retained_test_rows: 0, preexisting_records_deleted: false, uncaught_errors: errors, external_page_requests: external }, null, 2) + '\n');
  console.log(JSON.stringify({ status: 'passed', checks: checks.length, provider_requests: 1, retained_test_rows: 0 }));
} finally {
  if (createdId) {
    const response = await context.request.get(base + '/api/comparisons/' + createdId);
    if (response.status() !== 404) {
      const record = await response.json();
      assert.equal(record.id, createdId); assert.equal(record.old.title, marker); assert.equal(record.new.title, marker);
      assert.equal((await context.request.delete(base + '/api/comparisons/' + createdId)).status(), 204);
    }
  }
  await context.close(); await instance.close();
}
