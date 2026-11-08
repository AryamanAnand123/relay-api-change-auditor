import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { browser, base, root } from './helpers.mjs';

const fixtures = JSON.parse(execFileSync(path.join(root, '.venv/Scripts/python.exe'), [path.join(root, 'scripts/browser-fixtures.py')], { encoding: 'utf8' }));
const result = JSON.parse(fixtures.breaking), id = '00000000-0000-4000-8000-000000000001';
const record = { id, created_at: '2026-11-08T10:00:00Z', status: 'completed', old: { title: result.old.title, version: result.old.api_version }, new: { title: result.new.title, version: result.new.api_version }, summary: result.comparison.summary, coverage_status: 'supported_subset', result };
const instance = await browser();
const checks = [], errors = [], external = [];
let ready = false, posted = 0, failure = null;
try {
  const context = await instance.newContext({ viewport: { width: 1440, height: 1000 } });
  const page = await context.newPage();
  page.on('pageerror', error => errors.push(error.message));
  page.on('request', request => { if (request.url().startsWith('http') && new URL(request.url()).origin !== base) external.push(request.url()); });
  await page.route('**/api/**', async route => {
    const request = route.request(), url = new URL(request.url()), p = url.pathname;
    const send = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: typeof body === 'string' ? body : JSON.stringify(body) });
    if (p === '/api/system/database') return send({ status: 'ready', saved_comparisons: 1 });
    if (p === '/api/ai/status') return send({ status: ready ? 'ready' : 'missing_key', configured: ready });
    if (p.startsWith('/api/examples/')) return send(await readFile(path.join(root, 'examples', p.split('/').at(-1)), 'utf8'));
    if (p === '/api/comparisons') return send({ items: [record], next_cursor: null, has_more: false });
    if (p === '/api/specifications/compare') return send(fixtures.breaking);
    if (p === '/api/comparisons/' + id) return send(record);
    if (p.endsWith('/explanations')) {
      posted++;
      const data = request.postDataJSON();
      assert.equal(data.allow_external_processing, true);
      assert.deepEqual(Object.keys(data).sort(), ['allow_external_processing', 'finding_id']);
      await new Promise(resolve => setTimeout(resolve, 250));
      if (failure) return send({ detail: { code: failure.code, message: failure.message } }, failure.status);
      return send({ status: 'generated', cached: true, finding_id: data.finding_id,
        content: { finding_id: data.finding_id, explanation: '<img src=x onerror=alert(1)> Untrusted-looking guidance stays text.', migration_steps: ['Inspect the actual new schema.'], verification_steps: ['Test the old and new payloads.'], caveats: ['No runtime behavior established.'], evidence_references: ['before', 'after'] },
        references: { before: { pointer: '#/old' }, after: { pointer: '#/new' } },
        provenance: { reported_model: 'test-only-model', latency_ms: 123, prompt_version: 'test-only' }, notice: 'AI guidance is advisory. Rule severity is unchanged.' });
    }
    return send({ detail: 'Not found' }, 404);
  });
  await page.goto(base + '/#review=' + id);
  await page.locator('.report-title').waitFor();
  await page.getByText('Add your Free-plan key using', { exact: false }).waitFor();
  assert.equal(posted, 0);
  checks.push('missing-key guidance and zero automatic generation on saved reload');

  ready = true;
  await page.getByRole('button', { name: 'Refresh AI status', exact: true }).click();
  const button = page.getByRole('button', { name: 'Explain finding', exact: true });
  await button.waitFor();
  assert.equal(await button.isDisabled(), true);
  await page.getByRole('checkbox', { name: /Send this finding/ }).check();
  await button.evaluate(element => { element.click(); element.click(); });
  await page.locator('.ai-content').waitFor();
  assert.equal(posted, 1);
  assert.equal(await page.locator('.finding-row').count(), 3);
  checks.push('explicit evidence-sharing consent, duplicate-click protection, and unchanged findings');
  assert.match(await page.locator('.ai-content').innerText(), /Untrusted-looking guidance/);
  assert.equal(await page.locator('.ai-content img').count(), 0);
  assert.match(await page.locator('.ai-provenance').innerText(), /test-only-model/);
  assert.match(await page.locator('.ai-generated-label').innerText(), /Reused from memory cache/);
  checks.push('safe text rendering, model provenance, cache label, and evidence references');
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole('tab', { name: 'Evidence', exact: true }).click();
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
  checks.push('mobile guidance panel does not create horizontal overflow');

  await page.setViewportSize({ width: 1440, height: 1000 });
  for (const [code, status, message] of [['ai_rate_limited', 429, 'Free quota reached. Try later.'], ['ai_timeout', 504, 'AI timed out. Rule evidence remains available.'], ['ai_invalid_output', 502, 'AI output failed validation.']]) {
    await page.reload(); await page.locator('.report-title').waitFor();
    await page.getByRole('button', { name: 'Explain finding', exact: true }).waitFor();
    failure = { code, status, message };
    await page.getByRole('checkbox', { name: /Send this finding/ }).check();
    await page.getByRole('button', { name: 'Explain finding', exact: true }).click();
    await page.locator('.ai-error').filter({ hasText: message }).waitFor();
    assert.equal(await page.locator('.finding-row').count(), 3);
    assert.equal(await page.locator('.summary-card.breaking strong').innerText(), '3');
    checks.push(code + ' leaves the complete deterministic review usable');
  }
  failure = null;
  await page.reload(); await page.locator('.report-title').waitFor();
  await page.getByRole('checkbox', { name: /Send this finding/ }).check();
  await page.getByRole('button', { name: 'Explain finding', exact: true }).click();
  await page.locator('.finding-row').filter({ hasText: 'HTTP operation removed' }).click();
  await page.waitForTimeout(400);
  assert.equal(await page.locator('.ai-content').count(), 0);
  assert.equal(await page.getByRole('checkbox', { name: /Send this finding/ }).isChecked(), false);
  checks.push('switching findings discards stale AI responses and resets consent');

  await page.getByRole('button', { name: 'New comparison', exact: true }).click();
  await page.getByRole('button', { name: 'Load example', exact: true }).click();
  await page.getByText('Example loaded. Compare the versions when you’re ready.', { exact: true }).waitFor();
  await page.getByRole('checkbox', { name: 'Save to history', exact: true }).uncheck();
  await page.getByRole('button', { name: 'Compare specifications', exact: true }).click();
  await page.getByText('Save this comparison to request an explanation.', { exact: false }).waitFor();
  assert.equal(await page.getByRole('button', { name: 'Explain finding', exact: true }).count(), 0);
  checks.push('unsaved reports retain evidence and explain how to enable AI');
  assert.deepEqual(errors, []); assert.deepEqual(external, []);
  assert.deepEqual(await page.evaluate(() => [localStorage.length, sessionStorage.length]), [0, 0]);
  const report = { status: 'passed', mode: 'simulated AI API responses; no real provider calls or history writes', checks, uncaught_errors: errors, external_page_requests: external };
  await writeFile(path.join(root, 'docs/section-5-browser.json'), JSON.stringify(report, null, 2) + '\n');
  console.log(JSON.stringify({ status: 'passed', checks: checks.length }));
  await context.close();
} finally { await instance.close(); }
