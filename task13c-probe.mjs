import {
  summarizeFrameTimes,
  evaluateRuntimePolicy,
  memoryGrowthRatio,
} from './task13c-metrics.mjs';

const SOURCE_CARRIER_COMMIT = 'bf5ba41951b7d37c588ebd7abc0944a856782b2c';
const ASSET_CLASS = 'nonfinal_test_fixture';
const DEFAULT_DURATION_MS = 10 * 60 * 1000;
const MEMORY_SAMPLE_INTERVAL_MS = 30_000;
const MEMORY_SETTLED_BASELINE_MS = 2 * 60 * 1000;
const SOFTWARE_RENDERER_PATTERN = /swiftshader|llvmpipe|software rasterizer|microsoft basic render/i;

const requestedDuration = Number(new URLSearchParams(location.search).get('task13cDurationMs'));
const durationMs = Number.isFinite(requestedDuration) && requestedDuration >= 2_000
  ? requestedDuration
  : DEFAULT_DURATION_MS;

const state = {
  firstInteractiveAtMs: null,
  running: false,
  startedAtMs: null,
  endedAtMs: null,
  lastRuntimeFrameAtMs: null,
  runtimeFrameTimesMs: [],
  keyDownCount: 0,
  keyUpCount: 0,
  trackedKeys: { w: 0, a: 0, s: 0, d: 0, e: 0 },
  focusCount: 0,
  blurCount: 0,
  hiddenCount: 0,
  visibleCount: 0,
  contextLossCount: 0,
  contextRestoreCount: 0,
  fallbackCount: 0,
  errors: [],
  memorySamples: [],
  timerId: null,
  memoryTimerId: null,
  liveTimerId: null,
  canvasObserved: false,
};

const originalReplaceChildren = Element.prototype.replaceChildren;
Element.prototype.replaceChildren = function (...nodes) {
  const result = originalReplaceChildren.apply(this, nodes);

  if (this instanceof HTMLElement && this.classList.contains('runtime-app__overlay')) {
    const overlay = this.querySelector('.runtime-overlay');
    const mode = overlay?.dataset.runtimeMode ?? null;
    const now = performance.now();

    if (mode === 'interactive' && state.firstInteractiveAtMs === null) {
      state.firstInteractiveAtMs = now;
    }

    if (mode === 'fallback') {
      state.fallbackCount += 1;
    }

    if (state.running && mode === 'interactive') {
      if (state.lastRuntimeFrameAtMs !== null) {
        const delta = now - state.lastRuntimeFrameAtMs;
        if (Number.isFinite(delta) && delta > 0 && delta < 10_000) {
          state.runtimeFrameTimesMs.push(delta);
        }
      }
      state.lastRuntimeFrameAtMs = now;
    }
  }

  return result;
};

function formatBytes(value) {
  if (!Number.isFinite(value)) return 'n/a';
  return `${(value / 1024 / 1024).toFixed(1)} MiB`;
}

function memoryBytes() {
  const memory = performance.memory;
  return memory && Number.isFinite(memory.usedJSHeapSize)
    ? memory.usedJSHeapSize
    : null;
}

function captureMemorySample() {
  const bytes = memoryBytes();
  if (bytes === null || state.startedAtMs === null) return;
  state.memorySamples.push({
    elapsedMs: performance.now() - state.startedAtMs,
    usedJSHeapBytes: bytes,
  });
}

function canvasAndContext() {
  const canvas = document.querySelector('.runtime-app__scene canvas');
  if (!(canvas instanceof HTMLCanvasElement)) {
    return { canvas: null, gl: null };
  }
  const gl = canvas.getContext('webgl2');
  return { canvas, gl };
}

function attachContextListeners() {
  if (state.canvasObserved) return;
  const { canvas } = canvasAndContext();
  if (!canvas) return;
  state.canvasObserved = true;
  canvas.addEventListener('webglcontextlost', () => {
    state.contextLossCount += 1;
  });
  canvas.addEventListener('webglcontextrestored', () => {
    state.contextRestoreCount += 1;
  });
}

function webglSnapshot() {
  const { canvas, gl } = canvasAndContext();
  if (!canvas || !gl) {
    return {
      available: false,
      vendor: null,
      renderer: null,
      version: null,
      unmaskedVendor: null,
      unmaskedRenderer: null,
      softwareRendererDetected: null,
      framebuffer: null,
      cssSize: null,
    };
  }

  let unmaskedVendor = null;
  let unmaskedRenderer = null;
  const debugInfo = gl.getExtension('WEBGL_debug_renderer_info');
  if (debugInfo) {
    unmaskedVendor = gl.getParameter(debugInfo.UNMASKED_VENDOR_WEBGL);
    unmaskedRenderer = gl.getParameter(debugInfo.UNMASKED_RENDERER_WEBGL);
  }

  const renderer = gl.getParameter(gl.RENDERER);
  const rendererText = `${renderer ?? ''} ${unmaskedRenderer ?? ''}`;
  const rect = canvas.getBoundingClientRect();

  return {
    available: true,
    vendor: gl.getParameter(gl.VENDOR),
    renderer,
    version: gl.getParameter(gl.VERSION),
    unmaskedVendor,
    unmaskedRenderer,
    softwareRendererDetected: SOFTWARE_RENDERER_PATTERN.test(rendererText),
    framebuffer: { width: canvas.width, height: canvas.height },
    cssSize: { width: Math.round(rect.width), height: Math.round(rect.height) },
  };
}

function settledMemoryBaseline() {
  if (state.memorySamples.length === 0) return null;
  const eligible = state.memorySamples.filter(
    (sample) => sample.elapsedMs >= MEMORY_SETTLED_BASELINE_MS,
  );
  return (eligible[0] ?? state.memorySamples[0]).usedJSHeapBytes;
}

function finalMemoryBytes() {
  return state.memorySamples.length > 0
    ? state.memorySamples[state.memorySamples.length - 1].usedJSHeapBytes
    : null;
}

function buildEvidence() {
  const frames = summarizeFrameTimes(state.runtimeFrameTimesMs);
  const baselineMemory = settledMemoryBaseline();
  const finalMemory = finalMemoryBytes();
  const webgl2 = webglSnapshot();

  return {
    schemaVersion: 1,
    sourceCarrierCommit: SOURCE_CARRIER_COMMIT,
    assetClass: ASSET_CLASS,
    startedAt: state.startedAtMs === null
      ? null
      : new Date(performance.timeOrigin + state.startedAtMs).toISOString(),
    endedAt: state.endedAtMs === null
      ? null
      : new Date(performance.timeOrigin + state.endedAtMs).toISOString(),
    durationMs: state.startedAtMs === null
      ? 0
      : (state.endedAtMs ?? performance.now()) - state.startedAtMs,
    environment: {
      userAgent: navigator.userAgent,
      platform: navigator.platform,
      language: navigator.language,
      screen: { width: screen.width, height: screen.height },
      viewport: { width: innerWidth, height: innerHeight },
      devicePixelRatio,
      documentVisibility: document.visibilityState,
    },
    startupNavigationToInteractiveMs: state.firstInteractiveAtMs,
    webgl2,
    runtimeFrames: frames,
    policy: evaluateRuntimePolicy(frames.medianFps),
    inputs: {
      keyDownCount: state.keyDownCount,
      keyUpCount: state.keyUpCount,
      trackedKeys: state.trackedKeys,
    },
    focus: {
      focusCount: state.focusCount,
      blurCount: state.blurCount,
      hiddenCount: state.hiddenCount,
      visibleCount: state.visibleCount,
    },
    webglContext: {
      lossCount: state.contextLossCount,
      restoreCount: state.contextRestoreCount,
    },
    fallbackCount: state.fallbackCount,
    errors: state.errors,
    memory: {
      supported: 'memory' in performance,
      sampleCount: state.memorySamples.length,
      settledBaselineBytes: baselineMemory,
      finalBytes: finalMemory,
      growthRatio: memoryGrowthRatio(baselineMemory, finalMemory),
      samples: state.memorySamples,
    },
    caveat: 'webgl renderer strings do not independently prove browser hardware acceleration; chrome://gpu evidence remains required for formal real-GPU classification',
  };
}

function writeEvidence() {
  const output = document.querySelector('#task13c-evidence');
  if (output instanceof HTMLTextAreaElement) {
    output.value = JSON.stringify(buildEvidence(), null, 2);
  }
}

function updateLivePanel() {
  const frames = summarizeFrameTimes(state.runtimeFrameTimesMs);
  const status = document.querySelector('#task13c-live');
  if (!(status instanceof HTMLElement)) return;
  const elapsed = state.startedAtMs === null ? 0 : (state.endedAtMs ?? performance.now()) - state.startedAtMs;
  status.textContent = [
    `狀態：${state.running ? 'RUNNING' : state.endedAtMs ? 'COMPLETE' : 'READY'}`,
    `經過：${(elapsed / 1000).toFixed(1)} s / ${(durationMs / 1000).toFixed(0)} s`,
    `Runtime median：${frames.medianFps === null ? 'n/a' : frames.medianFps.toFixed(1)} FPS`,
    `p95 frame：${frames.p95FrameMs === null ? 'n/a' : `${frames.p95FrameMs.toFixed(1)} ms`}`,
    `WebGL context loss：${state.contextLossCount}`,
    `JS heap：${formatBytes(memoryBytes())}`,
  ].join('\n');
}

function finishProbe() {
  if (!state.running) return;
  state.running = false;
  state.endedAtMs = performance.now();
  captureMemorySample();
  if (state.timerId !== null) clearTimeout(state.timerId);
  if (state.memoryTimerId !== null) clearInterval(state.memoryTimerId);
  if (state.liveTimerId !== null) clearInterval(state.liveTimerId);
  state.timerId = state.memoryTimerId = state.liveTimerId = null;
  writeEvidence();
  updateLivePanel();

  const button = document.querySelector('#task13c-start');
  if (button instanceof HTMLButtonElement) {
    button.disabled = false;
    button.textContent = '重新開始正式測試';
  }
}

function startProbe() {
  if (state.running) return;
  attachContextListeners();
  state.running = true;
  state.startedAtMs = performance.now();
  state.endedAtMs = null;
  state.lastRuntimeFrameAtMs = null;
  state.runtimeFrameTimesMs = [];
  state.keyDownCount = 0;
  state.keyUpCount = 0;
  state.trackedKeys = { w: 0, a: 0, s: 0, d: 0, e: 0 };
  state.focusCount = 0;
  state.blurCount = 0;
  state.hiddenCount = 0;
  state.visibleCount = 0;
  state.contextLossCount = 0;
  state.contextRestoreCount = 0;
  state.fallbackCount = 0;
  state.errors = [];
  state.memorySamples = [];
  captureMemorySample();

  const button = document.querySelector('#task13c-start');
  if (button instanceof HTMLButtonElement) {
    button.disabled = true;
    button.textContent = '正式測試進行中';
  }

  state.memoryTimerId = setInterval(captureMemorySample, MEMORY_SAMPLE_INTERVAL_MS);
  state.liveTimerId = setInterval(updateLivePanel, 1000);
  state.timerId = setTimeout(finishProbe, durationMs);
  updateLivePanel();
}

function createPanel() {
  const panel = document.createElement('aside');
  panel.id = 'task13c-probe';
  panel.style.cssText = [
    'position:fixed',
    'right:12px',
    'top:12px',
    'z-index:2147483647',
    'width:min(420px,calc(100vw - 24px))',
    'max-height:calc(100vh - 24px)',
    'overflow:auto',
    'background:rgba(8,12,16,.94)',
    'color:#f4f4f4',
    'border:1px solid #46515d',
    'border-radius:10px',
    'padding:12px',
    'font:13px/1.45 ui-monospace,SFMono-Regular,Consolas,monospace',
    'box-shadow:0 10px 30px rgba(0,0,0,.35)',
  ].join(';');

  const heading = document.createElement('strong');
  heading.textContent = 'Task 13C-Low｜Real GPU Probe';

  const note = document.createElement('div');
  note.textContent = `固定 Source ${SOURCE_CARRIER_COMMIT.slice(0, 8)} · 預設 ${(durationMs / 60000).toFixed(1)} 分鐘`;
  note.style.margin = '6px 0';

  const live = document.createElement('pre');
  live.id = 'task13c-live';
  live.style.whiteSpace = 'pre-wrap';
  live.style.margin = '8px 0';

  const start = document.createElement('button');
  start.id = 'task13c-start';
  start.type = 'button';
  start.textContent = '開始正式測試';
  start.style.cssText = 'padding:8px 10px;margin:4px 6px 8px 0;cursor:pointer';
  start.addEventListener('click', startProbe);

  const finish = document.createElement('button');
  finish.type = 'button';
  finish.textContent = '提前結束';
  finish.style.cssText = 'padding:8px 10px;margin:4px 0 8px;cursor:pointer';
  finish.addEventListener('click', finishProbe);

  const output = document.createElement('textarea');
  output.id = 'task13c-evidence';
  output.readOnly = true;
  output.rows = 8;
  output.style.cssText = 'width:100%;box-sizing:border-box;background:#05080b;color:#cfe8ff;border:1px solid #46515d;padding:6px';

  const copy = document.createElement('button');
  copy.type = 'button';
  copy.textContent = '複製 Evidence JSON';
  copy.style.cssText = 'padding:8px 10px;margin-top:8px;cursor:pointer';
  copy.addEventListener('click', async () => {
    writeEvidence();
    await navigator.clipboard?.writeText(output.value).catch(() => {});
    output.select();
  });

  panel.append(heading, note, live, start, finish, output, copy);
  document.body.append(panel);
  updateLivePanel();
}

addEventListener('keydown', (event) => {
  if (!state.running || event.repeat) return;
  const key = event.key.toLowerCase();
  if (key in state.trackedKeys) {
    state.keyDownCount += 1;
    state.trackedKeys[key] += 1;
  }
}, true);

addEventListener('keyup', (event) => {
  if (!state.running) return;
  const key = event.key.toLowerCase();
  if (key in state.trackedKeys) state.keyUpCount += 1;
}, true);

addEventListener('focus', () => { if (state.running) state.focusCount += 1; }, true);
addEventListener('blur', () => { if (state.running) state.blurCount += 1; }, true);
document.addEventListener('visibilitychange', () => {
  if (!state.running) return;
  if (document.visibilityState === 'hidden') state.hiddenCount += 1;
  else state.visibleCount += 1;
});
addEventListener('error', (event) => {
  if (state.running) state.errors.push({ type: 'error', message: event.message || 'window_error' });
});
addEventListener('unhandledrejection', (event) => {
  if (state.running) state.errors.push({ type: 'unhandledrejection', message: String(event.reason) });
});

document.addEventListener('DOMContentLoaded', () => {
  createPanel();
  const waitForCanvas = setInterval(() => {
    attachContextListeners();
    if (state.canvasObserved) clearInterval(waitForCanvas);
  }, 250);
});
