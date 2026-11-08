import assert from 'node:assert/strict';
import { readFile, writeFile, mkdtemp, unlink, rmdir } from 'node:fs/promises';
import { randomUUID } from 'node:crypto';
import os from 'node:os';
import path from 'node:path';
import { browser, base, root } from './helpers.mjs';

const instance = await browser();
const context = await instance.newContext({ viewport: { width: 1440, height: 1000 }, acceptDownloads: true });
const page = await context.newPage();
const marker = 'section-4-browser-' + randomUUID();
const created = new Set(), checks = [], errors = [], external = [];
const directory = await mkdtemp(path.join(os.tmpdir(), 'relay-browser-export-'));
const downloadedFiles = [];
let baseline;
page.on('pageerror', error => errors.push(error.message));
page.on('request', request => { if (request.url().startsWith('http') && new URL(request.url()).origin !== base) external.push(request.url()); });
try {
  const status = await context.request.get(base + '/api/system/database');
  assert.equal(status.status(), 200);
  baseline = (await status.json()).saved_comparisons;
  const old = JSON.parse(await readFile(path.join(root, 'examples/orders-v1.json'), 'utf8'));
  const next = JSON.parse(await readFile(path.join(root, 'examples/orders-v2-breaking.json'), 'utf8'));
  old.info.title = marker; next.info.title = marker;
  await page.goto(base);
  await page.getByText('History ready', { exact: true }).waitFor();
  await page.getByLabel('Old specification', { exact: true }).setInputFiles({ name: 'orders-v1.json', mimeType: 'application/json', buffer: Buffer.from(JSON.stringify(old)) });
  await page.getByLabel('New specification', { exact: true }).setInputFiles({ name: 'orders-v2-breaking.json', mimeType: 'application/json', buffer: Buffer.from(JSON.stringify(next)) });
  const saveResponse = page.waitForResponse(response => new URL(response.url()).pathname === '/api/comparisons' && response.request().method() === 'POST');
  await page.getByRole('button', { name: 'Compare specifications', exact: true }).click();
  const savedResponse = await saveResponse;
  const saved = await savedResponse.json();
  assert.equal(savedResponse.status(), 201);
  assert.equal(saved.old.title, marker); assert.equal(saved.reused, false); created.add(saved.id);
  await page.locator('.report-title').waitFor();
  assert.equal(await page.locator('.finding-row').count(), 3);
  checks.push('real browser upload, worker comparison, and saved three-finding report');

  const duplicateResponse = page.waitForResponse(response => new URL(response.url()).pathname === '/api/comparisons' && response.request().method() === 'POST');
  await page.getByRole('button', { name: 'Compare specifications', exact: true }).click();
  const duplicate = await duplicateResponse;
  assert.equal(duplicate.status(), 200);
  const reused = await duplicate.json();
  assert.equal(reused.id, saved.id); assert.equal(reused.reused, true);
  await page.locator('.report-title').waitFor();
  checks.push('duplicate comparison reuses its saved record');

  await page.locator('.finding-row').filter({ hasText: 'Property added to the required list' }).click();
  assert.match(await page.locator('.evidence-value.after pre').innerText(), /currency/);
  await page.getByLabel('Search findings', { exact: true }).fill('schema_type_changed');
  assert.equal(await page.locator('.finding-row').count(), 1);
  await page.getByLabel('Search findings', { exact: true }).fill('');
  checks.push('real source evidence and interactive finding search');

  for (const [label, extension] of [['Export JSON', 'json'], ['Export Markdown', 'md']]) {
    const promise = page.waitForEvent('download');
    await page.getByRole('button', { name: label, exact: true }).click();
    const download = await promise;
    assert.equal(download.suggestedFilename(), 'comparison-' + saved.id + '.' + extension);
    const destination = path.join(directory, 'report.' + extension); downloadedFiles.push(destination);
    await download.saveAs(destination);
    const content = await readFile(destination, 'utf8');
    if (extension === 'json') assert.deepEqual(JSON.parse(content).result, saved.result);
    else {
      const blocks = [...content.matchAll(/```json\n(.*?)\n```/gs)].map(match => JSON.parse(match[1]));
      assert.deepEqual(blocks.slice(4), saved.result.comparison.findings);
    }
  }
  checks.push('both actual browser downloads preserve stored report evidence');

  await page.reload();
  await page.locator('.report-title').waitFor();
  assert.match(await page.locator('.report-title h3').innerText(), new RegExp(marker));
  assert.equal(await page.locator('.finding-row').count(), 3);
  assert.equal(new URL(page.url()).hash, '#review=' + saved.id);
  checks.push('reload reopens the bookmarked saved snapshot');

  await page.getByRole('button', { name: 'Delete current review', exact: true }).click();
  await page.getByRole('dialog').waitFor();
  await page.getByRole('button', { name: 'Cancel', exact: true }).click();
  assert.equal((await context.request.get(base + '/api/comparisons/' + saved.id)).status(), 200);
  await page.getByRole('button', { name: 'Delete current review', exact: true }).click();
  await page.getByRole('dialog').getByRole('button', { name: 'Delete review', exact: true }).click();
  await page.getByText('Saved comparison deleted.', { exact: true }).waitFor();
  assert.equal((await context.request.get(base + '/api/comparisons/' + saved.id)).status(), 404);
  checks.push('cancel preserves the report; confirmation deletes only the selected snapshot');

  async function runExample(kind) {
    await page.getByRole('button', { name: 'New comparison', exact: true }).click();
    await page.getByLabel('Example comparison', { exact: true }).selectOption(kind);
    await page.getByRole('button', { name: 'Load example', exact: true }).click();
    await page.getByText('Example loaded. Compare the versions when you’re ready.', { exact: true }).waitFor();
    await page.getByRole('checkbox', { name: 'Save to history', exact: true }).uncheck();
    await page.getByRole('button', { name: 'Compare specifications', exact: true }).click();
    await page.locator('.report-title').waitFor();
  }
  await runExample('additive');
  assert.equal(await page.locator('.finding-row').count(), 2);
  assert.equal(await page.locator('.summary-card.breaking strong').innerText(), '0');
  assert.equal(await page.locator('.summary-card.informational strong').innerText(), '2');
  checks.push('actual additive example produces two informational findings without saving');

  await runExample('breaking');
  await page.locator('.finding-row').filter({ hasText: 'HTTP operation removed' }).click();
  if (await page.getByRole('button', { name: 'Dismiss message', exact: true }).count()) await page.getByRole('button', { name: 'Dismiss message', exact: true }).click();
  const mask = baseline > 0 ? [page.locator('.recent-list'), page.locator('.nav-count')] : [];
  await page.screenshot({ path: path.join(root, 'docs/section-4-workspace.png'), fullPage: true, mask });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole('tab', { name: 'Findings', exact: false }).click();
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
  await page.screenshot({ path: path.join(root, 'docs/section-4-mobile.png'), fullPage: true });
  await page.locator('.finding-row').filter({ hasText: 'HTTP operation removed' }).click();
  await page.locator('.evidence-intro').waitFor({ state: 'visible' });
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
  await page.screenshot({ path: path.join(root, 'docs/section-4-evidence.png'), fullPage: true });
  checks.push('desktop and mobile screenshots use real unsaved original examples');
  assert.deepEqual(errors, []); assert.deepEqual(external, []);
  assert.deepEqual(await page.evaluate(() => [localStorage.length, sessionStorage.length]), [0, 0]);
  const current = await context.request.get(base + '/api/system/database');
  assert.equal((await current.json()).saved_comparisons, baseline);
  checks.push('no external page requests, browser storage, uncaught errors, or retained test rows');
  const report = { status: 'passed', mode: 'actual Chrome browser and local FastAPI/SQLite/offline workers', checks, baseline_saved_comparisons: baseline, test_fixture_deleted: true, preexisting_records_deleted: false, screenshots_mask_existing_history: baseline > 0, uncaught_errors: errors, external_requests: external, ai_used: false };
  await writeFile(path.join(root, 'docs/section-4-live.json'), JSON.stringify(report, null, 2) + '\n');
  console.log(JSON.stringify({ status: 'passed', checks: checks.length, retained_test_rows: 0 }));
} finally {
  for (const id of created) {
    const response = await context.request.get(base + '/api/comparisons/' + id);
    if (response.status() === 404) continue;
    const record = await response.json();
    if (response.status() !== 200 || record.id !== id || record.old.title !== marker || record.new.title !== marker || record.result.old.title !== marker) throw new Error('Fixture identity mismatch; refusing cleanup.');
    const removed = await context.request.delete(base + '/api/comparisons/' + id);
    assert.equal(removed.status(), 204);
  }
  await context.close(); await instance.close();
  for (const file of downloadedFiles) await unlink(file).catch(error => { if (error.code !== 'ENOENT') throw error; });
  await rmdir(directory);
}
