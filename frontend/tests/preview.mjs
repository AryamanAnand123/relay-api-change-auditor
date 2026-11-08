import { browser, base, root } from './helpers.mjs';
import path from 'node:path';

const instance = await browser();
try {
  const page = await instance.newPage({ viewport: { width: 1440, height: 1000 }, deviceScaleFactor: 1 });
  await page.goto(base);
  await page.getByText('History ready', { exact: true }).waitFor();
  await page.screenshot({ path: path.join(root, 'docs/section-4-empty.png'), fullPage: true });
  console.log(JSON.stringify({ title: await page.title(), screenshot: 'docs/section-4-empty.png', exactNumberReviver: await page.evaluate(() => { let source; JSON.parse('900719925474099312345678901', (_, value, context) => { source = context?.source; return value; }); return source === '900719925474099312345678901'; }) }));
} finally { await instance.close(); }
