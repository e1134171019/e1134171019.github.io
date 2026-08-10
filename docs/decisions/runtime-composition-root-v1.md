# Cinematic 3D Character Website — Runtime Composition Root Decision v1

## Decision identity

- decision_id: `cinematic-3d-character-runtime-composition-v1`
- layer: `07`
- task: `Task 11 — Runtime Composition Root and Minimum Interactive Milestone`
- owner_domain: `web_development`
- capability: `web_build` / runtime integration
- formal_skill_route: `GENERAL_EXECUTION_FALLBACK`
- fallback_method: `web_runtime_implementation_and_project_scaffolding`
- execution_owner: `GPT_PROJECT_INTEGRATOR`
- primary_workspace: `SANDBOX_PRIMARY_WORKSPACE`
- independent_execution_validator: `GitHub Actions isolated executor mirror`
- status: `implementation_ready`

## Bound inputs

Task 11 consumes the already implemented subsystem contracts from Tasks 2–10 without redefining their authority:

- `KeyboardInput` owns physical keyboard translation and focus-loss cleanup.
- `RuntimeState` owns loading / presentation / interactive / fallback lifecycle state.
- `CharacterState` owns desired character state.
- `CharacterController` owns deterministic planar motion math and Object3D transform application.
- `AnimationCoordinator` owns desired-state to actual-animation selection/transition policy.
- `CharacterCamera` owns character-relative camera goals and interpolation.
- `Renderer` owns explicit WebGL2 bootstrap, scene/camera/renderer resources and resize/dispose.
- `AssetLoader` owns the typed GLB loading boundary and `asset_load_failed` mapping.
- `PerformanceMonitor` / `QualityPolicy` own metric collection and degradation recommendations.
- `RuntimeOverlay` renders authoritative runtime/quality state but does not own business state.

The nonfinal runtime fixture remains `TEST_CHARACTER_ASSET_MANIFEST`. The restored `public/assets/test-character.glb` must match the already recorded byte length 1664 and SHA-256 `ed52f7192b8311d700ac0ce80644e3852cd01537e4d62241b9acba023da3d54e` before it is treated as the Task 5 artifact. It remains nonfinal and non-equivalent to the cinematic target.

## Composition responsibility

`RuntimeApp` is the only Task 11 composition root. It may coordinate lifecycle and side effects but must not copy subsystem algorithms into the app layer.

Lifecycle:

1. Mount scene and overlay hosts; authoritative runtime state begins at `loading`.
2. Initialize WebGL2 renderer. Typed renderer errors map to runtime `fallback`.
3. Load the approved nonfinal runtime fixture. Typed asset errors map to runtime `fallback`.
4. Attach the loaded root to the scene and create input/animation/camera/performance adapters.
5. Reduce `loading -> presentation`, then enable interaction and reduce `presentation -> interactive`.
6. Start exactly one animation-frame loop.
7. `dispose()` cancels the frame request, stops input, unregisters resize/focus side effects, removes the character from the scene, and disposes the renderer.

Per-frame sequence is fixed by the implementation plan:

`sample input -> reduce desired state -> step/apply character motion -> animation transition/update -> camera update/apply -> performance/quality sample -> renderer render -> overlay update`

## State and error boundaries

- No raw key codes enter character/runtime state reducers.
- No second UI runtime state is introduced.
- `RuntimeApp.state` is a read-only view of the existing `RuntimeState` authority.
- Known renderer and asset errors preserve their typed codes.
- Unexpected composition/runtime failures map to `runtime_failure` and explicit fallback UI; they are not swallowed.
- Fallback stops active input/frame-loop side effects and releases renderer resources where created.

## Camera / quality integration tuning

Task 8 deliberately left final camera constants caller-configurable. Task 11 therefore supplies provisional integration defaults only; they are not final cinematic camera acceptance values.

Task 9 deliberately left the sustained-window sample count caller-configurable. Task 11 supplies an integration measurement window while preserving the approved FPS thresholds (60 target / 45 degradation trigger / 30 minimum floor). This does not constitute real-GPU performance acceptance.

Quality policy is sampled in Task 11. A recommendation is not allowed to claim a visual degradation action that has no implemented safe target. The runtime may update its quality level only when the selected level corresponds to an implemented character-safe degradation route; otherwise the recommendation remains evidence for later runtime validation.

## Bootstrap boundary

`src/main.ts` becomes the formal browser entry. It:

- imports the approved stylesheet;
- creates one `RuntimeApp` from `#app` after DOM readiness;
- calls `start()` once;
- registers browser unload/pagehide cleanup and Vite hot-dispose cleanup when available.

`src/vite-env.d.ts` is allowed as a minimal Vite TypeScript support file because Task 10 already established that formal CSS side-effect imports require Vite client typings under the current strict TypeScript configuration. It does not add runtime behavior or a new framework.

## Explicit non-claims

Task 11 does not prove:

- Chromium / Firefox / WebKit interaction behavior (Task 12);
- real discrete/integrated GPU performance (Task 13/manual evidence);
- 10-minute stability;
- final cinematic face/skin/eyes/hair/deformation quality;
- final character asset selection or approval;
- production deployment or public release.

No React/R3F, Tailwind, backend, database, physics engine, cloud streaming, WebGPU primary route, credentials, paid assets, or production deployment are introduced.
