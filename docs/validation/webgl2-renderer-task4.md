# Layer 07 Task 4 Validation — WebGL2 Renderer Bootstrap

Date: 2026-08-10 (+08:00)
Proposal: `cinematic-3d-character-website-solution-r1@1.0`
Task: `layer07-task4-webgl2-renderer-bootstrap`
Capability: `CAP-14 web_runtime_implementation_and_project_scaffolding`
Execution route: `GENERAL_EXECUTION_FALLBACK`
Decision: `docs/decisions/webgl2-renderer-bootstrap-v1.md`
Formal workspace: `/mnt/data/cinematic-3d-character-website/.worktrees/layer07-v1`

## Scope validated

This task validates only the browser scene bootstrap boundary:

- explicit WebGL2 capability probe before Three.js `WebGLRenderer` construction;
- typed `unsupported_webgl2` and `renderer_initialization_failed` errors;
- `RendererHandle` ownership of bootstrap `Scene`, placeholder `PerspectiveCamera`, renderer, resize, and dispose lifecycle;
- minimal character-readability lighting as separate key/fill/rim directional lights;
- minimal environment as subdued background plus one ground plane;
- scene integration so the renderer-created scene contains the lighting and environment;
- disposal of bootstrap-owned ground geometry/material, renderer, and attached canvas;
- one isolated headless browser render smoke using the default WebGL2/Three renderer path.

Explicitly not validated here: final character asset, GLB loading, animation, project camera controller, input-to-motion integration, visual acceptance, performance budget, discrete/integrated real-GPU acceptance, Firefox/WebKit runtime, mobile/touch, deployment, or production release.

## TDD evidence

### RED-1 — WebGL2 capability module missing

- GitHub Actions run: `31326092429`
- Result: expected RED.
- Dependency install succeeded.
- Failure: `Failed to resolve import "./Renderer"` from `Renderer.test.ts`.

### RED-2 — Renderer lifecycle missing

- GitHub Actions run: `31326205438`
- Result: expected RED.
- Existing WebGL2 capability test remained PASS.
- New lifecycle tests failed because `createRendererHandle` did not yet exist.

### RED-3 — Lighting module missing

- GitHub Actions run: `31326319395`
- Result: expected RED.
- Failure: `Failed to resolve import "./Lighting"`.

### RED-4 — Environment module missing

- GitHub Actions run: `31326420922`
- Result: expected RED.
- Failure: `Failed to resolve import "./Environment"`.

### RED-5 — Scene integration missing

- GitHub Actions run: `31326611909`
- Result: expected RED.
- Four existing Task 4 tests passed; one integration test failed.
- Exact failure: renderer-created scene returned `undefined` for `character-readability-lighting`.
- This demonstrates the failure was at the intended handoff/integration boundary, not dependency installation or an unrelated regression.

## Verification defect found and corrected

An early Task 4 CI workflow used `npm run build 2>&1 | tee ...` without `pipefail`. The shell therefore reported the pipeline as successful even though TypeScript emitted:

`TS2339: Property 'isColor' does not exist on type 'Color | Texture<...>'`.

This invalidated the earlier build-PASS interpretation. The root cause was a test assertion that accessed `scene.background?.isColor` without type narrowing, plus CI pipeline error masking.

Corrections:

- changed the test to `expect(scene.background).toBeInstanceOf(Color)`;
- made full regression and build verification fail closed with `set -o pipefail`;
- made the browser-smoke build and smoke command fail closed as well;
- reran all affected verification after the correction.

No production behavior was weakened to make the build pass.

## Final unit / regression / build verification

GitHub Actions run: `31326961696`

- targeted `src/scene/Renderer.test.ts`: **5 / 5 PASS**;
- full unit regression: **25 / 25 PASS** across 3 test files;
- strict TypeScript: **PASS**;
- Vite production build: **PASS**;
- dependency installation: **PASS** on Node `22.23.1` / npm `10.9.8` in GitHub Actions.

Final CI source SHA-256 values:

```text
f79d991d6be917c64b2b8c174c551d29ddcda197f0a8a7638cb4bc4a2ed4885a  src/scene/Environment.ts
523f4cc5eb33d0fe6d6b93d6367aeb8034f105911b9637464a3a3a4aa15a61c9  src/scene/Lighting.ts
ddd1ce02a01d4436cbba06740ecefd8ff69d91cf0b3c97f1e355d92d647f6e04  src/scene/Renderer.test.ts
5e8a62f36b5d93688470c031ff79ffdbf4c54c2313510586aed7227900341dc1  src/scene/Renderer.ts
```

These hashes were compared with the formal Sandbox files and matched exactly.

## Runtime verification — headless WebGL2 / Three renderer

GitHub Actions run: `31326982224`

The workflow used a preinstalled `/usr/bin/google-chrome`; no browser download or additional product dependency was introduced. The executor-only smoke entry imported the formal scene modules, called the default `createRendererHandle`, positioned the bootstrap camera, and executed one real `renderer.render(scene, camera)` frame.

Result:

```json
{
  "status": "pass",
  "webglVersion": "WebGL 2.0 (OpenGL ES 3.0 Chromium)",
  "webglRenderer": "WebKit WebGL",
  "errorCode": null,
  "errorMessage": null,
  "userAgent": "HeadlessChrome/150.0.0.0",
  "executionClass": "headless_software_gpu_smoke_only",
  "realGpuAcceptance": false
}
```

Runtime interpretation:

- `RUNTIME_VERIFIED`: default WebGL2 context acquisition + Three `WebGLRenderer` construction + minimal scene creation + one-frame render in Headless Chrome software-GPU test scope.
- `UNVERIFIED`: real discrete GPU, real integrated GPU, hardware driver variability, Firefox/WebKit actual rendering, visual quality, frame-rate/performance budget, long-run context stability.

## Sandbox dependency note

A direct `npm ci --ignore-scripts` attempt in the formal Sandbox was blocked by the environment's internal npm mirror returning HTTP 404 for `xmlchars-2.2.0.tgz`. The same locked dependency set installed successfully in GitHub Actions. This is recorded as an execution-environment blocker, not a product-code failure. No dependency, registry, framework, or rendering fallback was substituted.

## Handbook / architecture conformance review

Applicable Web Handbook v1.0 rules were checked for this node:

- Type & Predictability: PASS — typed initialization errors and typed renderer interfaces.
- Modularity / Responsibility Separation: PASS — renderer, lighting, and environment remain distinct modules.
- State Ownership: PASS — renderer does not duplicate `RuntimeState`; it exposes typed failure for the runtime owner to consume later.
- Contract & Boundary: PASS — container, viewport, WebGL2 probe, renderer factory, resize, dispose, and failure semantics are explicit.
- Side-effect Isolation: PASS — injectable probes/factories allow GPU-independent unit tests; DOM/GPU effects stay at renderer boundary.
- Error Explicitness: PASS — no silent WebGL1, WebGPU, Canvas, video, or static-image substitution.
- Testability / Traceability: PASS within recorded scope — RED/GREEN chain, source hashes, CI runs, and smoke evidence retained.
- Showcase obligation: PASS for this bootstrap scope — environment is deliberately subordinate and lighting is oriented around future character readability.

## Capability cross review

Result: `pass` for Task 4 scope.

The output directly closes the renderer-bootstrap gap: the project now has an explicit, testable WebGL2/Three scene foundation rather than only architecture/state contracts. Lighting and environment are integrated into the same runnable scene, not delivered as disconnected modules.

## Project / outcome cross review

Outcome progress: `advanced`, not project-complete.

Remaining project gaps include:

- provenance-tracked nonfinal runtime character asset loading;
- animation mixer/state integration;
- project-specific camera controller;
- input/state → actual character motion handoff;
- progressive loading/fallback presentation;
- performance and stability instrumentation;
- character visual-quality validation;
- real hardware/browser matrix acceptance.

No upstream assumption was invalidated. No scope, architecture, engine, asset strategy, cost, credential, deployment, or public-release change was introduced. No return to Layer 06 is required.
