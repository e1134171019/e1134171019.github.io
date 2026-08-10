import { chromium } from '@playwright/test';
import { mkdir, writeFile } from 'node:fs/promises';

const BASE_URL = process.env.BASE_URL ?? 'http://127.0.0.1:4175';
const OUTPUT_DIR = 'artifacts/task13a-diagnostic';
const VIEWPORT = { width: 1920, height: 1080 };
const SAMPLE_MS = 5000;

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

async function sampleRuntime(page, label) {
  const result = await page.evaluate(async ({ sampleMs }) => {
    const overlayHost = document.querySelector('.runtime-app__overlay');
    if (!overlayHost) throw new Error('runtime overlay host missing');

    const rafTimes = [];
    let runtimeOverlayMutations = 0;
    const observer = new MutationObserver((records) => {
      for (const record of records) {
        if (record.type === 'childList') runtimeOverlayMutations += 1;
      }
    });
    observer.observe(overlayHost, { childList: true });

    const startedAt = performance.now();
    await new Promise((resolve) => {
      let previous = null;
      const tick = (timestamp) => {
        if (previous !== null) rafTimes.push(timestamp - previous);
        previous = timestamp;
        if (timestamp - startedAt >= sampleMs) resolve();
        else requestAnimationFrame(tick);
      };
      requestAnimationFrame(tick);
    });
    const actualDurationMs = performance.now() - startedAt;
    observer.disconnect();

    const runtime = document.querySelector('[data-character-runtime]');
    const overlay = document.querySelector('.runtime-overlay');
    return {
      rafTimes,
      runtimeOverlayMutations,
      actualDurationMs,
      documentHasFocus: document.hasFocus(),
      visibilityState: document.visibilityState,
      runtimeMode: overlay?.getAttribute('data-runtime-mode') ?? null,
      qualityLevel: overlay?.getAttribute('data-quality-level') ?? null,
      devRuntimeDiagnosticsPresent: Boolean(runtime),
      characterState: runtime?.getAttribute('data-state') ?? null,
      heldInputs: runtime?.getAttribute('data-held-inputs') ?? null,
    };
  }, { sampleMs: SAMPLE_MS });

  return {
    label,
    ...result,
    raf: summarize(result.rafTimes),
    rafTimes: undefined,
    runtimeFrameProxyFps: result.actualDurationMs > 0
      ? (result.runtimeOverlayMutations * 1000) / result.actualDurationMs
      : null,
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
      canvas: canvas ? { width: canvas.width, height: canvas.height, clientWidth: canvas.clientWidth, clientHeight: canvas.clientHeight } : null,
      documentHasFocus: document.hasFocus(),
      visibilityState: document.visibilityState,
    };
  });
}

async function syntheticBlur(page) {
  await page.evaluate(() => window.dispatchEvent(new Event('blur')));
  await page.waitForTimeout(250);
}

async function refocusRuntime(page) {
  await page.evaluate(() => {
    document.querySelector('.runtime-app')?.focus();
    window.dispatchEvent(new Event('focus'));
  });
  await page.waitForTimeout(250);
}

async function repeatedBlurFocus(page, count) {
  for (let index = 0; index < count; index += 1) {
    await syntheticBlur(page);
    await refocusRuntime(page);
  }
}

await mkdir(OUTPUT_DIR, { recursive: true });
const browser = await chromium.launch({ headless: true, args: ['--enable-precise-memory-info'] });
const output = {
  diagnostic: 'generic requestAnimationFrame versus RuntimeApp overlay-mutation frame proxy across synthetic blur/focus',
  browser: browser.version(),
  viewport: VIEWPORT,
  sampleDurationMs: SAMPLE_MS,
  phases: [],
};

try {
  const context = await browser.newContext({ viewport: VIEWPORT, deviceScaleFactor: 1 });
  const page = await context.newPage();
  await page.goto(BASE_URL, { waitUntil: 'domcontentloaded' });
  await waitInteractive(page);
  output.environment = await environment(page);

  output.phases.push(await sampleRuntime(page, 'baseline_before_blur'));

  await syntheticBlur(page);
  output.phases.push(await sampleRuntime(page, 'after_synthetic_window_blur'));

  await refocusRuntime(page);
  output.phases.push(await sampleRuntime(page, 'after_runtime_refocus'));

  await repeatedBlurFocus(page, 10);
  output.phases.push(await sampleRuntime(page, 'after_10_blur_focus_cycles'));

  output.finalEnvironment = await environment(page);
  await context.close();
} finally {
  await browser.close();
}

await writeFile(`${OUTPUT_DIR}/warmup-diagnostic.json`, JSON.stringify(output, null, 2));
console.log(JSON.stringify(output, null, 2));
