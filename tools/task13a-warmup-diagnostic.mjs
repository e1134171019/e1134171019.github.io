import { chromium } from '@playwright/test';
import { mkdir, writeFile } from 'node:fs/promises';

const BASE_URL = process.env.BASE_URL ?? 'http://127.0.0.1:4175';
const OUTPUT_DIR = 'artifacts/task13a-diagnostic';
const VIEWPORT = { width: 1920, height: 1080 };

function median(values) {
  const sorted = [...values].sort((a, b) => a - b);
  if (!sorted.length) return null;
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}

function summarize(values) {
  const valid = values.filter((v) => Number.isFinite(v) && v > 0);
  const fps = valid.map((v) => 1000 / v);
  return {
    count: valid.length,
    medianFrameMs: median(valid),
    medianFps: median(fps),
    over50ms: valid.filter((v) => v > 50).length,
  };
}

async function waitInteractive(page) {
  await page.waitForSelector('[data-runtime-mode="interactive"]', { state: 'visible', timeout: 30000 });
}

async function sample(page, label, observerEnabled) {
  const result = await page.evaluate(async ({ observerEnabled }) => {
    const frames = [];
    const longTasks = [];
    let observer = null;
    if (observerEnabled) {
      try {
        observer = new PerformanceObserver((list) => {
          for (const entry of list.getEntries()) longTasks.push(entry.duration);
        });
        observer.observe({ type: 'longtask', buffered: false });
      } catch {}
    }

    const start = performance.now();
    await new Promise((resolve) => {
      let previous = null;
      const tick = (timestamp) => {
        if (previous !== null) frames.push(timestamp - previous);
        previous = timestamp;
        if (timestamp - start >= 5000) resolve();
        else requestAnimationFrame(tick);
      };
      requestAnimationFrame(tick);
    });
    observer?.disconnect();

    return {
      frames,
      longTaskCount: longTasks.length,
      longTaskMs: longTasks.reduce((a, b) => a + b, 0),
      nowMs: performance.now(),
    };
  }, { observerEnabled });

  return {
    label,
    observerEnabled,
    atPerformanceNowMs: result.nowMs,
    frames: summarize(result.frames),
    longTaskCount: result.longTaskCount,
    longTaskMs: result.longTaskMs,
  };
}

async function environment(page) {
  return page.evaluate(() => {
    const canvas = document.querySelector('canvas');
    const gl = canvas?.getContext('webgl2') ?? null;
    const ext = gl?.getExtension('WEBGL_debug_renderer_info') ?? null;
    return {
      webgl2: Boolean(gl),
      renderer: gl ? (ext ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER)) : null,
      canvas: canvas ? { width: canvas.width, height: canvas.height } : null,
    };
  });
}

await mkdir(OUTPUT_DIR, { recursive: true });
const browser = await chromium.launch({ headless: true, args: ['--enable-precise-memory-info'] });
const output = { browser: browser.version(), viewport: VIEWPORT, phases: [] };

try {
  const context = await browser.newContext({ viewport: VIEWPORT, deviceScaleFactor: 1 });
  const page = await context.newPage();
  await page.goto(BASE_URL, { waitUntil: 'domcontentloaded' });
  await waitInteractive(page);
  output.environment = await environment(page);

  output.phases.push(await sample(page, 'cold_no_observer', false));
  output.phases.push(await sample(page, 'cold_with_observer', true));
  await page.waitForTimeout(10000);
  output.phases.push(await sample(page, 'warm_no_observer', false));
  output.phases.push(await sample(page, 'warm_with_observer', true));
  await context.close();

  const context2 = await browser.newContext({ viewport: VIEWPORT, deviceScaleFactor: 1 });
  const page2 = await context2.newPage();
  await page2.goto(BASE_URL, { waitUntil: 'domcontentloaded' });
  await waitInteractive(page2);
  output.secondContextEnvironment = await environment(page2);
  output.phases.push(await sample(page2, 'second_context_no_observer', false));
  output.phases.push(await sample(page2, 'second_context_with_observer', true));
  await context2.close();
} finally {
  await browser.close();
}

await writeFile(`${OUTPUT_DIR}/warmup-diagnostic.json`, JSON.stringify(output, null, 2));
console.log(JSON.stringify(output, null, 2));
