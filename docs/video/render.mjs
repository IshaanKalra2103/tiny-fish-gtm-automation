// Render a 1920x1080 diagram HTML to PNG with headless Playwright Chromium.
// Usage (from the repo root): node docs/video/render.mjs docs/video/architecture.html docs/video/architecture.png
// Uses the Playwright that web/ already installs (pnpm), so no extra install is needed.
import { createRequire } from 'node:module';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const require = createRequire(path.resolve(here, '../../web/package.json'));
const { chromium } = require('@playwright/test');

const [src, out] = process.argv.slice(2);
if (!src || !out) {
  console.error('usage: node docs/video/render.mjs <in.html> <out.png>');
  process.exit(1);
}
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1 });
await page.goto(pathToFileURL(path.resolve(src)).href, { waitUntil: 'networkidle' });
await page.evaluate(() => document.fonts.ready);
await page.waitForTimeout(300);
await page.screenshot({ path: path.resolve(out), clip: { x: 0, y: 0, width: 1920, height: 1080 } });
await browser.close();
console.log('wrote', out);
