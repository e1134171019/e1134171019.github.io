import { createServer } from 'node:http';
import { readFile, stat } from 'node:fs/promises';
import { extname, join, normalize, resolve } from 'node:path';
import { chromium } from '@playwright/test';

const [directory, portText, label] = process.argv.slice(2);
if (!directory || !portText || !label) {
  throw new Error('usage: node tools/task13b-smoke.mjs <directory> <port> <label>');
}

const root = resolve(directory);
const port = Number(portText);
const mime = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.glb': 'model/gltf-binary',
};

const server = createServer(async (req, res) => {
  try {
    const urlPath = decodeURIComponent((req.url ?? '/').split('?')[0]);
    const relative = urlPath === '/' ? 'index.html' : normalize(urlPath).replace(/^[/\\]+/, '');
    let filePath = resolve(join(root, relative));
    if (!filePath.startsWith(root)) throw new Error('path traversal');

    try {
      const info = await stat(filePath);
      if (info.isDirectory()) filePath = join(filePath, 'index.html');
    } catch {
      filePath = join(root, 'index.html');
    }

    const body = await readFile(filePath);
    res.writeHead(200, {
      'Content-Type': mime[extname(filePath)] ?? 'application/octet-stream',
      'Cache-Control': 'no-store',
    });
    res.end(body);
  } catch (error) {
    res.writeHead(500, { 'Content-Type': 'text/plain; charset=utf-8' });
    res.end(String(error));
  }
});

await new Promise((resolveListen) => server.listen(port, '127.0.0.1', resolveListen));
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1280, height: 720 } });
const errors = [];
page.on('pageerror', (error) => errors.push(`pageerror:${error.message}`));
page.on('console', (message) => {
  if (message.type() === 'error') errors.push(`console:${message.text()}`);
});

let result;
try {
  await page.goto(`http://127.0.0.1:${port}/`, { waitUntil: 'domcontentloaded' });
  await page.locator('.runtime-overlay[data-runtime-mode="interactive"]').waitFor({ timeout: 30000 });
  const canvasCount = await page.locator('.runtime-app__scene canvas').count();
  if (canvasCount < 1) throw new Error('runtime canvas missing');
  await page.locator('.runtime-app').focus();
  await page.keyboard.press('KeyW');
  await page.keyboard.press('KeyE');
  await page.waitForTimeout(750);
  const fallbackCount = await page.locator('.runtime-overlay[data-runtime-mode="fallback"]').count();
  if (fallbackCount !== 0) throw new Error('runtime entered fallback');
  if (errors.length) throw new Error(errors.join('\n'));

  result = {
    label,
    status: 'PASS',
    canvasCount,
    fallbackCount,
    errors,
  };
} catch (error) {
  result = {
    label,
    status: 'FAIL',
    errors: [...errors, String(error)],
  };
  process.exitCode = 1;
} finally {
  console.log(JSON.stringify(result, null, 2));
  await browser.close();
  await new Promise((resolveClose) => server.close(resolveClose));
}
