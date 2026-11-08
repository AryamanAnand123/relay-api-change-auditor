import { existsSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright-core';

export const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
export const base = 'http://127.0.0.1:8010';
export async function browser() {
  const executablePath = [process.env.RELAY_BROWSER, 'C:/Program Files/Google/Chrome/Application/chrome.exe', 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'].find(file => file && existsSync(file));
  if (!executablePath) throw new Error('Install Chrome/Edge or set RELAY_BROWSER to an existing browser executable; no browser is downloaded by these checks.');
  return chromium.launch({ executablePath, headless: true, args: ['--no-first-run', '--disable-background-networking'] });
}
