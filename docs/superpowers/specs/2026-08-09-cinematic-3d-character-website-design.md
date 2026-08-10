# Cinematic 3D Character Website — Layer 07 Design Spec

Date: 2026-08-09
Proposal: cinematic-3d-character-website-solution-r1
Revision: 1.0
Scenario: showcase
Status: approved design translated for Layer 07 execution

## 1. Goal

Build a desktop-browser-first interactive showcase whose primary visual and product value is one cinematic, photoreal 3D human character rendered in real time in the browser. The character must be directly controllable from the keyboard; prerecorded video, prerendered interactive video, static imagery, or a low-quality generic game character are not acceptable substitutes.

The product is a frontend-only browser application. V1 has no backend, database, authentication, persistent account state, multiplayer, open world, combat, inventory, CMS, or cloud-streaming primary runtime.

## 2. Approved Runtime Architecture

The V1 runtime is TypeScript + Vite + Three.js using WebGLRenderer/WebGL2 as the stable renderer baseline. WebGPU is experimental only and is not an acceptance dependency. No React, React Three Fiber, Tailwind, physics engine, backend framework, or database is introduced in V1 unless a later approved change requires it.

The browser owns runtime interaction state. Core authoritative state families are:

- input focus and named input actions
- character locomotion/action state
- animation state
- camera state
- loading state
- device/runtime capability state
- quality/fallback state

The runtime is divided by responsibility rather than by arbitrary file size. Expected boundaries include renderer/bootstrap, asset loading, input actions, character state, animation coordination, camera control, quality/performance policy, UI/loading/fallback presentation, and validation hooks.

## 3. User Experience Flow

1. User opens the site.
2. A loading/entry view reports progress while the minimum interactive character package loads.
3. The site presents the character as the dominant hero visual.
4. The experience enters interactive mode.
5. Keyboard input maps physical keys to named actions rather than hard-coding behavior throughout the codebase.
6. Named actions drive character state such as Idle, Move, Turn, Stop, and at least one non-locomotion Action.
7. Animation transitions follow character state and avoid obvious hard cuts.
8. Camera behavior keeps the character framed and observable during movement and close-up inspection.
9. Higher-quality assets may continue loading after minimum interactivity is reached.
10. If device capability is insufficient, secondary environment/effects are degraded before core character identity and critical material fidelity.
11. Runtime or capability failure enters an explicit fallback/error state rather than silently pretending full contract completion.

## 4. Character Asset Architecture

There are two distinct asset tiers for one character identity.

### cinematic_master_asset

High-fidelity, editable source/reference tier. It preserves the best available geometry, face/body proportions, skin, eyes, hair, clothing/material sources, rig, animation sources, provenance, version identity, and usage rights. Blender is the approved DCC for adaptation and corrective work. This tier must not be shipped directly to the browser merely because it can technically be loaded.

### web_runtime_asset

A separately derived browser-execution tier. Primary runtime format is binary glTF/GLB. Runtime adaptation may use KTX2/Basis Universal for texture delivery, Meshopt as the primary geometry/animation compression candidate, and glTF Transform for optimization. Every runtime derivative must remain traceable to its master source and adaptation record.

Optimization must preserve, in priority order, face identity, eyes, skin credibility, hair credibility, silhouette/body proportions, clothing/material identity, and major joint deformation quality. If optimization visibly destroys the character identity or high-attention features, that optimization is rejected even if performance improves.

## 5. Interaction and State Design

Input is expressed as named actions. The initial design requires forward/back or equivalent directional locomotion/turning plus at least one non-locomotion action. Exact physical key bindings remain an implementation detail unless later promoted to a user-facing requirement.

Focus loss, tab switching, runtime interruption, or similar browser events must clear held-input state so the character cannot continue moving uncontrollably.

The initial state model is:

- Loading
- Presentation Idle
- Interactive Idle
- Move
- Turn
- Stop
- Action
- Return to Idle
- Fallback/Error

Transitions must have explicit ownership and failure behavior. Character desired state and actual animation/runtime state are not treated as the same variable.

## 6. Camera Design

The camera is an independent subsystem coordinated with character state. V1 supports a character-first presentation model with three behavior families: hero/presentation framing, interactive follow, and orbit/close-up inspection. These are behavioral responsibilities, not a requirement for three unrelated camera implementations.

The camera must avoid sustained jitter, abrupt uncontrolled jumps, severe occlusion, and obvious clipping that prevents character inspection. Camera transitions should be state-aware and must not reduce character readability merely to create visual spectacle.

## 7. Scene and Visual Priority

The scene is controlled and subordinate to the character. It provides lighting context, scale, grounding, and cinematic composition. It is not an open-world environment.

Quality priority is:

1. character identity and face
2. skin, eyes, hair, clothing/material credibility
3. deformation and animation quality
4. camera stability/composition
5. lighting and character readability
6. secondary environment
7. optional visual effects

When performance pressure appears, degradation moves from the bottom of this list upward, not the reverse.

## 8. Loading, Quality, and Performance Policy

The application reaches a minimum interactive state before all optional/high-quality resources are necessarily present. Higher-quality resources can continue to stream/load after interaction begins.

Approved V1 targets:

- primary quality target: 60 FPS median on the reference discrete-GPU class
- quality review/degradation trigger: sustained inability to maintain 45 FPS in the repeatable interaction window
- minimum interactive floor after approved degradation: 30 FPS median on the reference integrated-GPU class
- cold start to minimum interactive: <= 10 s on 50 Mbps cold-cache reference network
- warm start: <= 3 s in the same reference environment when required assets are cached
- local named-action/state transition should become visible within <= 100 ms
- 10-minute scripted interaction loop must not crash, lose WebGL context, or leave uncontrolled movement after focus loss
- after a 2-minute stabilization period, the remaining fixed test loop must not show sustained monotonic memory growth >20%

These targets are acceptance baselines, not permission to damage core character visual quality to achieve a number.

## 9. Browser and Device Validation

Automated browser coverage targets Chromium, Firefox, and WebKit. Real-GPU validation requires at minimum a primary desktop/laptop discrete-GPU class at 1920x1080 and a desktop/laptop integrated-GPU class. At least Chromium must be exercised on both hardware classes, plus one non-Chromium real browser where matching hardware/OS is available.

Mobile/touch is not a mandatory V1 acceptance environment.

Playwright is the selected repeatable browser automation route, but screenshots alone cannot prove interactive runtime behavior. Real-browser/GPU evidence remains required for visual and performance claims.

## 10. UI / UX Responsibilities

The UI is intentionally minimal so it does not compete with the character. Required views/states are loading/entry, hero character presentation, interactive character view, and fallback/error presentation. UI must communicate loading, input focus, interaction availability, and error/fallback state clearly.

The project uses the approved GENERAL_EXECUTION_FALLBACK for UX/UI execution because no writable specialist design app was validated. That fallback does not remove independent review requirements.

## 11. Error Handling

Errors are explicit. Loading, invalid asset, unsupported capability, runtime initialization failure, input focus loss, and fallback state must not collapse into generic null/false/undefined handling.

A failed high-quality asset upgrade must not necessarily kill minimum interaction if a valid lower quality path exists. Conversely, if the browser cannot provide an equivalent realtime 3D runtime, the fallback must be labeled non-equivalent and cannot be counted as completing the core outcome contract.

## 12. Testing Strategy

Tests are layered by responsibility:

- unit/state tests for named input actions and deterministic state transitions
- runtime smoke tests for Vite/TypeScript bootstrap and Three.js WebGL2 initialization
- asset loading validation for a legally usable nonfinal GLB test asset
- animation state smoke tests using a nonfinal compatible test asset where available
- Playwright flows for loading entry, keyboard input, movement/action transition, focus-loss cleanup, and fallback presentation
- real-browser/GPU visual inspection for camera stability and character material/deformation quality
- repeatable performance instrumentation for startup, frame time/FPS, memory, and stability

Runtime Gate failures block the affected core route. They do not authorize silent substitution of another engine, cloud streaming, or a different asset strategy.

## 13. Source, Workspace, and Delivery

The formal implementation workspace begins as an isolated local Git repository. GitHub becomes the source/version SSOT after repository creation. Vercel is approved only as a preview target after local validation; public production deployment remains separately unapproved.

No production credentials or secrets are placed in source or client assets.

## 14. Explicitly Excluded / Separately Approved Work

The following remain outside the present authorization:

- purchase of a paid character asset
- commissioning character, rigging, or animation work
- adoption of a specific final cinematic master asset
- public production deployment
- production credentials or secrets
- architecture/contract scope changes
- multiplayer, open world, game systems, advanced conversational AI, lip sync, full facial performance, or gaze interaction unless contract change is approved

## 15. Reapproval Triggers

Stop the affected work and return to governance when any of these change materially: core runtime/engine route, delivery architecture, visible outcome, required interaction, asset acquisition strategy, final character choice, paid action, credential use, production deployment, or any change that expands the outcome contract.

## 16. Development Handbook Binding

`Web 專案開發規範 v1.0` is active and required for all web-development create/modify/test/maintain nodes in this project. Layer 07 applies it using MUST_READ -> MUST_BIND -> MUST_APPLY -> MUST_VERIFY. The most relevant core rules for this project are typed/predictable state, responsibility-based modularity, explicit state ownership, module contracts/boundaries, side-effect isolation, explicit error semantics, testability, traceability, performance, reliability, compatibility, accessibility, maintainability, and showcase-specific visual/media/responsive obligations.

