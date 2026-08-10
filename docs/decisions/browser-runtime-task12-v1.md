# Task 12 Decision — Cross-Browser Runtime Smoke and Failure Evidence

Decision ID: cinematic-3d-character-browser-runtime-task12-v1
Date: 2026-08-10
Layer: 07
Status: EXECUTION_DECISION

## Scope

Task 12 verifies the formal Vite/Three.js runtime in Playwright Chromium, Firefox, and WebKit at 1280×720. It adds only test observability and a development-only forced WebGL2 failure path. It does not change the WebGL2 baseline, character asset policy, renderer architecture, production fallback semantics, or approved input bindings.

## Binding decisions

1. `primaryAction` is verified with `KeyE`, not Space. Task 2's approved input decision is authoritative; the older Task 12 plan example using Space is stale and is treated as a documented plan deviation.
2. Browser observability uses inert, read-only DOM data attributes only when `import.meta.env.DEV` is true:
   - `data-character-runtime`
   - `data-state`
   - `data-held-inputs`
3. `data-held-inputs` is derived from the same `InputSnapshot` consumed by the production frame loop. Tests cannot mutate runtime state through the diagnostic surface.
4. `?forceWebGL2Failure=1` is recognized only in a development build. It injects the existing renderer seam with a WebGL2 context probe returning `null`, causing the existing typed `unsupported_webgl2` path. No new fallback renderer is introduced.
5. Production builds must ignore the diagnostic query flag and must not depend on diagnostic DOM attributes.
6. Playwright's 1280×720 automated evidence does not satisfy the approved 1920×1080 real-hardware GPU acceptance gate.
7. If a CI browser engine cannot expose WebGL2 independently of the product runtime, that engine is recorded as an executor-environment blocker. The product must not silently downgrade to WebGL1 to make the CI matrix pass.
