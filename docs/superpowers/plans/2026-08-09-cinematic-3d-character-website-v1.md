# Cinematic 3D Character Website V1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a desktop-browser-first, frontend-only cinematic character showcase with real-time Three.js/WebGL2 rendering, named keyboard actions, explicit character/animation/camera/loading/fallback state, progressive quality handling, automated browser tests, and performance instrumentation using only nonfinal test assets until a final character is separately approved.

**Architecture:** A Vite + TypeScript application owns browser runtime state through small responsibility-focused modules. Rendering, input, state transitions, animation coordination, camera, asset loading, quality policy, UI state, and instrumentation communicate through typed contracts rather than shared mutable globals. The first executable milestone uses a legally usable nonfinal GLB test asset and explicit placeholder labeling; final cinematic asset acquisition remains outside this plan.

**Tech Stack:** TypeScript, Vite, Three.js WebGLRenderer/WebGL2, Vitest, Playwright, glTF/GLB test asset, optional KTX2/Meshopt loaders when runtime asset evidence exists.

## Global Constraints

- V1 is frontend-only: no backend, database, authentication, persistent account state, multiplayer, open world, combat, inventory, CMS, or cloud-streaming primary runtime.
- Renderer baseline is Three.js `WebGLRenderer` / WebGL2. WebGPU is experimental only and is not an acceptance dependency.
- No React, React Three Fiber, Tailwind, physics engine, backend framework, or database is introduced without an approved change.
- `cinematic_master_asset` and `web_runtime_asset` remain distinct. This plan uses only a nonfinal runtime test asset; it does not select a final cinematic master asset.
- Named input actions must own keyboard semantics; physical keys must not be scattered through character logic.
- Held input must clear on blur / visibility loss so the character cannot continue moving after focus loss.
- Character desired state and actual animation/runtime state must be represented separately.
- Camera is an independent subsystem with presentation, follow, and orbit/inspection behavior families.
- Quality degradation must reduce secondary environment/effects before core character identity/material quality.
- Required UI states: loading/entry, hero presentation, interactive view, fallback/error.
- Required performance baselines: 60 FPS median primary target; sustained <45 FPS triggers quality review/degradation; 30 FPS median minimum after approved degradation; cold start to minimum interactive <=10 s at 50 Mbps; warm start <=3 s; local named action visible <=100 ms; 10-minute scripted loop must not crash/lose WebGL context/leave uncontrolled movement; no sustained monotonic memory growth >20% after stabilization.
- Automated browser coverage targets Chromium, Firefox, and WebKit. Mobile/touch is not a mandatory V1 acceptance environment.
- Public production deployment, paid asset purchase, commissioning, final character adoption, and production credentials remain outside authorization.
- Apply `Web 專案開發規範 v1.0`: typed/predictable state, modularity by responsibility, explicit state ownership, boundary contracts, side-effect isolation, explicit error semantics, testability, traceability, performance, reliability, compatibility, accessibility, maintainability, and showcase visual/media/responsive obligations.

---

## Planned File Structure

```text
cinematic-3d-character-website/
├── index.html                         # Static HTML entry and accessibility fallback shell
├── package.json                       # Scripts and runtime/dev dependencies
├── tsconfig.json                      # Strict TypeScript configuration
├── vite.config.ts                     # Vite test/build configuration
├── playwright.config.ts               # Cross-browser E2E configuration
├── public/
│   └── assets/
│       └── test-character.glb          # Nonfinal, provenance-recorded test GLB only
├── src/
│   ├── main.ts                        # Composition root only
│   ├── styles.css                     # Minimal showcase UI styles
│   ├── app/
│   │   ├── RuntimeApp.ts              # Owns runtime lifecycle and subsystem coordination
│   │   └── RuntimeContracts.ts        # Shared app-level typed contracts
│   ├── state/
│   │   ├── CharacterState.ts          # Desired character state machine
│   │   ├── RuntimeState.ts            # Loading/interactive/fallback state machine
│   │   └── state.test.ts              # Deterministic state transition tests
│   ├── input/
│   │   ├── InputActions.ts            # Named actions and key map
│   │   ├── KeyboardInput.ts           # Browser keyboard/focus side effects
│   │   └── KeyboardInput.test.ts      # Action mapping and cleanup tests
│   ├── scene/
│   │   ├── Renderer.ts                # WebGL2 renderer/canvas lifecycle
│   │   ├── Lighting.ts                # Character-first lighting setup
│   │   └── Environment.ts             # Minimal subordinate environment
│   ├── assets/
│   │   ├── AssetLoader.ts             # GLB loading + explicit error results
│   │   ├── AssetManifest.ts           # Provenance/version/runtime test-asset metadata
│   │   └── AssetLoader.test.ts        # Loader contract tests with mocked loader boundary
│   ├── character/
│   │   ├── CharacterController.ts     # Movement/turn/action intent application
│   │   ├── AnimationCoordinator.ts    # Desired state -> available clip transition policy
│   │   └── CharacterController.test.ts
│   ├── camera/
│   │   ├── CharacterCamera.ts         # Presentation/follow/orbit behavior families
│   │   └── CharacterCamera.test.ts    # Deterministic framing behavior tests
│   ├── quality/
│   │   ├── QualityPolicy.ts           # Quality levels and degradation rules
│   │   ├── PerformanceMonitor.ts      # Frame/startup/memory instrumentation
│   │   └── QualityPolicy.test.ts      # Threshold/degradation tests
│   └── ui/
│       ├── RuntimeOverlay.ts           # Loading/input/fallback status presentation
│       └── RuntimeOverlay.test.ts      # Explicit UI-state rendering tests
├── tests/
│   └── e2e/
│       ├── runtime.spec.ts             # Load -> interactive -> movement/action flow
│       ├── focus-loss.spec.ts          # Held input cleanup regression
│       └── fallback.spec.ts            # Unsupported/runtime error presentation
└── docs/
    ├── assets/
    │   └── test-asset-provenance.md    # Source/license/hash/adaptation record
    └── validation/
        └── runtime-gate.md             # Versions, environment, commands, evidence, scope
```

---

### Task 1: Runtime Toolchain Gate and Strict Project Skeleton

**Files:**
- Create: `package.json`
- Create: `tsconfig.json`
- Create: `vite.config.ts`
- Create: `index.html`
- Create: `src/main.ts`
- Create: `src/app/RuntimeContracts.ts`
- Create: `docs/validation/runtime-gate.md`
- Test: `src/state/state.test.ts` (initial smoke test target)

**Interfaces:**
- Consumes: approved V1 stack `TypeScript + Vite + Three.js/WebGL2`, active Web handbook rules.
- Produces: `npm` scripts `dev`, `build`, `test`, `test:e2e`; strict TypeScript build; stable `RuntimeMode` and `RuntimeErrorCode` types for downstream tasks.

- [x] **Step 1: Verify local runtime prerequisites without changing the project**

Run:

```bash
node --version
npm --version
git --version
```

Expected: Node and npm are executable. Record exact versions in `docs/validation/runtime-gate.md`. If Node/npm are unavailable, stop this route as `BLOCKED`; do not substitute another build system.

- [x] **Step 2: Initialize package metadata and install only approved dependencies**

Create `package.json`:

```json
{
  "name": "cinematic-3d-character-website",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc --noEmit && vite build",
    "test": "vitest run",
    "test:watch": "vitest",
    "test:e2e": "playwright test"
  },
  "dependencies": {
    "three": "0.185.1"
  },
  "devDependencies": {
    "@playwright/test": "1.62.1",
    "@types/three": "0.185.1",
    "jsdom": "30.0.1",
    "typescript": "7.0.2",
    "vite": "8.2.1",
    "vitest": "4.1.10"
  }
}
```

Run:

```bash
npm install
```

Expected: dependency install exits 0. Record resolved versions with `npm ls --depth=0` in `docs/validation/runtime-gate.md`. If the Sandbox registry/network is blocked, use only the separately approved and Runtime-verified GitHub Actions dependency/bootstrap bridge; do not change the runtime stack. `jsdom` is dev-only and was added as a plan correction because the selected Vitest environment requires it.

- [x] **Step 3: Write the failing strict-state smoke test**

Create `src/state/state.test.ts`:

```ts
import { describe, expect, it } from 'vitest';
import { isInteractiveRuntimeMode } from '../app/RuntimeContracts';

describe('runtime contracts', () => {
  it('treats only interactive mode as interactive', () => {
    expect(isInteractiveRuntimeMode('interactive')).toBe(true);
    expect(isInteractiveRuntimeMode('loading')).toBe(false);
    expect(isInteractiveRuntimeMode('fallback')).toBe(false);
  });
});
```

- [x] **Step 4: Run the test and verify the RED state**

Run:

```bash
npm test -- src/state/state.test.ts
```

Expected: FAIL because `RuntimeContracts` / `isInteractiveRuntimeMode` does not exist.

Execution evidence (2026-08-10): executed through the verified GitHub Actions dependency/bootstrap bridge because Sandbox shell networking is unavailable. Run `31323594859` produced the package lockfile and confirmed the intended RED failure (`ERR_MODULE_NOT_FOUND` for `../app/RuntimeContracts`). The CI mirror is not the project Source SSOT.

- [x] **Step 5: Add strict configuration and minimal runtime contracts**

Create `tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "useDefineForClassFields": true,
    "module": "ESNext",
    "moduleResolution": "Bundler",
    "strict": true,
    "noUncheckedIndexedAccess": true,
    "exactOptionalPropertyTypes": true,
    "isolatedModules": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "types": ["vitest/globals"]
  },
  "include": ["src", "vite.config.ts", "playwright.config.ts", "tests"]
}
```

Create `vite.config.ts`:

```ts
import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    environment: 'jsdom',
  },
});
```

Create `src/app/RuntimeContracts.ts`:

```ts
export type RuntimeMode = 'loading' | 'presentation' | 'interactive' | 'fallback';

export type RuntimeErrorCode =
  | 'unsupported_webgl2'
  | 'renderer_initialization_failed'
  | 'asset_load_failed'
  | 'invalid_asset'
  | 'runtime_failure';

export function isInteractiveRuntimeMode(mode: RuntimeMode): boolean {
  return mode === 'interactive';
}
```

Create minimal `index.html` with one `#app` root and `<script type="module" src="/src/main.ts"></script>`. Create `src/main.ts` that renders only `Runtime bootstrap pending` text; no 3D behavior yet.

- [x] **Step 6: Run unit test and build**

Run:

```bash
npm test -- src/state/state.test.ts
npm run build
```

Expected: PASS and successful Vite build.

Execution evidence (2026-08-10): GitHub Actions run `31323865873` completed successfully. Vitest reported `1 passed`; `npm run build` completed `tsc --noEmit && vite build` with Vite `8.2.1`. Artifact `9040957865` returned the build output, resolved dependency evidence, and a lockfile whose SHA-256 exactly matches the formal Sandbox lockfile. The `vite.config.ts` import was corrected to `vitest/config` because the `test` block is a Vitest configuration surface; this is a test-config correction only, not a runtime architecture change.

- [x] **Step 7: Commit the Runtime Gate foundation**

```bash
git add package.json package-lock.json tsconfig.json vite.config.ts index.html src docs/validation/runtime-gate.md
git commit -m "chore: establish verified web runtime foundation"
```

---

### Task 2: Named Input Actions and Focus-Loss Safety

**Files:**
- Create: `src/input/InputActions.ts`
- Create: `src/input/KeyboardInput.ts`
- Create: `src/input/KeyboardInput.test.ts`

**Interfaces:**
- Consumes: DOM keyboard/focus events.
- Produces: `InputAction`, `InputSnapshot`, `KeyboardInput.start()`, `KeyboardInput.stop()`, `KeyboardInput.snapshot()`.

- [ ] **Step 1: Write failing tests for named actions and focus cleanup**

Create `src/input/KeyboardInput.test.ts`:

```ts
import { afterEach, describe, expect, it } from 'vitest';
import { KeyboardInput } from './KeyboardInput';

const activeInputs: KeyboardInput[] = [];
afterEach(() => activeInputs.splice(0).forEach((input) => input.stop()));

describe('KeyboardInput', () => {
  it('maps physical keys to named actions', () => {
    const input = new KeyboardInput(window);
    activeInputs.push(input);
    input.start();
    window.dispatchEvent(new KeyboardEvent('keydown', { code: 'KeyW' }));
    expect(input.snapshot().moveForward).toBe(true);
  });

  it('clears held actions when window loses focus', () => {
    const input = new KeyboardInput(window);
    activeInputs.push(input);
    input.start();
    window.dispatchEvent(new KeyboardEvent('keydown', { code: 'KeyW' }));
    window.dispatchEvent(new Event('blur'));
    expect(input.snapshot().moveForward).toBe(false);
  });
});
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
npm test -- src/input/KeyboardInput.test.ts
```

Expected: FAIL because `KeyboardInput` does not exist.

- [ ] **Step 3: Implement named action contracts and keyboard side-effect adapter**

Create `src/input/InputActions.ts`:

```ts
export type InputAction =
  | 'moveForward'
  | 'moveBackward'
  | 'turnLeft'
  | 'turnRight'
  | 'primaryAction';

export type InputSnapshot = Readonly<Record<InputAction, boolean>>;

export const DEFAULT_KEY_BINDINGS: Readonly<Record<string, InputAction>> = {
  KeyW: 'moveForward',
  ArrowUp: 'moveForward',
  KeyS: 'moveBackward',
  ArrowDown: 'moveBackward',
  KeyA: 'turnLeft',
  ArrowLeft: 'turnLeft',
  KeyD: 'turnRight',
  ArrowRight: 'turnRight',
  Space: 'primaryAction',
};

export const EMPTY_INPUT: InputSnapshot = Object.freeze({
  moveForward: false,
  moveBackward: false,
  turnLeft: false,
  turnRight: false,
  primaryAction: false,
});
```

Implement `KeyboardInput` so browser event handling is isolated from character logic. `blur` and hidden visibility state must clear all held actions.

- [ ] **Step 4: Run tests**

```bash
npm test -- src/input/KeyboardInput.test.ts
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/input
git commit -m "feat: add named keyboard input actions"
```

---

### Task 3: Deterministic Character and Runtime State Machines

**Files:**
- Create: `src/state/CharacterState.ts`
- Create: `src/state/RuntimeState.ts`
- Modify: `src/state/state.test.ts`

**Interfaces:**
- Consumes: `InputSnapshot`, runtime events.
- Produces: `CharacterDesiredState`, `RuntimeState`, pure reducers `reduceCharacterState()` and `reduceRuntimeState()`.

- [ ] **Step 1: Extend state tests with movement, action, and fallback transitions**

Add to `src/state/state.test.ts`:

```ts
import { EMPTY_INPUT } from '../input/InputActions';
import { reduceCharacterState } from './CharacterState';
import { reduceRuntimeState } from './RuntimeState';

it('moves from interactive idle to move from named input', () => {
  expect(
    reduceCharacterState('interactiveIdle', { ...EMPTY_INPUT, moveForward: true }),
  ).toBe('move');
});

it('gives primary action precedence over locomotion for one decision tick', () => {
  expect(
    reduceCharacterState('move', { ...EMPTY_INPUT, moveForward: true, primaryAction: true }),
  ).toBe('action');
});

it('enters explicit fallback on renderer failure', () => {
  expect(reduceRuntimeState({ mode: 'loading' }, { type: 'runtimeError', code: 'renderer_initialization_failed' }))
    .toEqual({ mode: 'fallback', error: 'renderer_initialization_failed' });
});
```

- [ ] **Step 2: Run tests and verify RED**

```bash
npm test -- src/state/state.test.ts
```

Expected: FAIL for missing reducers/types.

- [ ] **Step 3: Implement pure reducers**

`CharacterDesiredState` must include:

```ts
export type CharacterDesiredState =
  | 'presentationIdle'
  | 'interactiveIdle'
  | 'move'
  | 'turn'
  | 'stop'
  | 'action'
  | 'returnToIdle';
```

`reduceCharacterState()` maps action snapshots deterministically. `RuntimeState` must distinguish `loading`, `presentation`, `interactive`, and `fallback` with typed error codes; it must never encode all failure semantics as `false`/`undefined`.

- [ ] **Step 4: Run state tests**

```bash
npm test -- src/state/state.test.ts
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/state
git commit -m "feat: add explicit runtime and character state machines"
```

---

### Task 4: WebGL2 Renderer Bootstrap and Explicit Capability Failure

**Files:**
- Create: `src/scene/Renderer.ts`
- Create: `src/scene/Lighting.ts`
- Create: `src/scene/Environment.ts`
- Create: `src/scene/Renderer.test.ts`

**Interfaces:**
- Consumes: target container element and viewport dimensions.
- Produces: `RendererHandle` containing Three.js scene, camera, renderer, resize/dispose hooks; throws/returns typed initialization failure for unsupported WebGL2.

- [ ] **Step 1: Write failing renderer capability tests**

Create `src/scene/Renderer.test.ts` with an injected context-probe function so unit tests do not need a real GPU:

```ts
import { describe, expect, it } from 'vitest';
import { assertWebGL2Available } from './Renderer';

describe('renderer capability', () => {
  it('rejects an unavailable WebGL2 context explicitly', () => {
    expect(() => assertWebGL2Available(() => null)).toThrow('unsupported_webgl2');
  });
});
```

- [ ] **Step 2: Run test and verify RED**

```bash
npm test -- src/scene/Renderer.test.ts
```

Expected: FAIL because renderer module does not exist.

- [ ] **Step 3: Implement WebGL2 bootstrap**

`Renderer.ts` must create `WebGLRenderer` only after an explicit WebGL2 capability probe and must expose `dispose()` and resize handling. `Lighting.ts` adds neutral key/fill/rim lighting oriented around character readability. `Environment.ts` creates only a ground plane and subdued background; no open-world or decorative system.

- [ ] **Step 4: Run unit tests and build**

```bash
npm test -- src/scene/Renderer.test.ts
npm run build
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/scene
git commit -m "feat: add explicit WebGL2 scene bootstrap"
```

---

### Task 5: Provenance-Tracked Nonfinal GLB Asset Loading

**Files:**
- Create: `public/assets/test-character.glb`
- Create: `docs/assets/test-asset-provenance.md`
- Create: `src/assets/AssetManifest.ts`
- Create: `src/assets/AssetLoader.ts`
- Create: `src/assets/AssetLoader.test.ts`

**Interfaces:**
- Consumes: runtime asset manifest and URL.
- Produces: `RuntimeCharacterAsset` with root object, clips, source manifest; typed `AssetLoadError` on failure.

- [ ] **Step 1: Acquire only a legally reusable nonfinal GLB test asset within the approved asset-read/download scope**

Use an official/publicly licensed source. Record in `docs/assets/test-asset-provenance.md`:

```text
Asset title:
Source URL:
Source owner/repository:
License:
Downloaded at:
SHA-256:
Purpose: nonfinal runtime validation only
Final character approved: no
Adaptations performed: none
```

If source/license cannot be verified, do not use the asset; mark this task blocked.

- [ ] **Step 2: Write failing loader contract tests with an injected loader boundary**

Create tests that prove loader success preserves manifest metadata and loader failure returns `asset_load_failed` rather than `undefined`.

- [ ] **Step 3: Run tests and verify RED**

```bash
npm test -- src/assets/AssetLoader.test.ts
```

Expected: FAIL.

- [ ] **Step 4: Implement manifest and loader**

`AssetManifest.ts` must export a typed manifest for `/assets/test-character.glb` and state `finalAsset: false`. `AssetLoader.ts` wraps `GLTFLoader`; it may wire `MeshoptDecoder` only if the downloaded test asset requires it. KTX2 setup is deferred unless the actual asset requires KTX2.

- [ ] **Step 5: Run loader tests and build**

```bash
npm test -- src/assets/AssetLoader.test.ts
npm run build
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add public/assets/test-character.glb docs/assets src/assets
git commit -m "feat: add provenance-tracked runtime test asset loading"
```

---

### Task 6: Character Locomotion and Action Intent

**Files:**
- Create: `src/character/CharacterController.ts`
- Create: `src/character/CharacterController.test.ts`

**Interfaces:**
- Consumes: `CharacterDesiredState`, `InputSnapshot`, delta time, Three.js `Object3D` character root.
- Produces: controlled position/yaw updates and `CharacterMotionSnapshot` for camera/animation consumers.

- [ ] **Step 1: Write failing deterministic movement tests**

Test forward displacement, yaw turn direction, no movement in idle, and clamped delta time so a background-tab frame does not teleport the character.

Example:

```ts
it('moves forward in local character space', () => {
  const motion = stepCharacterMotion(
    { position: { x: 0, z: 0 }, yaw: 0 },
    'move',
    { ...EMPTY_INPUT, moveForward: true },
    0.1,
  );
  expect(motion.position.z).toBeLessThan(0);
});
```

- [ ] **Step 2: Run tests and verify RED**

```bash
npm test -- src/character/CharacterController.test.ts
```

Expected: FAIL.

- [ ] **Step 3: Implement pure motion math plus object application adapter**

Keep motion calculation pure/testable. Apply world transforms in a thin method. No physics engine.

- [ ] **Step 4: Run tests**

```bash
npm test -- src/character/CharacterController.test.ts
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/character/CharacterController.ts src/character/CharacterController.test.ts
git commit -m "feat: add deterministic character locomotion"
```

---

### Task 7: Animation Coordination with Graceful Missing-Clip Fallback

**Files:**
- Create: `src/character/AnimationCoordinator.ts`
- Create: `src/character/AnimationCoordinator.test.ts`

**Interfaces:**
- Consumes: `CharacterDesiredState`, available `AnimationClip[]`, Three.js mixer target.
- Produces: actual animation state and transition result; preserves interaction even when the nonfinal asset lacks a requested clip.

- [ ] **Step 1: Write failing animation policy tests**

Tests must cover: exact clip selection by semantic candidates; crossfade request when source/target clips differ; fallback to idle when walk/action clips are absent; no crash when asset has zero animations.

- [ ] **Step 2: Run tests and verify RED**

```bash
npm test -- src/character/AnimationCoordinator.test.ts
```

Expected: FAIL.

- [ ] **Step 3: Implement semantic clip mapping and transition policy**

Use normalized semantic candidates such as `idle`, `walk`, `run`, `turn`, `action`; do not hard-code a single vendor clip name. Maintain `desiredState` separately from `actualAnimationState`.

- [ ] **Step 4: Run tests**

```bash
npm test -- src/character/AnimationCoordinator.test.ts
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/character/AnimationCoordinator.ts src/character/AnimationCoordinator.test.ts
git commit -m "feat: coordinate character animation states"
```

---

### Task 8: Character-First Camera Behaviors

**Files:**
- Create: `src/camera/CharacterCamera.ts`
- Create: `src/camera/CharacterCamera.test.ts`

**Interfaces:**
- Consumes: character world transform, camera behavior mode, delta time, optional orbit input.
- Produces: smooth target camera position/look-at with presentation, follow, and orbit/inspection modes.

- [ ] **Step 1: Write failing camera tests**

Tests must verify follow target remains behind the character, interpolation is bounded (no instant uncontrolled jump), orbit radius stays inside configured min/max, and presentation mode targets the character upper body rather than world origin.

- [ ] **Step 2: Run tests and verify RED**

```bash
npm test -- src/camera/CharacterCamera.test.ts
```

Expected: FAIL.

- [ ] **Step 3: Implement camera policy**

Use a single camera system with behavior modes, not three unrelated camera objects. Use damped interpolation and explicit limits. Avoid collision/physics features not required by V1.

- [ ] **Step 4: Run tests**

```bash
npm test -- src/camera/CharacterCamera.test.ts
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/camera
git commit -m "feat: add character-first camera behaviors"
```

---

### Task 9: Quality Policy and Performance Instrumentation

**Files:**
- Create: `src/quality/QualityPolicy.ts`
- Create: `src/quality/PerformanceMonitor.ts`
- Create: `src/quality/QualityPolicy.test.ts`

**Interfaces:**
- Consumes: rolling FPS/frame-time samples, startup timestamps, memory samples where supported.
- Produces: `QualityLevel`, degradation recommendation, performance evidence snapshot.

- [ ] **Step 1: Write failing degradation-policy tests**

Tests must establish that sustained FPS below 45 requests degradation, but degradation order starts with optional effects/environment before character fidelity. 30 FPS is the minimum interactive floor, not an automatic success state.

- [ ] **Step 2: Run tests and verify RED**

```bash
npm test -- src/quality/QualityPolicy.test.ts
```

Expected: FAIL.

- [ ] **Step 3: Implement rolling metrics and quality decision**

Define:

```ts
export type QualityLevel = 'high' | 'balanced' | 'minimumInteractive';
```

Use bounded sample windows. Performance monitor exposes startup-to-interactive, median FPS, median frame time, and optional memory growth ratio without silently treating unsupported memory APIs as zero.

- [ ] **Step 4: Run tests**

```bash
npm test -- src/quality/QualityPolicy.test.ts
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/quality
git commit -m "feat: add runtime quality and performance policy"
```

---

### Task 10: Minimal UI States and Accessible Runtime Status

**Files:**
- Create: `src/ui/RuntimeOverlay.ts`
- Create: `src/ui/RuntimeOverlay.test.ts`
- Create: `src/styles.css`

**Interfaces:**
- Consumes: `RuntimeState`, loading progress, interaction focus status, quality level.
- Produces: accessible loading/status/error DOM without owning 3D business state.

- [ ] **Step 1: Write failing UI-state tests**

Tests must verify loading includes progress/status text, interactive mode exposes keyboard help and focus status, and fallback exposes the typed error and states that fallback is non-equivalent when realtime 3D is unavailable.

- [ ] **Step 2: Run tests and verify RED**

```bash
npm test -- src/ui/RuntimeOverlay.test.ts
```

Expected: FAIL.

- [ ] **Step 3: Implement DOM-only overlay**

Use semantic status elements (`role="status"`, `aria-live`) and minimal CSS. UI must not duplicate authoritative runtime state.

- [ ] **Step 4: Run tests**

```bash
npm test -- src/ui/RuntimeOverlay.test.ts
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/ui src/styles.css
git commit -m "feat: add explicit runtime status interface"
```

---

### Task 11: Runtime Composition Root and Minimum Interactive Milestone

**Files:**
- Create: `src/app/RuntimeApp.ts`
- Modify: `src/main.ts`
- Modify: `src/styles.css`
- Test: all unit tests

**Interfaces:**
- Consumes: all subsystem interfaces from Tasks 2-10.
- Produces: one lifecycle-managed runtime app with `start()` and `dispose()`, animation frame loop, loading -> presentation -> interactive transition, and explicit fallback path.

- [ ] **Step 1: Write a failing lifecycle test around injected subsystem fakes**

Test that successful renderer + asset initialization reaches `interactive`, renderer initialization failure reaches `fallback`, and `dispose()` stops input/animation-frame side effects.

- [ ] **Step 2: Run lifecycle test and verify RED**

```bash
npm test -- src/app/RuntimeApp.test.ts
```

Expected: FAIL.

- [ ] **Step 3: Implement `RuntimeApp` as the composition root**

`RuntimeApp` coordinates but does not absorb subsystem logic. The render loop sequence is: sample input -> reduce desired state -> step character motion -> update animation -> update camera -> sample performance/quality -> render -> update overlay. Errors are mapped to explicit `RuntimeState` fallback.

- [ ] **Step 4: Replace bootstrap placeholder in `src/main.ts`**

Instantiate the overlay/runtime app on `DOMContentLoaded`, start it, and register hot-reload/browser unload cleanup where appropriate.

- [ ] **Step 5: Run all unit tests and build**

```bash
npm test
npm run build
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/app src/main.ts src/styles.css
git commit -m "feat: integrate minimum interactive character runtime"
```

---

### Task 12: Playwright Cross-Browser Interaction and Focus-Loss Regression

**Files:**
- Create: `playwright.config.ts`
- Create: `tests/e2e/runtime.spec.ts`
- Create: `tests/e2e/focus-loss.spec.ts`
- Create: `tests/e2e/fallback.spec.ts`

**Interfaces:**
- Consumes: built/dev app.
- Produces: repeatable Chromium/Firefox/WebKit evidence for loading, interaction, focus cleanup, and fallback presentation.

- [ ] **Step 1: Configure Playwright projects**

Create `playwright.config.ts` with `chromium`, `firefox`, and `webkit` projects, `webServer.command = 'npm run dev -- --host 127.0.0.1'`, and deterministic viewport `1280x720` for automation. This does not replace separate 1920x1080 real-GPU validation.

- [ ] **Step 2: Write failing runtime flow test**

`runtime.spec.ts` must wait for `[data-runtime-mode="interactive"]`, send `KeyW`, assert character state changes to `move`, send `Space`, assert action state is observed, and assert no page errors.

- [ ] **Step 3: Write failing focus-loss cleanup test**

Expose an instrumentation-only `data-held-inputs` or test hook from `RuntimeApp`/overlay. Hold `KeyW`, dispatch window blur through page evaluate, and assert held action count returns to zero.

- [ ] **Step 4: Write fallback test**

Start the app with an approved test-only query flag such as `?forceWebGL2Failure=1` that is compiled only as a development/test diagnostic path. Assert fallback UI contains `unsupported_webgl2` and explicit non-equivalent fallback wording.

- [ ] **Step 5: Run tests and verify RED or missing browser binaries**

```bash
npx playwright install chromium firefox webkit
npm run test:e2e
```

Expected: initial FAIL until test hooks are wired. If browser download is blocked, record `BLOCKED` scope; do not claim cross-browser verification.

- [ ] **Step 6: Add minimal test hooks and make tests pass**

Expose state through inert `data-*` attributes or a read-only `window.__RUNTIME_DIAGNOSTICS__` object only in development/test builds. Do not let tests mutate production state directly.

- [ ] **Step 7: Run full E2E matrix**

```bash
npm run test:e2e
```

Expected: PASS on Chromium, Firefox, and WebKit for the automated scope.

- [ ] **Step 8: Commit**

```bash
git add playwright.config.ts tests src
git commit -m "test: verify cross-browser character interaction flow"
```

---

### Task 13: Performance Evidence and 10-Minute Stability Script

**Files:**
- Create: `tests/e2e/performance.spec.ts`
- Modify: `docs/validation/runtime-gate.md`

**Interfaces:**
- Consumes: runtime diagnostics from `PerformanceMonitor`.
- Produces: startup/FPS/frame-time/memory/stability evidence; clearly distinguishes automation environment from real-GPU acceptance evidence.

- [ ] **Step 1: Write automated metrics collection test**

Collect startup-to-interactive, rolling FPS/frame time, page errors, and memory metric availability. Do not assert real-GPU 60 FPS in CI/headless. Assert instrumentation returns typed values and no uncontrolled input remains.

- [ ] **Step 2: Add repeatable 10-minute scripted interaction mode**

Use Playwright to cycle movement, turn, action, orbit/inspection input where available, and focus loss/recovery. Capture WebGL context-loss event count and runtime errors.

- [ ] **Step 3: Run the stability test**

```bash
npx playwright test tests/e2e/performance.spec.ts --project=chromium
```

Expected: no crash, no context loss, no stuck input. Headless FPS is evidence of instrumentation only, not acceptance of GPU target.

- [ ] **Step 4: Update runtime gate record**

Record automated evidence plus explicit unverified real-GPU items:

```text
Real discrete-GPU 1920x1080 60 FPS target: pending manual/runtime environment evidence
Real integrated-GPU 30 FPS floor: pending manual/runtime environment evidence
Visual face/skin/eyes/hair/deformation quality: not testable with nonfinal asset
```

- [ ] **Step 5: Commit**

```bash
git add tests/e2e/performance.spec.ts docs/validation/runtime-gate.md
git commit -m "test: add runtime stability and performance evidence"
```

---

### Task 14: Layer 07 Integration Review Package

**Files:**
- Create: `docs/validation/layer-07-integration-review.md`
- Modify: `README.md` (create if absent)

**Interfaces:**
- Consumes: all test/build/runtime evidence and asset provenance record.
- Produces: an integration review that can be handed to Layer 08 without claiming final cinematic character acceptance.

- [ ] **Step 1: Run the full verification suite from a clean state**

```bash
rm -rf dist
npm test
npm run build
npm run test:e2e
```

Expected: all available automated checks PASS. Any browser/tool unavailable is recorded as blocked/partial rather than rewritten as pass.

- [ ] **Step 2: Write the integration review**

`docs/validation/layer-07-integration-review.md` must include:

```text
Approved proposal: cinematic-3d-character-website-solution-r1@1.0
Handbook: Web 專案開發規範 v1.0, bound
Artifact classification: formal_artifact
Automated unit tests: pass/fail with command
Build: pass/fail with command
Chromium E2E: pass/fail/blocked
Firefox E2E: pass/fail/blocked
WebKit E2E: pass/fail/blocked
Test asset provenance: pass/fail
Final cinematic asset selected: no
Real discrete GPU validation: pending/pass/fail
Real integrated GPU validation: pending/pass/fail
Character visual-quality acceptance: pending final asset
Scope deviations: none or explicit list
Reapproval triggers encountered: none or explicit list
Layer 08 readiness: partial/ready
```

- [ ] **Step 3: Add concise run instructions**

Create/update `README.md` with only setup, `npm run dev`, `npm test`, `npm run build`, `npm run test:e2e`, test-asset disclaimer, and excluded production deployment/asset scope.

- [ ] **Step 4: Commit**

```bash
git add README.md docs/validation/layer-07-integration-review.md
git commit -m "docs: record layer 07 integration evidence"
```

- [ ] **Step 5: Do not advance to Layer 08 based solely on automated placeholder-runtime success**

Layer 08 can receive the integrated runtime for engineering validation, but final cinematic visual acceptance remains blocked until a separately approved final master/runtime character asset is integrated and real-GPU visual/performance evidence exists.

---

## Plan Self-Review

- Spec coverage: runtime architecture, input, explicit state, camera, animation, asset provenance, loading/fallback, quality policy, cross-browser tests, stability/performance instrumentation, Web handbook binding, and excluded scope all map to explicit tasks.
- No final character asset acquisition is hidden in implementation. Task 5 allows only a nonfinal test asset with verified provenance/license.
- WebGPU, React/R3F, Tailwind, backend, database, physics, cloud streaming, paid assets, production deployment, and credentials are not introduced.
- Type names are consistent across tasks: `RuntimeMode`, `RuntimeErrorCode`, `InputAction`, `InputSnapshot`, `CharacterDesiredState`, `QualityLevel`.
- Automated performance evidence is not misrepresented as real-GPU acceptance.
