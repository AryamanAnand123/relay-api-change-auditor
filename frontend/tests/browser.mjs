import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { browser, base, root } from './helpers.mjs';

const raw = JSON.parse(execFileSync(path.join(root, '.venv/Scripts/python.exe'), [path.join(root, 'scripts/browser-fixtures.py')], { encoding: 'utf8' }));
const fixtures = Object.fromEntries(Object.entries(raw).map(([key, text]) => [key, JSON.parse(text)]));
const instance = await browser();
const checks = [], errors = [], external = [];
let rows = [], nextKind = 'breaking', nextError = null, counter = 0, posts = 0, deletes = 0, unavailable = false;
const makeRecord = (kind = 'breaking', title) => {
  const result = fixtures[kind];
  const id = '00000000-0000-4000-8000-' + String(++counter).padStart(12, '0');
  return { meta: { id, created_at: '2026-11-08T09:00:00.000000Z', status: 'completed', old: { title: title || result.old.title, version: result.old.api_version }, new: { title: result.new.title, version: result.new.api_version }, summary: result.comparison.summary, coverage_status: result.comparison.coverage.status, reused: false }, kind };
};
const serialized = record => JSON.stringify(record.meta).slice(0, -1) + ',"result":' + raw[record.kind] + '}';
try {
  const context = await instance.newContext({ viewport: { width: 1440, height: 1000 }, acceptDownloads: true });
  const page = await context.newPage();
  page.on('pageerror', error => errors.push(error.message));
  page.on('request', request => { if (request.url().startsWith('http') && new URL(request.url()).origin !== base) external.push(request.url()); });
  await page.route('**/api/**', async route => {
    const url = new URL(route.request().url()), method = route.request().method(), p = url.pathname;
    const send = (value, status = 200) => route.fulfill({ status, contentType: 'application/json', body: typeof value === 'string' ? value : JSON.stringify(value) });
    if (p === '/api/system/database') return send(unavailable ? { detail: { message: 'Unavailable' } } : { status: 'ready', saved_comparisons: rows.length }, unavailable ? 503 : 200);
    if (p.startsWith('/api/examples/')) return send(await readFile(path.join(root, 'examples', decodeURIComponent(p.split('/').at(-1))), 'utf8'));
    if (p === '/api/comparisons' && method === 'GET') {
      if (unavailable) return send({ detail: { message: 'Unavailable' } }, 503);
      const anchor = url.searchParams.get('cursor');
      const start = anchor ? rows.findIndex(row => row.meta.id === anchor) + 1 : 0;
      const selected = rows.slice(start, start + 10), more = start + 10 < rows.length;
      return send({ items: selected.map(row => row.meta), next_cursor: more ? selected.at(-1).meta.id : null, has_more: more });
    }
    if ((p === '/api/comparisons' || p === '/api/specifications/compare') && method === 'POST') {
      posts++; await new Promise(resolve => setTimeout(resolve, 150));
      if (nextError) { const error = nextError; nextError = null; return send({ detail: error }, 422); }
      if (p === '/api/specifications/compare') return send(raw[nextKind]);
      const record = makeRecord(nextKind); rows.unshift(record); return send(serialized(record), 201);
    }
    const id = p.split('/')[3], record = rows.find(row => row.meta.id === id);
    if (p.startsWith('/api/comparisons/')) {
      if (!record) return send({ detail: { message: 'Saved comparison not found.' } }, 404);
      if (method === 'DELETE') { deletes++; rows = rows.filter(row => row !== record); return route.fulfill({ status: 204 }); }
      if (p.endsWith('/export')) return route.fulfill({ status: 200, contentType: url.searchParams.get('format') === 'json' ? 'application/json' : 'text/markdown', body: url.searchParams.get('format') === 'json' ? serialized(record) : '# Simulated export for browser interaction check\n' });
      return send(serialized(record));
    }
    return send({ detail: 'Not found' }, 404);
  });

  await page.goto(base);
  await page.getByText('History ready', { exact: true }).waitFor();
  assert.equal(await page.title(), 'Relay — API Change Auditor');
  assert.equal(await page.getByRole('button', { name: 'Compare specifications', exact: true }).isDisabled(), true);
  await page.getByText('Saved comparisons will appear here.', { exact: true }).waitFor();
  checks.push('honest empty state and disabled incomplete comparison');

  async function loadAndRun(kind, example = 'breaking') {
    if (await page.locator('.finding-row').count() || await page.locator('.report-title').count()) await page.getByRole('button', { name: 'New comparison', exact: true }).click();
    nextKind = kind;
    await page.getByLabel('Example comparison', { exact: true }).selectOption(example);
    await page.getByRole('button', { name: 'Load example', exact: true }).click();
    await page.getByText('Example loaded. Compare the versions when you’re ready.', { exact: true }).waitFor();
    await page.getByRole('button', { name: 'Compare specifications', exact: true }).evaluate(button => { button.click(); button.click(); });
    await page.locator('.report-title').waitFor();
  }
  await loadAndRun('breaking');
  assert.equal(posts, 1);
  assert.equal(await page.locator('.finding-row').count(), 3);
  checks.push('example loading, real report shape, and duplicate-click prevention');
  await page.locator('.finding-row').filter({ hasText: 'Property added to the required list' }).click();
  assert.match(await page.locator('.evidence-value.after pre').innerText(), /currency/);
  assert.match(await page.locator('.evidence-value.before pre').innerText(), /item/);
  await page.getByRole('button', { name: 'Filter informational', exact: true }).click();
  await page.getByText('No matching findings', { exact: true }).waitFor();
  assert.equal(await page.locator('.evidence-intro').count(), 0);
  await page.getByRole('button', { name: 'Clear filters', exact: true }).click();
  await page.getByLabel('Filter endpoint', { exact: true }).selectOption('POST /orders');
  assert.equal(await page.locator('.finding-row').count(), 2);
  await page.getByLabel('Search findings', { exact: true }).fill('schema_type_changed');
  assert.equal(await page.locator('.finding-row').count(), 1);
  checks.push('severity/search/endpoint filters and matching evidence selection');
  const download = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Export JSON', exact: true }).click();
  assert.match((await download).suggestedFilename(), /^comparison-.*\.json$/);
  checks.push('export triggers a download with a safe generated filename');

  await loadAndRun('partial');
  await page.getByText('Coverage needs review', { exact: true }).click();
  await page.getByText('allOf', { exact: true }).waitFor();
  await page.getByRole('button', { name: 'Filter needs review', exact: true }).click();
  await page.locator('.review-note').waitFor();
  checks.push('partial coverage and uncertainty stay visible');
  await loadAndRun('identical', 'identical');
  await page.getByText('No changes in the implemented subset', { exact: true }).waitFor();
  assert.equal(await page.locator('.finding-row').count(), 0);
  checks.push('zero-change result makes no universal safe-upgrade claim');

  await loadAndRun('numeric');
  assert.match(await page.locator('.evidence-value.before pre').innerText(), /900719925474099312345678901/);
  checks.push('large numeric evidence is displayed exactly without rounding');
  await loadAndRun('malicious');
  assert.equal(await page.locator('img[src="x"]').count(), 0);
  assert.equal(await page.evaluate(() => window.__relayInjected), undefined);
  assert.match(await page.locator('.evidence-value.after pre').innerText(), /<img/);
  checks.push('untrusted titles and evidence render as text');

  await page.getByRole('button', { name: 'New comparison', exact: true }).click();
  await page.getByRole('button', { name: 'Load example', exact: true }).click();
  await page.getByText('Example loaded. Compare the versions when you’re ready.', { exact: true }).waitFor();
  nextError = { code: 'invalid_json', side: 'old', message: 'File is not valid JSON.' };
  await page.getByRole('button', { name: 'Compare specifications', exact: true }).click();
  await page.getByRole('alert').filter({ hasText: 'Old specification' }).waitFor();
  assert.equal(await page.locator('.drop-zone.invalid').count(), 1);
  assert.equal(await page.getByRole('button', { name: 'Compare specifications', exact: true }).isEnabled(), true);
  checks.push('validation errors retain files and identify the failing side');

  await page.getByRole('button', { name: /^Saved reviews/ }).click();
  await page.locator('.history-card').first().waitFor();
  await page.locator('.history-card').first().getByRole('button', { name: /^Delete review/ }).click();
  await page.getByRole('dialog').waitFor();
  await page.getByRole('button', { name: 'Cancel', exact: true }).click();
  assert.equal(deletes, 0);
  await page.locator('.history-card').first().getByRole('button', { name: /^Delete review/ }).click();
  await page.getByRole('dialog').getByRole('button', { name: 'Delete review', exact: true }).click();
  await page.getByText('Saved comparison deleted.', { exact: true }).waitFor();
  assert.equal(deletes, 1);
  checks.push('native confirmation supports cancel and exact-record deletion');

  rows = Array.from({ length: 13 }, (_, i) => makeRecord('breaking', 'Review ' + (i + 1)));
  await page.getByRole('button', { name: 'Refresh', exact: true }).click();
  await page.getByRole('button', { name: 'Load more reviews', exact: true }).waitFor();
  assert.equal(await page.locator('.history-card').count(), 10);
  await page.getByRole('button', { name: 'Load more reviews', exact: true }).click();
  await page.waitForFunction(() => document.querySelectorAll('.history-card').length === 13);
  await page.locator('.history-card').first().getByRole('button', { name: 'Open review', exact: true }).click();
  await page.locator('.report-title').waitFor();
  const hash = new URL(page.url()).hash;
  await page.reload();
  await page.locator('.report-title').waitFor();
  assert.equal(new URL(page.url()).hash, hash);
  checks.push('history pagination, reopen, and saved-review reload bookmarks');

  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole('tab', { name: 'Findings', exact: false }).click();
  await page.getByRole('tab', { name: 'Findings', exact: false }).press('ArrowRight');
  assert.equal(await page.getByRole('tab', { name: 'Evidence', exact: true }).getAttribute('aria-selected'), 'true');
  await page.getByRole('tab', { name: 'Evidence', exact: true }).press('Home');
  assert.equal(await page.getByRole('tab', { name: 'Specifications', exact: true }).getAttribute('aria-selected'), 'true');
  await page.getByRole('tab', { name: 'Findings', exact: false }).click();
  await page.locator('.finding-row').first().click();
  await page.locator('.evidence-intro').waitFor({ state: 'visible' });
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true);
  await page.getByRole('tab', { name: 'Specifications', exact: true }).click();
  await page.getByRole('button', { name: 'New comparison', exact: true }).click();
  await page.getByRole('button', { name: 'Load example', exact: true }).click();
  await page.getByText('Example loaded. Compare the versions when you’re ready.', { exact: true }).waitFor();
  checks.push('mobile keyboard/panel navigation and no horizontal overflow');

  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.getByRole('button', { name: /^Saved reviews/ }).click();
  await page.locator('.history-card').first().getByRole('button', { name: 'Open review', exact: true }).click();
  await page.locator('.report-title').waitFor();
  const removedId = new URL(page.url()).hash.split('=')[1];
  rows = rows.filter(row => row.meta.id !== removedId);
  await page.getByRole('button', { name: 'Export JSON', exact: true }).click();
  await page.getByRole('alert').filter({ hasText: 'Saved comparison not found' }).waitFor();
  assert.equal(await page.locator('.report-title').count(), 0);
  assert.equal(new URL(page.url()).hash, '');
  checks.push('export of a review removed elsewhere clears the stale snapshot');

  unavailable = true;
  await page.goto(base);
  await page.getByText('History unavailable', { exact: true }).waitFor({ state: 'attached' });
  assert.equal(await page.getByRole('checkbox', { name: 'Save to history', exact: true }).isChecked(), false);
  await page.getByRole('button', { name: 'Load example', exact: true }).click();
  await page.getByText('Example loaded. Compare the versions when you’re ready.', { exact: true }).waitFor();
  nextKind = 'breaking';
  await page.getByRole('button', { name: 'Compare specifications', exact: true }).click();
  await page.locator('.report-title').waitFor();
  await page.getByText('UNSAVED REVIEW', { exact: true }).waitFor();
  checks.push('unavailable history still permits an explicit unsaved comparison');
  assert.deepEqual(await page.evaluate(() => [localStorage.length, sessionStorage.length]), [0, 0]);
  assert.deepEqual(errors, []); assert.deepEqual(external, []);
  checks.push('no browser storage, uncaught errors, or external page requests');
  const report = { status: 'passed', mode: 'simulated API states using current-engine original fixtures', checks, uncaught_errors: errors, external_requests: external };
  await writeFile(path.join(root, 'docs/section-4-browser.json'), JSON.stringify(report, null, 2) + '\n');
  console.log(JSON.stringify({ status: 'passed', checks: checks.length, mode: report.mode }));
  await context.close();
} finally { await instance.close(); }
