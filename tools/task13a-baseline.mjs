import { chromium } from '@playwright/test';
import { mkdir, readdir, readFile, stat, writeFile } from 'node:fs/promises';
import { gzipSync } from 'node:zlib';
import process from 'node:process';

const MODE = process.env.TASK13A_MODE ?? 'production';
const BASE_URL = process.env.BASE_URL ?? 'http://127.0.0.1:4173';
const STABILITY_MS = Number(process.env.STABILITY_MS ?? 600000);
const SCENARIO_MS = Number(process.env.SCENARIO_MS ?? 5000);
const OUTPUT_DIR = process.env.OUTPUT_DIR ?? 'artifacts/task13a';
const SOURCE_CARRIER_SHA = process.env.SOURCE_CARRIER_SHA ?? null;
const LOCAL_SOURCE_SHA = process.env.LOCAL_SOURCE_SHA ?? null;
const VIEWPORT = { width: 1920, height: 1080 };
const NETWORK_50_MBPS_BYTES_PER_SEC = (50 * 1024 * 1024) / 8;

function round(value, digits = 3) {
  if (value === null || value === undefined || !Number.isFinite(value)) return value ?? null;
  const factor = 10 ** digits;
  return Math.round(value * factor) / factor;
}

function percentile(values, p) {
  if (!values.length) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const index = Math.min(sorted.length - 1, Math.max(0, Math.ceil((p / 100) * sorted.length) - 1));
  return sorted[index] ?? null;
}

function median(values) {
  if (!values.length) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 1 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
}

function summarizeFrames(frameTimesMs) {
  const valid = frameTimesMs.filter((value) => Number.isFinite(value) && value > 0);
  const fpsSamples = valid.map((value) => 1000 / value);
  return {
    sampleCount: valid.length,
    medianFrameTimeMs: round(median(valid)),
    p95FrameTimeMs: round(percentile(valid, 95)),
    p99FrameTimeMs: round(percentile(valid, 99)),
    medianFps: round(median(fpsSamples)),
    p05Fps: round(percentile(fpsSamples, 5)),
    framesOver22_22ms: valid.filter((value) => value > 22.22).length,
    framesOver33_33ms: valid.filter((value) => value > 33.33).length,
    framesOver50ms: valid.filter((value) => value > 50).length,
  };
}

async function waitForRuntime(page) {
  await page.waitForFunction(() => {
    return Boolean(document.querySelector('[data-runtime-mode="interactive"], [data-runtime-mode="fallback"]'));
  }, { timeout: 30000 });

  const mode = await page.locator('.runtime-overlay').getAttribute('data-runtime-mode');
  if (mode !== 'interactive') {
    const text = await page.locator('.runtime-overlay').textContent();
    throw new Error(`runtime did not become interactive; mode=${mode}; overlay=${text}`);
  }
}

async function runtimePageSnapshot(page) {
  return page.evaluate(() => {
    const overlay = document.querySelector('.runtime-overlay');
    const runtime = document.querySelector('[data-character-runtime]');
    const canvas = document.querySelector('canvas');
    const gl = canvas?.getContext('webgl2') ?? null;
    const debug = gl?.getExtension('WEBGL_debug_renderer_info') ?? null;
    const memory = performance.memory;

    return {
      runtimeMode: overlay?.getAttribute('data-runtime-mode') ?? null,
      qualityLevel: overlay?.getAttribute('data-quality-level') ?? null,
      debugStateAvailable: Boolean(runtime),
      characterState: runtime?.getAttribute('data-state') ?? null,
      heldInputs: runtime?.getAttribute('data-held-inputs') ?? null,
      viewport: { width: window.innerWidth, height: window.innerHeight },
      devicePixelRatio: window.devicePixelRatio,
      canvas: canvas ? { width: canvas.width, height: canvas.height, clientWidth: canvas.clientWidth, clientHeight: canvas.clientHeight } : null,
      webgl2: Boolean(gl),
      webglVendor: gl ? (debug ? gl.getParameter(debug.UNMASKED_VENDOR_WEBGL) : gl.getParameter(gl.VENDOR)) : null,
      webglRenderer: gl ? (debug ? gl.getParameter(debug.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER)) : null,
      jsHeapUsedBytes: typeof memory?.usedJSHeapSize === 'number' ? memory.usedJSHeapSize : null,
      jsHeapTotalBytes: typeof memory?.totalJSHeapSize === 'number' ? memory.totalJSHeapSize : null,
      jsHeapLimitBytes: typeof memory?.jsHeapSizeLimit === 'number' ? memory.jsHeapSizeLimit : null,
    };
  });
}

async function collectNavigationSnapshot(page) {
  return page.evaluate(() => {
    const nav = performance.getEntriesByType('navigation')[0];
    const resources = performance.getEntriesByType('resource').map((entry) => ({
      name: entry.name,
      initiatorType: entry.initiatorType,
      durationMs: entry.duration,
      transferSize: entry.transferSize,
      encodedBodySize: entry.encodedBodySize,
      decodedBodySize: entry.decodedBodySize,
    }));

    return {
      interactiveAtPerformanceNowMs: performance.now(),
      navigation: nav ? {
        domContentLoadedMs: nav.domContentLoadedEventEnd,
        loadEventMs: nav.loadEventEnd,
        responseStartMs: nav.responseStart,
        responseEndMs: nav.responseEnd,
        transferSize: nav.transferSize,
        encodedBodySize: nav.encodedBodySize,
        decodedBodySize: nav.decodedBodySize,
      } : null,
      resources,
      totalResourceTransferBytes: resources.reduce((sum, entry) => sum + (entry.transferSize || 0), 0),
      totalResourceEncodedBytes: resources.reduce((sum, entry) => sum + (entry.encodedBodySize || 0), 0),
    };
  });
}

async function measureStartup(browser) {
  const context = await browser.newContext({ viewport: VIEWPORT, deviceScaleFactor: 1 });
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', (error) => errors.push(`pageerror:${error.message}`));
  page.on('console', (message) => {
    if (message.type() === 'error') errors.push(`console:${message.text()}`);
  });

  const cdp = await context.newCDPSession(page);
  await cdp.send('Network.enable');
  await cdp.send('Network.clearBrowserCache');
  await cdp.send('Network.setCacheDisabled', { cacheDisabled: false });
  await cdp.send('Network.emulateNetworkConditions', {
    offline: false,
    latency: 0,
    downloadThroughput: NETWORK_50_MBPS_BYTES_PER_SEC,
    uploadThroughput: NETWORK_50_MBPS_BYTES_PER_SEC,
    connectionType: 'other',
  });

  await page.goto(BASE_URL, { waitUntil: 'domcontentloaded' });
  await waitForRuntime(page);
  const cold = await collectNavigationSnapshot(page);

  await page.reload({ waitUntil: 'domcontentloaded' });
  await waitForRuntime(page);
  const warm = await collectNavigationSnapshot(page);

  const environment = await runtimePageSnapshot(page);
  await context.close();

  return {
    configuration: {
      bandwidthMbps: 50,
      latencyMs: 0,
      cachePolicy: 'browser cache cleared before first navigation; normal browser caching enabled; second navigation is reload in same context',
    },
    cold,
    warm,
    environment,
    errors,
  };
}

async function sampleFrames(page, durationMs, actionMode = 'none') {
  return page.evaluate(async ({ durationMs, actionMode }) => {
    const frameTimesMs = [];
    const longTasks = [];
    let observer = null;
    let actionTimer = null;

    if ('PerformanceObserver' in window) {
      try {
        observer = new PerformanceObserver((list) => {
          for (const entry of list.getEntries()) {
            longTasks.push({ startTime: entry.startTime, duration: entry.duration });
          }
        });
        observer.observe({ type: 'longtask', buffered: false });
      } catch {
        observer = null;
      }
    }

    const dispatchKey = (type, code) => {
      window.dispatchEvent(new KeyboardEvent(type, { code, bubbles: true, cancelable: true }));
    };

    if (actionMode === 'action') {
      actionTimer = window.setInterval(() => {
        dispatchKey('keydown', 'KeyE');
        dispatchKey('keyup', 'KeyE');
      }, 750);
    }

    const start = performance.now();
    await new Promise((resolve) => {
      let previous = null;
      const tick = (timestamp) => {
        if (previous !== null) frameTimesMs.push(timestamp - previous);
        previous = timestamp;
        if (timestamp - start >= durationMs) {
          resolve();
          return;
        }
        requestAnimationFrame(tick);
      };
      requestAnimationFrame(tick);
    });

    if (actionTimer !== null) clearInterval(actionTimer);
    observer?.disconnect();
    return { frameTimesMs, longTasks };
  }, { durationMs, actionMode });
}

async function runScenario(page, name, setup, teardown, actionMode = 'none') {
  await setup();
  await page.waitForTimeout(500);
  const measured = await sampleFrames(page, SCENARIO_MS, actionMode);
  await teardown();
  await page.waitForTimeout(150);
  const snapshot = await runtimePageSnapshot(page);
  return {
    name,
    configuration: { sampleDurationMs: SCENARIO_MS },
    frames: summarizeFrames(measured.frameTimesMs),
    longTaskCount: measured.longTasks.length,
    totalLongTaskMs: round(measured.longTasks.reduce((sum, entry) => sum + entry.duration, 0)),
    runtimeAfterScenario: snapshot,
  };
}

async function measureScenarios(browser) {
  const context = await browser.newContext({ viewport: VIEWPORT, deviceScaleFactor: 1 });
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', (error) => errors.push(`pageerror:${error.message}`));
  page.on('console', (message) => {
    if (message.type() === 'error') errors.push(`console:${message.text()}`);
  });

  await page.goto(BASE_URL, { waitUntil: 'domcontentloaded' });
  await waitForRuntime(page);

  const initialEnvironment = await runtimePageSnapshot(page);
  const scenarios = [];

  scenarios.push(await runScenario(page, 'hero_idle_presentation', async () => {}, async () => {}));

  scenarios.push(await runScenario(
    page,
    'character_move_and_turn',
    async () => {
      await page.keyboard.down('KeyW');
      await page.keyboard.down('KeyD');
    },
    async () => {
      await page.keyboard.up('KeyD');
      await page.keyboard.up('KeyW');
    },
  ));

  scenarios.push(await runScenario(
    page,
    'primary_action_zero_clip_fixture',
    async () => { await page.keyboard.press('KeyE'); },
    async () => {},
    'action',
  ));

  scenarios.push(await runScenario(
    page,
    'camera_follow_character_forward',
    async () => { await page.keyboard.down('KeyW'); },
    async () => { await page.keyboard.up('KeyW'); },
  ));

  const finalEnvironment = await runtimePageSnapshot(page);
  await context.close();

  return {
    initialEnvironment,
    finalEnvironment,
    scenarios,
    unavailableRepresentativeScenarios: [
      {
        name: 'camera_transition_or_orbit',
        reason: 'current RuntimeApp composition exposes follow mode only; no runtime transition/orbit control is wired',
      },
      {
        name: 'quality_level_transition',
        reason: 'quality policy is evaluated but its degradation recommendation is not applied to a runtime quality target',
      },
      {
        name: 'final_cinematic_action_cost',
        reason: 'current approved test fixture contains zero animation clips and is not the final cinematic character asset',
      },
    ],
    errors,
  };
}

async function runStability(browser) {
  const context = await browser.newContext({ viewport: VIEWPORT, deviceScaleFactor: 1 });
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', (error) => errors.push(`pageerror:${error.message}`));
  page.on('console', (message) => {
    if (message.type() === 'error') errors.push(`console:${message.text()}`);
  });

  await page.goto(BASE_URL, { waitUntil: 'domcontentloaded' });
  await waitForRuntime(page);

  const stability = await page.evaluate(async ({ durationMs }) => {
    const runtime = document.querySelector('[data-character-runtime]');
    const overlay = () => document.querySelector('.runtime-overlay');
    const canvas = document.querySelector('canvas');
    let contextLosses = 0;
    canvas?.addEventListener('webglcontextlost', () => { contextLosses += 1; });

    const semanticAvailable = Boolean(runtime);
    const semanticFailures = [];
    let focusLossChecks = 0;
    let focusLossFailures = 0;
    let fallbackObservations = 0;
    let actionChecks = 0;
    let actionStickyFailures = 0;
    const memorySamples = [];
    const frameTimesMs = [];
    const longTasks = [];
    let observer = null;

    if ('PerformanceObserver' in window) {
      try {
        observer = new PerformanceObserver((list) => {
          for (const entry of list.getEntries()) longTasks.push(entry.duration);
        });
        observer.observe({ type: 'longtask', buffered: false });
      } catch {
        observer = null;
      }
    }

    let collectingFrames = true;
    let previousFrame = null;
    const frameLoop = (timestamp) => {
      if (!collectingFrames) return;
      if (previousFrame !== null) frameTimesMs.push(timestamp - previousFrame);
      previousFrame = timestamp;
      requestAnimationFrame(frameLoop);
    };
    requestAnimationFrame(frameLoop);

    const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
    const key = (type, code) => window.dispatchEvent(new KeyboardEvent(type, { code, bubbles: true, cancelable: true }));
    const state = () => runtime?.getAttribute('data-state') ?? null;
    const held = () => runtime?.getAttribute('data-held-inputs') ?? null;
    const mode = () => overlay()?.getAttribute('data-runtime-mode') ?? null;
    const quality = () => overlay()?.getAttribute('data-quality-level') ?? null;
    const usedHeap = () => {
      const memory = performance.memory;
      return typeof memory?.usedJSHeapSize === 'number' ? memory.usedJSHeapSize : null;
    };

    const startedAt = performance.now();
    let nextMemoryAt = 120000;
    let cycles = 0;

    while (performance.now() - startedAt < durationMs) {
      cycles += 1;

      key('keydown', 'KeyW');
      await delay(120);
      if (semanticAvailable && state() !== 'move') semanticFailures.push({ cycle: cycles, stage: 'forward', state: state(), held: held() });
      key('keyup', 'KeyW');
      await delay(80);

      key('keydown', cycles % 2 === 0 ? 'KeyA' : 'KeyD');
      await delay(100);
      key('keyup', cycles % 2 === 0 ? 'KeyA' : 'KeyD');
      await delay(80);

      actionChecks += 1;
      key('keydown', 'KeyE');
      key('keyup', 'KeyE');
      await delay(120);
      if (semanticAvailable && state() === 'action') {
        actionStickyFailures += 1;
        semanticFailures.push({ cycle: cycles, stage: 'action_sticky', state: state(), held: held() });
      }

      key('keydown', 'KeyW');
      await delay(80);
      window.dispatchEvent(new Event('blur'));
      await delay(120);
      focusLossChecks += 1;
      if (semanticAvailable && (held() !== '0' || state() === 'move')) {
        focusLossFailures += 1;
        semanticFailures.push({ cycle: cycles, stage: 'blur_reset', state: state(), held: held() });
      }
      document.querySelector('.runtime-app')?.focus();

      if (mode() === 'fallback') fallbackObservations += 1;

      const elapsed = performance.now() - startedAt;
      if (elapsed >= nextMemoryAt) {
        memorySamples.push({ elapsedMs: elapsed, usedJSHeapSize: usedHeap() });
        nextMemoryAt += 60000;
      }

      await delay(250);
    }

    key('keyup', 'KeyW');
    key('keyup', 'KeyA');
    key('keyup', 'KeyD');
    key('keyup', 'KeyE');
    await delay(200);

    collectingFrames = false;
    observer?.disconnect();

    const finalElapsed = performance.now() - startedAt;
    if (memorySamples.length === 0 || memorySamples.at(-1)?.elapsedMs < finalElapsed - 10000) {
      memorySamples.push({ elapsedMs: finalElapsed, usedJSHeapSize: usedHeap() });
    }

    return {
      requestedDurationMs: durationMs,
      actualDurationMs: finalElapsed,
      cycles,
      semanticAvailable,
      semanticFailures: semanticFailures.slice(0, 100),
      semanticFailureCount: semanticFailures.length,
      focusLossChecks,
      focusLossFailures,
      actionChecks,
      actionStickyFailures,
      fallbackObservations,
      contextLosses,
      memorySamples,
      frameTimesMs,
      longTaskCount: longTasks.length,
      totalLongTaskMs: longTasks.reduce((sum, value) => sum + value, 0),
      finalMode: mode(),
      finalQualityLevel: quality(),
      finalState: state(),
      finalHeldInputs: held(),
    };
  }, { durationMs: STABILITY_MS });

  const memoryValues = stability.memorySamples.map((sample) => sample.usedJSHeapSize).filter((value) => Number.isFinite(value));
  const firstMemory = memoryValues[0] ?? null;
  const lastMemory = memoryValues.at(-1) ?? null;
  const memoryGrowthRatio = firstMemory && lastMemory ? (lastMemory - firstMemory) / firstMemory : null;
  const monotonicMemory = memoryValues.length >= 2 ? memoryValues.every((value, index) => index === 0 || value >= memoryValues[index - 1]) : null;

  const result = {
    ...stability,
    actualDurationMs: round(stability.actualDurationMs),
    frames: summarizeFrames(stability.frameTimesMs),
    frameTimesMs: undefined,
    totalLongTaskMs: round(stability.totalLongTaskMs),
    memoryGrowthRatio: round(memoryGrowthRatio, 5),
    memoryMonotonicNonDecreasing: monotonicMemory,
    memoryPolicyFailureObserved: memoryGrowthRatio !== null && monotonicMemory === true && memoryGrowthRatio > 0.2,
    errors,
    finalEnvironment: await runtimePageSnapshot(page),
  };

  await context.close();
  return result;
}

async function collectBundleMetrics() {
  try {
    const files = await readdir('dist/assets');
    const metrics = [];
    for (const name of files) {
      const path = `dist/assets/${name}`;
      const info = await stat(path);
      if (!info.isFile()) continue;
      const bytes = await readFile(path);
      metrics.push({ name, bytes: info.size, gzipBytes: gzipSync(bytes).length });
    }
    metrics.sort((a, b) => b.bytes - a.bytes);
    return metrics;
  } catch {
    return [];
  }
}

async function main() {
  if (!Number.isFinite(STABILITY_MS) || STABILITY_MS <= 0) throw new Error('STABILITY_MS must be positive');
  await mkdir(OUTPUT_DIR, { recursive: true });

  const browser = await chromium.launch({ headless: true, args: ['--enable-precise-memory-info'] });
  const browserVersion = browser.version();
  const result = {
    task: 'Task 13A Performance Baseline',
    mode: MODE,
    capturedAt: new Date().toISOString(),
    sourceCarrierSha: SOURCE_CARRIER_SHA,
    localSourceSha: LOCAL_SOURCE_SHA,
    executorCommitSha: process.env.GITHUB_SHA ?? null,
    browser: { engine: 'chromium', version: browserVersion, headless: true },
    viewport: VIEWPORT,
    limitations: [
      'GitHub-hosted Chromium is not accepted as real discrete or integrated GPU evidence.',
      'Current Box GLB fixture is non-final and cannot establish final cinematic-character performance acceptance.',
      'Task 13C real-hardware 1920x1080 validation remains required regardless of this baseline.',
    ],
  };

  try {
    if (MODE === 'production') {
      result.bundle = await collectBundleMetrics();
      result.startup = await measureStartup(browser);
      result.runtimeScenarios = await measureScenarios(browser);
    }

    result.stability = await runStability(browser);
  } finally {
    await browser.close();
  }

  const outputPath = `${OUTPUT_DIR}/task13a-${MODE}.json`;
  await writeFile(outputPath, `${JSON.stringify(result, null, 2)}\n`, 'utf8');

  const concise = {
    mode: result.mode,
    browser: result.browser,
    startupColdMs: result.startup?.cold?.interactiveAtPerformanceNowMs ?? null,
    startupWarmMs: result.startup?.warm?.interactiveAtPerformanceNowMs ?? null,
    scenarios: result.runtimeScenarios?.scenarios?.map((scenario) => ({ name: scenario.name, ...scenario.frames })) ?? null,
    stability: {
      requestedDurationMs: result.stability.requestedDurationMs,
      actualDurationMs: result.stability.actualDurationMs,
      cycles: result.stability.cycles,
      frames: result.stability.frames,
      contextLosses: result.stability.contextLosses,
      fallbackObservations: result.stability.fallbackObservations,
      errors: result.stability.errors,
      semanticAvailable: result.stability.semanticAvailable,
      semanticFailureCount: result.stability.semanticFailureCount,
      focusLossFailures: result.stability.focusLossFailures,
      actionStickyFailures: result.stability.actionStickyFailures,
      memoryGrowthRatio: result.stability.memoryGrowthRatio,
      memoryPolicyFailureObserved: result.stability.memoryPolicyFailureObserved,
    },
  };
  console.log(JSON.stringify(concise, null, 2));
}

await main();
